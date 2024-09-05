from __future__ import annotations

import json
import os
from copy import deepcopy
from pprint import pprint
from typing import Dict, List, Tuple
from configs import HUB_NAME

import yaml

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import (
    attach_yml_ambient_native,
    attach_yml_ambient_wasm,
)
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def compile_wasm_elements(girs: Dict[str, GraphIR]):
    global wasm_not_empty
    wasm_not_empty = False
    compiled_elements = set()
    for gir in girs.values():
        for element in gir.elements["ambient"]:
            if (
                element.lib_name not in compiled_elements
                and element.target == "ambient_wasm"
            ):
                wasm_not_empty = True
                compiled_elements.add(element.lib_name)
                impl_dir = os.path.join(
                    local_gen_dir, f"{element.lib_name}_{element.target}"
                )
                # Compile
                execute_local(
                    [
                        "cargo",
                        "build",
                        "--target=wasm32-wasi",
                        "--manifest-path",
                        os.path.join(impl_dir, "Cargo.toml"),
                        "--release",
                    ]
                )
                # copy binary to /tmp/appnet
                execute_local(
                    [
                        "cp",
                        os.path.join(
                            impl_dir,
                            f"target/wasm32-wasi/release/{element.lib_name}.wasm",
                        ),
                        "/tmp/appnet",
                    ]
                )


def generate_native_element_image(girs: Dict[str, GraphIR]):
    global native_not_empty
    native_not_empty = False
    inserted_elements = set()
    for gir in girs.values():
        for element in gir.elements["ambient"]:
            if (
                element.lib_name not in inserted_elements
                and element.target == "ambient_native"
            ):
                native_not_empty = True
                inserted_elements.add(element.lib_name)
                impl_dir = os.path.join(
                    local_gen_dir, f"{element.lib_name}_{element.target}"
                )

                filter_name = element.lib_name
                # Copy $impl_dir/appnet_filter to istio-proxy/source/extensions/filters/http/$filter_name
                # if exists, delete the old one
                if os.path.exists(
                    os.path.join(
                        generated_istio_proxy_path,
                        "source/extensions/filters/http",
                        filter_name,
                    )
                ):
                    os.system(
                        f"rm -rf {generated_istio_proxy_path}/source/extensions/filters/http/{filter_name}"
                    )

                execute_local(
                    [
                        "cp",
                        "-r",
                        os.path.join(impl_dir, "appnet_filter"),
                        os.path.join(
                            generated_istio_proxy_path,
                            "source/extensions/filters/http",
                            filter_name,
                        ),
                    ]
                )

                # Do source code transformation to make it fit in.
                for root, _, files in os.walk(
                    os.path.join(
                        generated_istio_proxy_path,
                        "source/extensions/filters/http",
                        filter_name,
                    )
                ):
                    for file in files:
                        # if file does not ends with .cc or .h or proto
                        suffix = file.split(".")[-1]
                        if suffix not in ["cc", "h", "proto"]:
                            continue
                        file_path = os.path.join(root, file)
                        with open(file_path, "r") as f:
                            lines = f.readlines()
                        with open(file_path, "w") as f:
                            for line in lines:
                                # Rule 1. Change the include path of the .pb.h and .pb.validate.h files.
                                # We replace prefix "appnet_filter/" with "source/extensions/filters/http/".
                                #
                                # For example
                                # Origin: #include "appnet_filter/echo.pb.h"
                                # After: #include "source/extensions/filters/http/${filter_name}/echo.pb.h"

                                if "#include" in line and (
                                    ".pb.h" in line or ".pb.validate.h" in line
                                ):
                                    file_name = line.split("/")[-1].split(".")[0]
                                    line = line.replace(
                                        f'#include "appnet_filter/{file_name}.pb.h"',
                                        f'#include "source/extensions/filters/http/{filter_name}/{file_name}.pb.h"',
                                    )
                                    line = line.replace(
                                        f'#include "appnet_filter/{file_name}.pb.validate.h"',
                                        f'#include "source/extensions/filters/http/{filter_name}/{file_name}.pb.validate.h"',
                                    )

                                # Rule 2. replace all AppNetSampleFilter and appnetsamplefilter
                                line = line.replace(
                                    "AppNetSampleFilter", f"appnet{filter_name}"
                                )
                                line = line.replace(
                                    "appnetsamplefilter", f"appnet{filter_name}"
                                )

                                # Rule 3. webdis_cluster -> webdis-service-{filter_name}
                                line = line.replace(
                                    "webdis_cluster", f"webdis-service-{filter_name}"
                                )

                                f.write(line)
    # Modify BUILD.
    # Checkout the BUILD fiel template first.
    # i.e. execute "git checkout origin/master -- source/extensions/filters/http/appnet_filter/BUILD" in that directory
    if native_not_empty:
        ROOT_BUILD_FILE = os.path.join(generated_istio_proxy_path, "BUILD")
        subprocess.run(
            [
                "git",
                "checkout",
                "origin/master",
                "--",
                ROOT_BUILD_FILE,
            ],
            cwd=generated_istio_proxy_path,
            check=True,
        )

        with open(ROOT_BUILD_FILE, "r") as f:
            lines = f.readlines()

        # Insert "//source/extensions/filters/http/${filter_name}:appnet_filter_lib", in the correct position
        insert_idx = 0
        for idx, line in enumerate(lines):
            if "# !APPNET_FILTERS\n" in line:
                insert_idx = idx
                break
        for element in inserted_elements:
            lines.insert(
                insert_idx,
                f'    "//source/extensions/filters/http/{element}:appnet_filter_config",\n',
            )

        with open(ROOT_BUILD_FILE, "w") as f:
            f.writelines(lines)

        GRAPH_BACKEND_LOG.info(
            f"The istio envoy source code is generated successfully in {generated_istio_proxy_path}."
        )


