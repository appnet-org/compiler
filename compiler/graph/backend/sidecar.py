from __future__ import annotations

import json
import os
from copy import deepcopy
from pprint import pprint
from typing import Dict, List, Tuple

import yaml

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import attach_yml, attach_yml_native
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def compile_wasm_elements(girs: Dict[str, GraphIR]):
    global wasm_not_empty
    wasm_not_empty = False
    compiled_elements = set()
    for gir in girs.values():
        for element in gir.elements["client_sidecar"] + gir.elements["server_sidecar"]:
            if (
                element.lib_name not in compiled_elements
                and element.target == "sidecar_wasm"
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
        for element in gir.elements["client_sidecar"] + gir.elements["server_sidecar"]:
            if (
                element.lib_name not in inserted_elements
                and element.target == "sidecar_native"
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
    native_image_name = f"appnetorg/istio-proxy-1.22-sidecar:latest"
    if os.getenv("APPNET_NO_BAKE") != "1":
        GRAPH_BACKEND_LOG.info("Building the istio sidecar...")
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
                f"docker.io/{native_image_name}",
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
        execute_local(["docker", "push", f"docker.io/{native_image_name}"])
        GRAPH_BACKEND_LOG.info(
            f"Docker image {native_image_name} is pushed successfully."
        )
    else:
        GRAPH_BACKEND_LOG.info("Skip building and pushing the istio proxy image.")


def scriptgen_sidecar(
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

    GRAPH_BACKEND_LOG.info("Compiling elements for sidecar. This might take a while...")
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

    # for file_or_dir in os.listdir(app_manifest_dir):
    #     if app_name not in file_or_dir:
    #         execute_local(
    #             [
    #                 "cp",
    #                 "-r",
    #                 os.path.join(app_manifest_dir, file_or_dir),
    #                 os.path.join(deploy_dir, file_or_dir),
    #             ]
    #         )

    # Generate the istio manifest file for the application.
    GRAPH_BACKEND_LOG.info("Generating the istio manifest file for the application...")
    istio_injected_file = os.path.join(local_gen_dir, app_name + "_istio.yml")
    execute_local(
        [
            "istioctl",
            "kube-inject",
            "-f",
            app_install_file,
            "-o",
            istio_injected_file,
        ]
    )
    if native_not_empty:
        # Use custom istio-proxy-sidecar image in the generated manifest file
        with open(istio_injected_file, "r") as f:
            content = f.readlines()
            # replace
            # docker.io/istio/proxyv2:<version_number>
            # with
            # docker.io/{image_name}
            for i, line in enumerate(content):
                if "docker.io/istio/proxyv2" in line:
                    content[i] = (
                        line.split("docker.io/istio/proxyv2")[0]
                        + f"docker.io/{native_image_name}"
                        + "\n"
                    )
        with open(istio_injected_file, "w") as f:
            f.writelines(content)

        # Set pull policy always
        with open(istio_injected_file, "r") as f:
            yml_list = list(yaml.safe_load_all(f))
            for obj_yml in yml_list:
                if obj_yml and "kind" in obj_yml and obj_yml["kind"] == "Deployment":
                    for container_yaml in (
                        obj_yml["spec"]["template"]["spec"]["containers"]
                        + obj_yml["spec"]["template"]["spec"]["initContainers"]
                    ):
                        # if the image is our custom image, set the pull policy to Always
                        if container_yaml["image"] == f"docker.io/{native_image_name}":
                            container_yaml["imagePullPolicy"] = "Always"
        with open(istio_injected_file, "w") as f:
            yaml.dump_all(yml_list, f, default_flow_style=False)
    GRAPH_BACKEND_LOG.info(
        f"The istio-injected file is generated successfully at {istio_injected_file}."
    )

    with open(istio_injected_file, "r") as f:
        yml_list_istio = list(yaml.safe_load_all(f))
    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

    service_to_hostname = extract_service_pos(yml_list_istio)
    service_to_port_number = extract_service_port(yml_list_istio)
    service_to_label = extract_service_label(yml_list_istio)

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

    # Load pv and pvc template
    # with open(os.path.join(BACKEND_CONFIG_DIR, "volume_template.yml"), "r") as f:
    #     pv, pvc = list(yaml.safe_load_all(f))

    # Attach the version number config file
    # for service in services:
    #     target_service_yml = find_target_yml(yml_list_istio, service)

    #     if "volumeMounts" not in target_service_yml["spec"]["template"]["spec"]["containers"][0]:
    #         target_service_yml["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []

    #     target_service_yml["spec"]["template"]["spec"]["containers"][0][
    #         "volumeMounts"
    #     ].append(
    #         {
    #             "mountPath": f"/etc/config-version",
    #             "name": f"config-version",
    #         }
    #     )
    #     target_service_yml["spec"]["template"]["spec"]["volumes"].append(
    #         {
    #             "hostPath": {
    #                 "path": f"/tmp/appnet/config-version",
    #                 "type": "File",
    #             },
    #             "name": f"config-version",
    #         }
    #     )

    #     pv_copy, pvc_copy = deepcopy(pv), deepcopy(pvc)
    #     pv_copy["metadata"]["name"] = f"{service}-pv"
    #     pv_copy["spec"]["hostPath"]["path"] = "/tmp/appnet"
    #     pvc_copy["metadata"]["name"] = f"{service}-pvc"
    #     pvc_copy["spec"]["volumeName"] = f"{service}-pv"
    #     yml_list_istio.append(pv_copy)
    #     yml_list_istio.append(pvc_copy)

    #     target_service_yml["spec"]["template"]["spec"]["containers"][1][
    #         "volumeMounts"
    #     ].append(
    #         {
    #             "mountPath": "/etc/appnet",
    #             "name": f"{service}-volume",
    #         }
    #     )

    #     target_service_yml["spec"]["template"]["spec"]["volumes"].append(
    #         {
    #             "persistentVolumeClaim": {"claimName": f"{service}-pvc"},
    #             "name": f"{service}-volume",
    #         }
    #     )

    whitelist_port, blacklist_port = {}, {}
    for sname in services_all:
        whitelist_port[(sname, "C")] = set()
        whitelist_port[(sname, "S")] = set()
        blacklist_port[(sname, "C")] = []
        blacklist_port[(sname, "S")] = []

    # Attach elements to the sidecar pods using volumes
    webdis_configs = []
    for gir in girs.values():
        elist = [(e, gir.client) for e in gir.elements["client_sidecar"]] + [
            (e, gir.server) for e in gir.elements["server_sidecar"]
        ]
        for (element, sname) in elist:
            placement = "C" if sname == gir.client else "S"
            whitelist_port[(sname, placement)].add(service_to_port_number[gir.server])

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
                webdis_deploy_copy["spec"]["template"]["spec"].update(
                    {"nodeName": service_to_hostname[sname]}
                )
                webdis_configs.append(webdis_service_copy)
                webdis_configs.append(webdis_deploy_copy)

            # Copy the wasm binary to the remote hosts (except the control plane node)
            # We need to copy to all hosts because we don't know where the service will be scheduled
            nodes = get_node_names(control_plane=False)
            for node in nodes:
                copy_remote_host(
                    node, f"/tmp/appnet/{element.lib_name}.wasm", "/tmp/appnet"
                )

    if os.getenv("APPNET_NO_OPTIMIZE") != "1":
        # has optimization: exclude ports that has no element attached to
        for client, server in app_edges:
            port_number = service_to_port_number[server]
            if port_number not in whitelist_port[(client, "C")]:
                blacklist_port[(client, "C")].append(port_number)
            if port_number not in whitelist_port[(server, "S")]:
                blacklist_port[(server, "S")].append(port_number)
        # bypass frontend ingress sidecar
        if "frontend" in services:
            blacklist_port[("frontend", "S")].append(service_to_port_number["frontend"])
        for (sname, placement), portlist in blacklist_port.items():
            if portlist != []:
                annotation_name = (
                    "traffic.sidecar.istio.io/excludeOutboundPorts"
                    if placement == "C"
                    else "traffic.sidecar.istio.io/excludeInboundPorts"
                )
                target_service_yml = find_target_yml(yml_list_istio, sname)
                target_service_yml["spec"]["template"]["metadata"][
                    "annotations"
                ].update({annotation_name: ",".join(portlist)})
    else:
        # no optimization: keep everything unchanged so that no sidecar will be bypassed
        # TODO: bypass frontend ingress sidecar for ping-pong-app
        pass

    # if os.getenv("APPNET_NO_OPTIMIZE") != "1":
    #     # has optimization: add whitelist annotations, ports not included in whitelist will be bypassed
    #     for (sname, placement), portset in whitelist_port.items():
    #         annotation_name = "traffic.sidecar.istio.io/includeOutboundPorts" if placement == "C" else "traffic.sidecar.istio.io/includeInboundPorts"
    #         target_service_yml = find_target_yml(yml_list_istio, sname)
    #         target_service_yml["spec"]["template"]["metadata"]["annotations"].update({
    #             # annotation_name: ','.join(list(portset))
    #             annotation_name: ''
    #         })
    # else:
    #     # no optimization: keep everything unchanged so that no sidecar will be bypassed
    #     pass

    # Adjust replica count
    replica = os.getenv("SERVICE_REPLICA")
    if replica is not None:
        for sname in services:
            target_yml = find_target_yml(yml_list_istio, sname)
            target_yml["spec"]["replicas"] = int(replica)

    # Dump the final manifest file (somehow there is a None)
    webdis_configs = [wbs for wbs in webdis_configs if wbs is not None]
    if len(webdis_configs) > 0:
        with open(os.path.join(deploy_dir, "sidecar-webdis.yml"), "w") as f:
            yaml.dump_all(webdis_configs, f, default_flow_style=False)

    yml_list_istio = [yml for yml in yml_list_istio if yml is not None]
    with open(app_install_file, "w") as f:
        yaml.dump_all(yml_list_istio, f, default_flow_style=False)
    # TODO: we probably should just pipe the output of istioctl
    execute_local(["rm", istio_injected_file])

    # Generate script to attach elements.
    attach_all_yml = ""
    for gir in girs.values():
        elist = [
            (e, gir.client, "client", e.target) for e in gir.elements["client_sidecar"]
        ] + [
            (e, gir.server, "server", e.target) for e in gir.elements["server_sidecar"]
        ]
        for (e, sname, placement, target) in elist:
            contents = {
                "metadata_name": f"{e.lib_name}-{sname}-{placement}",
                "name": f"{e.lib_name}-{placement}",
                "ename": e.lib_name,
                "service": sname,
                "bound": "SIDECAR_OUTBOUND"
                if placement == "client"
                else "SIDECAR_INBOUND",
                "port": service_to_port_number[gir.server],
                "vmid": f"vm.sentinel.{e.lib_name}-{placement}",
                "filename": f"/appnet/{e.lib_name}.wasm",
                "service_label": service_to_label[sname],
            }
            if "wasm" in target:
                attach_all_yml += attach_yml.format(**contents)
            elif "native" in target:
                attach_all_yml += attach_yml_native.format(**contents)
            else:
                raise ValueError(f"Unrecognized target: {target}")
    with open(os.path.join(deploy_dir, "sidecar-attach.yml"), "w") as f:
        f.write(attach_all_yml)

    GRAPH_BACKEND_LOG.info(
        "Element compilation and manifest generation complete. The generated files are in the 'generated' directory."
    )
    GRAPH_BACKEND_LOG.info(
        f"To deploy the application and attach the elements, run kubectl apply -Rf {deploy_dir}"
    )
