from __future__ import annotations

import os
from copy import deepcopy
from typing import Dict, List, Tuple

import yaml

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import attach_yml_ambient
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_ambient(
    girs: Dict[str, GraphIR],
    app_name: str,
    app_manifest_file: str,
    app_edges: List[Tuple[str, str]],
):
    global local_gen_dir
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    os.makedirs(local_gen_dir, exist_ok=True)
    deploy_dir = os.path.join(local_gen_dir, f"{app_name}-deploy")
    os.makedirs(deploy_dir, exist_ok=True)
    os.makedirs("/tmp/appnet", exist_ok=True)

    # Compile each element
    GRAPH_BACKEND_LOG.info("Compiling elements for Ambient. This might take a while...")
    compiled_elements = set()
    for gir in girs.values():
        for element in gir.elements["req_client"] + gir.elements["req_server"]:
            if element.lib_name not in compiled_elements:
                compiled_elements.add(element.lib_name)
                impl_dir = os.path.join(local_gen_dir, f"{element.lib_name}_ambient")
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
                # copy binary to /tmp
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

    with open(app_manifest_file, "r") as f:
        yml_list = list(yaml.safe_load_all(f))

    service_to_hostname = extract_service_pos(yml_list)
    service_to_label = extract_service_label(yml_list)
    service_to_service_account = extract_service_account_mapping(yml_list)

    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

    with open(os.path.join(BACKEND_CONFIG_DIR, "volume_template.yml"), "r") as f:
        pv, pvc = list(yaml.safe_load_all(f))

    # Extract the list of microservices
    services_all = list()
    for yml in yml_list:
        if yml and "kind" in yml and yml["kind"] == "Service":
            services_all.append(yml["metadata"]["name"])
    services = list(
        filter(
            lambda s: "mongodb" not in s and "memcached" not in s and "jaeger" not in s,
            services_all,
        )
    )
    
    # Attach the version number config file
    for service in services:
        target_service_yml = find_target_yml(yml_list, service)
        
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
        
        if "volumes" not in target_service_yml["spec"]["template"]["spec"]:
            target_service_yml["spec"]["template"]["spec"]["volumes"] = []
        target_service_yml["spec"]["template"]["spec"]["volumes"].append(
            {
                "hostPath": {
                    "path": f"/tmp/appnet/config-version",
                    "type": "File",
                },
                "name": f"config-version",
            }
        )

    pv_service_set = set()
    service_account_set = set()
    for gir in girs.values():
        elist = [(e, gir.client) for e in gir.elements["req_client"]] + [
            (e, gir.server) for e in gir.elements["req_server"]
        ]
        for (element, sname) in elist:

            # Add pv and pvc for this service
            if sname not in pv_service_set:
                pv_service_set.add(sname)
                service_account_set.add(service_to_service_account[sname])
                pv_copy, pvc_copy = deepcopy(pv), deepcopy(pvc)
                pv_copy["metadata"]["name"] = f"{sname}-pv"
                pvc_copy["metadata"]["name"] = f"{sname}-pvc"
                pvc_copy["spec"]["volumeName"] = f"{sname}-pv"
                yml_list.append(pv_copy)
                yml_list.append(pvc_copy)

            # All ambient elements should be placed on the server-side
            assert sname != gir.client
            placement = "S"

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
                yml_list.append(webdis_service_copy)
                yml_list.append(webdis_deploy_copy)

            # Copy the wasm binary to the remote hosts (except the control plane node)
            # We need to copy to all hosts because we don't know where the service will be scheduled
            nodes = get_node_names(control_plane=False)
            for node in nodes:
                copy_remote_host(
                    node, f"/tmp/appnet/{element.lib_name}.wasm", "/tmp/appnet"
                )

    # Dump the final manifest file (somehow there is a None)
    yml_list = [yml for yml in yml_list if yml is not None]
    with open(os.path.join(deploy_dir, "install.yml"), "w") as f:
        yaml.dump_all(yml_list, f, default_flow_style=False)

    # Generate script to attach elements.
    attach_all_yml = ""
    for gir in girs.values():
        elist = [(e, gir.client, "client") for e in gir.elements["req_client"]] + [
            (e, gir.server, "server") for e in gir.elements["req_server"]
        ]
        for (e, sname, placement) in elist:
            contents = {
                "metadata_name": f"{e.lib_name}-{sname}-{placement}",
                "name": f"{e.lib_name}-{placement}",
                "ename": e.lib_name,
                "service": service_to_service_account[sname],
                "bound": "ANY",
                "vmid": f"vm.sentinel.{e.lib_name}-{placement}",
                "filename": f"/data/{e.lib_name}.wasm",
                "service_label": service_to_label[sname],
            }
            attach_all_yml += attach_yml_ambient.format(**contents)
    with open(os.path.join(deploy_dir, "attach_all_elements.yml"), "w") as f:
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