def compile_native_image():
    global native_image_name
    native_image_name = f"{HUB_NAME}/proxyv2:1.22.3-distroless"
    if os.getenv("APPNET_NO_BAKE") != "1":
        GRAPH_BACKEND_LOG.info("Building the istio ambient...")
        execute_local(
            ["bash", "build.sh"],
            cwd=generated_istio_proxy_path,
        )
        # Bake the istio proxy image.
        GRAPH_BACKEND_LOG.info("Building the istio proxy image...")
        execute_local(
            [
                "docker",
                "build",
                "-t",
                f"{native_image_name}",
                "-f",
                "Dockerfile.istioproxy",
                ".",
            ],
            cwd=generated_istio_proxy_path,
        )
        GRAPH_BACKEND_LOG.info(
            f"Docker image {native_image_name} is built successfully."
        )

        # Push the image to the docker hub.
        GRAPH_BACKEND_LOG.info("Pushing the istio proxy image to the docker hub...")
        execute_local(["docker", "push", native_image_name])
        GRAPH_BACKEND_LOG.info(
            f"Docker image {native_image_name} is pushed successfully."
        )
    else:
        GRAPH_BACKEND_LOG.info("Skip building and pushing the istio proxy image.")


def scriptgen_ambient(
    girs: Dict[str, GraphIR],
    app_name: str,
    app_install_file: str,
    app_edges: List[Tuple[str, str]],
):
    global local_gen_dir, native_gen_dir, deploy_dir
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    native_gen_dir = os.path.join(graph_base_dir, "generated_native")
    deploy_dir = os.path.join(local_gen_dir, f"{app_name}-deploy")

    os.makedirs(local_gen_dir, exist_ok=True)
    os.makedirs(native_gen_dir, exist_ok=True)
    os.makedirs(deploy_dir, exist_ok=True)
    os.makedirs("/tmp/appnet", exist_ok=True)

    GRAPH_BACKEND_LOG.info("Compiling elements for ambient. This might take a while...")
    # Compile wasm elements
    compile_wasm_elements(girs)

    # Copy the istio-proxy source code to the generated directory
    global generated_istio_proxy_path
    generated_istio_proxy_path = os.path.join(native_gen_dir, "istio_envoy")
    # Clone the istio-proxy repository

    if os.path.exists(generated_istio_proxy_path) == False:
        execute_local(
            [
                "git",
                "clone",
                # TODO: move to appnet-org in future
                "git@github.com:jokerwyt/istio-proxy.git",
                generated_istio_proxy_path,
            ]
        )

    # Remove the original appnet_filter (if exists)
    os.system(
        f"rm -rf {generated_istio_proxy_path}/source/extensions/filters/http/appnet_filter"
    )
    generate_native_element_image(girs)
    if native_not_empty:
        compile_native_image()


    with open(app_install_file, "r") as f:
        yml_list_istio = list(yaml.safe_load_all(f))
    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

    service_to_hostname = extract_service_pos(yml_list_istio)
    service_to_port_number = extract_service_port(yml_list_istio)
    service_to_label = extract_service_label(yml_list_istio)
    service_to_service_account = extract_service_account_mapping(yml_list_istio)

    # Extract the list of microservices
    services_all = list()
    for yml in yml_list_istio:
        if yml and "kind" in yml and yml["kind"] == "Service":
            services_all.append(yml["metadata"]["name"])
    services = list(
        filter(
            lambda s: "mongodb" not in s and "memcached" not in s and "jaeger" not in s,
            services_all,
        )
    )

    # Attach elements to the sidecar pods using volumes
    webdis_configs = []
    service_account_set = set()
    for gir in girs.values():
        if len(gir.elements["ambient"]) > 0:
            service_account_set.add(service_to_service_account[gir.server])
        for element in gir.elements["ambient"]:
            # If the element is stateful and requires strong consistency, deploy a webdis instance
            if (
                # hasattr(element, "_prop") and
                element.prop[  # The element has no property when no-optimize flag is set
                    "state"
                ][
                    "stateful"
                ]
                == True
                and element.prop["state"]["consistency"] in ["strong", "weak"]
            ):
                # Add webdis config
                webdis_service_copy, webdis_deploy_copy = deepcopy(
                    webdis_service
                ), deepcopy(webdis_deploy)
                webdis_service_copy["metadata"][
                    "name"
                ] = f"webdis-service-{element.lib_name}"
                webdis_deploy_copy["metadata"][
                    "name"
                ] = f"webdis-test-{element.lib_name}"
                # webdis_deploy_copy["spec"]["template"]["spec"].update(
                #     {"nodeName": service_to_hostname[sname]}
                # )
                webdis_configs.append(webdis_service_copy)
                webdis_configs.append(webdis_deploy_copy)

            # Copy the wasm binary to the remote hosts (except the control plane node)
            # We need to copy to all hosts because we don't know where the service will be scheduled
            nodes = get_node_names(control_plane=False)
            for node in nodes:
                copy_remote_host(
                    node, f"/tmp/appnet/{element.lib_name}.wasm", "/tmp/appnet"
                )

    # Dump the webdis file (somehow there is a None)
    webdis_configs = [wbs for wbs in webdis_configs if wbs is not None]
    if len(webdis_configs) > 0:
        with open(os.path.join(deploy_dir, "ambient-webdis.yml"), "w") as f:
            yaml.dump_all(webdis_configs, f, default_flow_style=False)

    yml_list_istio = [yml for yml in yml_list_istio if yml is not None]
    with open(app_install_file, "w") as f:
        yaml.dump_all(yml_list_istio, f, default_flow_style=False)

    # Generate script to attach elements.
    attach_all_yml = ""
    for gir in girs.values():
        for e in gir.elements["ambient"][::-1]:
            contents = {
                "metadata_name": f"{e.lib_name}-{gir.server}-ambient",
                "name": f"{e.lib_name}-ambient",
                "ename": e.lib_name,
                "service": service_to_service_account[gir.server],
                "bound": "ANY",
                "vmid": f"vm.sentinel.{e.lib_name}-ambient",
                "filename": f"/appnet/{e.lib_name}.wasm",
            }
            if "wasm" in e.target:
                attach_all_yml += attach_yml_ambient_wasm.format(**contents)
            elif "native" in e.target:
                attach_all_yml += attach_yml_ambient_native.format(**contents)
            else:
                raise ValueError(f"Unrecognized target: {e.target}")
    with open(os.path.join(deploy_dir, "ambient-attach.yml"), "w") as f:
        f.write(attach_all_yml)

    # Generate script to create and delete ambient waypoint proxies
    service_to_delete = [
        service
        for service, service_account in service_to_service_account.items()
        if service_account not in service_account_set
    ]
    for service in service_to_delete:
        del service_to_service_account[service]
    with open(os.path.join(deploy_dir, "waypoint_create.sh"), "w") as file:
        # Loop through each service name and write the corresponding shell command
        file.write("#!/bin/bash\n")
        file.write("kubectl label namespace default istio.io/dataplane-mode=ambient\n")
        for service, service_account in service_to_service_account.items():
            command = f"istioctl experimental waypoint apply -n default --name {service_account}-waypoint\n"
            command += f"kubectl label service {service} istio.io/use-waypoint={service_account}-waypoint --overwrite\n"
            file.write(command)

    with open(os.path.join(deploy_dir, "waypoint_delete.sh"), "w") as file:
        # Loop through each service name and write the corresponding shell command
        file.write("#!/bin/bash\n")
        for service_account in service_account_set:
            command = f"istioctl x waypoint delete {service_account}-waypoint\n"
            file.write(command)

    GRAPH_BACKEND_LOG.info(
        "Element compilation and manifest generation complete. The generated files are in the 'generated' directory."
    )
    GRAPH_BACKEND_LOG.info(
        f"To deploy the application and attach the elements, run kubectl apply -Rf {deploy_dir}"
    )
