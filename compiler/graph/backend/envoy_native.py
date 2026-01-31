from __future__ import annotations

import argparse
import os
from copy import deepcopy
from typing import Dict, List, Tuple
from compiler.graph.backend.imagehub import HUB_NAME

import yaml

from compiler import graph_base_dir
from compiler.config import COMPILER_ROOT
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import attach_yml_native
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_envoy_native(
    girs: Dict[str, GraphIR],
    app_name: str,
    app_manifest_file: str,
    app_edges: List[Tuple[str, str]],
    args: argparse.Namespace,
):
    global local_gen_dir
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    native_gen_dir = os.path.join(graph_base_dir, "generated_native")
    deploy_dir = os.path.join(local_gen_dir, f"{app_name}-deploy")

    os.makedirs(local_gen_dir, exist_ok=True)
    os.makedirs(native_gen_dir, exist_ok=True)
    os.makedirs(deploy_dir, exist_ok=True)

    # Change the owner of the generated directory to the current user
    # We use docker to compile the final Envoy, therefore some previous cache may be owned by root.
    # if os.geteuid() != 0:
    #     raise Exception("This script must be run as root")
    # os.system(f"sudo chown -R {os.getenv('USER')} {local_gen_dir}")

    # Copy the istio-proxy source code to the generated directory
    generated_istio_proxy_path = os.path.join(native_gen_dir, "istio_envoy")
    # Clone the istio-proxy repository

    if os.path.exists(generated_istio_proxy_path) == False:
        execute_local(
            [
                "git",
                "clone",
                # TODO: move to appnet-org in future
                # "git@github.com:jokerwyt/istio-proxy.git",
                "git@github.com:appnet-org/istio-proxy.git",
                generated_istio_proxy_path,
            ]
        )

    # Remove the original appnet_filter (if exists)
    os.system(f"rm -rf {generated_istio_proxy_path}/source/extensions/filters/http/appnet_filter")

    # Combining all elements into the istio Envoy template.
    inserted_elements = set()
    for gir in girs.values():
        for element in gir.elements["req_client"] + gir.elements["req_server"]:
            if element.lib_name not in inserted_elements:
                inserted_elements.add(element.lib_name)
                impl_dir = os.path.join(local_gen_dir, f"{element.lib_name}_envoy_native")

                filter_name = element.lib_name
                # Copy $impl_dir/appnet_filter to istio-proxy/source/extensions/filters/http/$filter_name
                # if exists, delete the old one
                if os.path.exists(
                    os.path.join(
                        generated_istio_proxy_path, "source/extensions/filters/http", filter_name
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
                        generated_istio_proxy_path, "source/extensions/filters/http", filter_name
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

                                if "#include" in line and (".pb.h" in line or ".pb.validate.h" in line):
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
                                line = line.replace("AppNetSampleFilter", f"appnet{filter_name}")
                                line = line.replace("appnetsamplefilter", f"appnet{filter_name}")

                                # Rule 3. webdis_cluster -> webdis-service-{filter_name}
                                line = line.replace("webdis_cluster", f"webdis-service-{filter_name}")

                                f.write(line)


    # Modify BUILD.
    # Checkout the BUILD fiel template first.
    # i.e. execute "git checkout origin/master -- source/extensions/filters/http/appnet_filter/BUILD" in that directory
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

    # Remove the original appnet_filter items in BUILD, and insert the new filters.
    # 
    # The template is in the following format:
    # ISTIO_EXTENSIONS = [
    #     "//source/extensions/common/workload_discovery:api_lib",  # Experimental: WIP
    #     "//source/extensions/filters/http/alpn:config_lib",
    #     "//source/extensions/filters/http/istio_stats",
    #     "//source/extensions/filters/http/peer_metadata:filter_lib",
    #     "//source/extensions/filters/network/metadata_exchange:config_lib",
    #     # !APPNET_FILTERS
    #     "//source/extensions/filters/http/appnet_filter:appnet_filter_lib",
    #     "//source/extensions/load_balancing_policies/random:random_lb_lib",
    # ]
    with open(ROOT_BUILD_FILE, "r") as f:
        lines = f.readlines()
    
    # Insert "//source/extensions/filters/http/${filter_name}:appnet_filter_lib", in the correct position
    insert_idx = 0
    for idx, line in enumerate(lines):
        if "# !APPNET_FILTERS\n" in line:
            insert_idx = idx
            break
    for element in inserted_elements:
        lines.insert(insert_idx, f'    "//source/extensions/filters/http/{element}:appnet_filter_config",\n')

    with open(ROOT_BUILD_FILE, "w") as f:
        f.writelines(lines)

    # Dirty hack for handmade filters.
    # Example.
    # APPNET_OVERWRITE_FILTERS=/mnt/appnet/compiler/compiler/graph/handmade_filters/servercachestrong
    # then we will copy the servercachestrong folder into {generated_istio_proxy_path}/source/extensions/filters/http/servercachestrong
    overwrite_from_env = os.getenv("APPNET_OVERWRITE_FILTERS")
    if overwrite_from_env is not None:
        # copy that file to the generated filter directory, overwriting the existing one.
        for handmade_filter_path in overwrite_from_env.split(","):
            folder_name = handmade_filter_path.split("/")[-1]

            # remove the original folder
            original_path = os.path.join(generated_istio_proxy_path, "source/extensions/filters/http", folder_name)
            os.system(
                f"rm -rf {original_path}"
            )

            execute_local(
                [
                    "cp",
                    "-r",
                    handmade_filter_path,
                    os.path.join(generated_istio_proxy_path, "source/extensions/filters/http", folder_name),
                ]
            )
            GRAPH_BACKEND_LOG.warn(f"Overwriting filter. dst {original_path}, src {handmade_filter_path}.")


    GRAPH_BACKEND_LOG.info(f"The istio envoy source code is generated successfully in {generated_istio_proxy_path}.")
    

    # Compile the istio envoy.

    image_name = f"{HUB_NAME}/proxyv2:1.22.3-distroless"
    if os.getenv("APPNET_NO_BAKE") != "1":
        GRAPH_BACKEND_LOG.info("Building the istio envoy...")
        execute_local(
            ["bash", "build.sh"], cwd=generated_istio_proxy_path,
        )
        # Bake the istio proxy image.
        GRAPH_BACKEND_LOG.info("Building the istio proxy image...")
        execute_local(
            ["docker", "build", "-t", f"{image_name}", "-f", "Dockerfile.istioproxy", "."],
            cwd=generated_istio_proxy_path,
        )
        GRAPH_BACKEND_LOG.info(f"Docker image {image_name} is built successfully.")

        # Push the image to the docker hub.
        GRAPH_BACKEND_LOG.info("Pushing the istio proxy image to the docker hub...")
        execute_local(["docker", "push", f"{image_name}"])
        GRAPH_BACKEND_LOG.info(f"Docker image {image_name} is pushed successfully.")
    else:
        GRAPH_BACKEND_LOG.info("Skip building and pushing the istio proxy image.")

    GRAPH_BACKEND_LOG.info("Injecting the istio proxy image to the application manifest file...")
    istio_injected_file = os.path.join(local_gen_dir, app_name + "_istio.yml")
    
    cmd=f"istioctl kube-inject -f {app_manifest_file} -o {istio_injected_file} --set values.global.proxy.image=docker.io/{image_name}"
    GRAPH_BACKEND_LOG.info(f"Executing command: {cmd}")
    # Generate the istio manifest file for the application.
    execute_local(
        [
            "istioctl",
            "kube-inject",
            "-f",
            app_manifest_file,
            "-o",
            os.path.join(local_gen_dir, app_name + "_istio.yml"),
        ]
    )

    # Use custom istio-proxy image in the generated manifest file
    with open(istio_injected_file, "r") as f:
        content = f.readlines()
        # replace
        # docker.io/istio/proxyv2:<version_number>
        # with 
        # docker.io/{image_name}
        for i, line in enumerate(content):
            if "docker.io/istio/proxyv2" in line:
                content[i] = line.split("docker.io/istio/proxyv2")[0] + f"{image_name}" + "\n"
    with open(istio_injected_file, "w") as f:
        f.writelines(content)

    # Set pull policy always
    with open(istio_injected_file, "r") as f:
        yml_list = list(yaml.safe_load_all(f))
        for obj_yml in yml_list:
            if obj_yml and "kind" in obj_yml and obj_yml["kind"] == "Deployment":
                for container_yaml in obj_yml["spec"]["template"]["spec"]["containers"] + obj_yml["spec"]["template"]["spec"]["initContainers"]:
                    # if the image is our custom image, set the pull policy to Always
                    if container_yaml["image"] == image_name:
                        container_yaml["imagePullPolicy"] = "Always"

    # Dump back
    with open(istio_injected_file, "w") as f:
        yaml.dump_all(yml_list, f, default_flow_style=False)
    GRAPH_BACKEND_LOG.info(f"The istio-injected file is generated successfully at {istio_injected_file}.")

    GRAPH_BACKEND_LOG.info("Generating the istio manifest file for the application...")
    with open(app_manifest_file, "r") as f:
        yml_list_plain = list(yaml.safe_load_all(f))

    service_to_hostname = extract_service_pos(yml_list_plain)
    service_to_port_number = extract_service_port(yml_list_plain)
    service_to_label = extract_service_label(yml_list_plain)

    with open(os.path.join(local_gen_dir, app_name + "_istio.yml"), "r") as f:
        yml_list_istio = list(yaml.safe_load_all(f))
    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

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
    with open(os.path.join(BACKEND_CONFIG_DIR, "volume_template.yml"), "r") as f:
        pv, pvc = list(yaml.safe_load_all(f))
    
    # Attach the version number config file
    for service in services:
        target_service_yml = find_target_yml(yml_list_istio, service)
        
        if "volumeMounts" not in target_service_yml["spec"]["template"]["spec"]["containers"][0]:
            target_service_yml["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []
        
        target_service_yml["spec"]["template"]["spec"]["containers"][0][
            "volumeMounts"
        ].append(
            {
                "mountPath": f"/etc/config-version",
                "name": f"config-version",
            }
        )
        target_service_yml["spec"]["template"]["spec"]["volumes"].append(
            {
                "hostPath": {
                    "path": f"/tmp/appnet/config-version",
                    "type": "File",
                },
                "name": f"config-version",
            }
        )
        
        pv_copy, pvc_copy = deepcopy(pv), deepcopy(pvc)
        pv_copy["metadata"]["name"] = f"{service}-pv"
        pv_copy["spec"]["hostPath"]["path"] = "/tmp/appnet"
        pvc_copy["metadata"]["name"] = f"{service}-pvc"
        pvc_copy["spec"]["volumeName"] = f"{service}-pv"
        yml_list_istio.append(pv_copy)
        yml_list_istio.append(pvc_copy)
        
        target_service_yml["spec"]["template"]["spec"]["containers"][1][
            "volumeMounts"
        ].append(
            {
                "mountPath": "/etc/appnet",
                "name": f"{service}-volume",
            }
        )
        
        target_service_yml["spec"]["template"]["spec"]["volumes"].append(
            {
                "persistentVolumeClaim": {"claimName": f"{service}-pvc"},
                "name": f"{service}-volume",
            }
        )

    whitelist_port, blacklist_port = {}, {}
    for sname in services_all:
        whitelist_port[(sname, "C")] = set()
        whitelist_port[(sname, "S")] = set()
        blacklist_port[(sname, "C")] = []
        blacklist_port[(sname, "S")] = []

    # Attach elements to the sidecar pods using volumes
    for gir in girs.values():
        elist = [(e, gir.client) for e in gir.elements["req_client"]] + [
            (e, gir.server) for e in gir.elements["req_server"]
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
                yml_list_istio.append(webdis_service_copy)
                yml_list_istio.append(webdis_deploy_copy)

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
    yml_list_istio = [yml for yml in yml_list_istio if yml is not None]
    with open(os.path.join(deploy_dir, "install.yml"), "w") as f:
        yaml.dump_all(yml_list_istio, f, default_flow_style=False)
    # TODO: we probably should just pipe the output of istioctl
    execute_local(["rm", os.path.join(local_gen_dir, app_name + "_istio.yml")])

    # Generate script to attach elements.
    attach_all_yml = ""
    for gir in girs.values():
        elist = [(e, gir.client, "client") for e in gir.elements["req_client"]] \
            + [(e, gir.server, "server") for e in gir.elements["req_server"]][::-1]
        
        for (e, sname, placement) in elist:
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
                "filename": f"/etc/appnet/{e.lib_name}.wasm",
                "service_label": service_to_label[sname],
            }
            attach_all_yml += attach_yml_native.format(**contents)
    with open(os.path.join(deploy_dir, "attach_all_elements.yml"), "w") as f:
        f.write(attach_all_yml)

    GRAPH_BACKEND_LOG.info(
        "Element compilation and manifest generation complete. The generated files are in the 'generated' directory."
    )
    GRAPH_BACKEND_LOG.info(
        f"To deploy the application and attach the elements, run kubectl apply -Rf {deploy_dir}"
    )
