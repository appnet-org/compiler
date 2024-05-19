from __future__ import annotations

from datetime import datetime
from itertools import groupby
from operator import attrgetter
import os
from copy import deepcopy
from typing import Dict, List, Tuple

import yaml

from compiler import graph_base_dir
from compiler.element.backend.grpc.gotype import GoGlobalFunctions
from compiler.element.frontend.util import extract_proto_package_name, extract_proto_service_name
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import *
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.ir.element import AbsElement
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_grpc(
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

    GRAPH_BACKEND_LOG.info("Compiling elements for gRPC. This might take a while...")

    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))
    webdis_yml_list = []

    # Map elements to the applications they will be injected into
    client_elements: Dict[str, set[AbsElement]] = {}
    server_elements: Dict[str, set[AbsElement]] = {}
    for gir in girs.values():
        for element in gir.elements["req_client"] + gir.elements["req_server"]:
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
                webdis_yml_list.append(webdis_service_copy)
                webdis_yml_list.append(webdis_deploy_copy)
        # assuming req_client/res_client and req_server/res_server contain same elements
        for element in gir.elements["req_client"]:
            try:
                client_elements[gir.client].add(element)
            except KeyError:
                client_elements[gir.client] = {element}
        for element in gir.elements["req_server"]:
            try:
                server_elements[gir.server].add(element)
            except KeyError:
                server_elements[gir.server] = {element}

    # Produce the manifest file with webdis instances
    webdis_yml_list = [yml for yml in webdis_yml_list if yml is not None]

    # Service as in application not proto service
    services = set(list(client_elements.keys()) + list(server_elements.keys()))
    for service in services:        
        service_dir = os.path.join(deploy_dir, service)
        os.makedirs(service_dir, exist_ok=True)

        proto_modules = {} # dict protomodulename => protomodulelocation

        # Copy element implementations to appropriate service directory before compilation
        service_elements = (client_elements.get(service) or set()).union(server_elements.get(service) or set())
        for element in service_elements:
            execute_local(
                [
                    "cp",
                    os.path.join(local_gen_dir, f"{element.lib_name}_grpc", "interceptor.go"),
                    os.path.join(service_dir, f"{element.lib_name}.go"),
                ]
            )
            source_path = os.path.join(service_dir, f"{element.lib_name}.go")
            os.system(f"goimports -w {source_path}")
            proto_modules[element.proto_mod_name] = element.proto_mod_location

        proto_module_requires = "  \n".join(f"{name} v0.0.0-00010101000000-000000000000" for name in proto_modules.keys())
        proto_module_replaces = "\n".join(f"replace {name} => {loc}" for name, loc in proto_modules.items())
        
        # Generate server and client interceptor for each service, with match on rpc method
        init_fields = { "ClientMethodInterceptors": "",
                        "ServerMethodInterceptors": "",
                        "ClientMethodMatches": "",
                        "ServerMethodMatches": "",
                         "GlobalFuncDef": ";".join([f.definition for f in GoGlobalFunctions.values()]) }

        for method, els in groupby(sorted(client_elements.get(service) or {}, key=attrgetter('method')), attrgetter('method')):
            init_fields["ClientMethodInterceptors"] += f"var {method}_interceptor grpc.UnaryClientInterceptor\n"
            elements = list(els)
            full_method_name = extract_full_method_name(elements)
            interceptor_list = ", ".join(f"{element.lib_name}ClientInterceptor()" for element in elements)
            method_match = client_method_match.format(MethodName = method, FullMethodName = full_method_name, InterceptorList = interceptor_list)
            init_fields["ClientMethodMatches"] += method_match

        for method, els in groupby(sorted(server_elements.get(service) or {}, key=attrgetter('method')), attrgetter('method')):
            init_fields["ServerMethodInterceptors"] += f"var {method}_interceptor grpc.UnaryServerInterceptor\n"
            elements = list(els)
            full_method_name = extract_full_method_name(elements)
            interceptor_list = ", ".join(f"{element.lib_name}ServerInterceptor()" for element in elements) 
            method_match = server_method_match.format(MethodName = method, FullMethodName = full_method_name, InterceptorList = interceptor_list)
            init_fields["ServerMethodMatches"] += method_match

        timestamp = str(datetime.now().strftime("%Y%m%d%H%M%S")) # append timestamp to module so Go knows they are different plugins
        with open(f"{service_dir}/go.mod", "w") as f:
            f.write(go_mod.format(ServiceName = service + timestamp, ProtoModuleRequires = proto_module_requires, ProtoModuleReplaces = proto_module_replaces))
        with open(f"{service_dir}/go.sum", "w") as f:
            f.write(go_sum.format())
        with open(f"{service_dir}/interceptinit.go", "w") as f:
            f.write(intercept_init.format(**init_fields))
        os.system(f"goimports -w {service_dir}/interceptinit.go")

        # Compile
        execute_local(
            [
                "go",
                "build",
                "-C",
                service_dir,
                "-o",
                f"{service + timestamp}",
                "-buildmode=plugin",
                ".",
            ]
        )

        execute_local(["mkdir", "-p", "/tmp/appnet/interceptors"])
        execute_local(
            [
                "cp",
                os.path.join(
                    service_dir,
                    f"{service + timestamp}",
                ),
                "/tmp/appnet/interceptors",
            ]
        )

        # Create and attach pv/pvcs for services
        webdis_yml_list.extend(attach_volumes(app_manifest_file, deploy_dir))
        # Dump the final manifest file (somehow there is a None)
        yml_list = [yml for yml in webdis_yml_list if yml is not None]
        with open(os.path.join(deploy_dir, "install.yml"), "w") as f:
            yaml.dump_all(yml_list, f, default_flow_style=False)
        
        # Copy to all nodes
        nodes = get_node_names(control_plane=False)
        for node in nodes:
            execute_remote_host(node, ["mkdir", "-p", "/tmp/appnet/interceptors"])
            copy_remote_host(node, f"/tmp/appnet/interceptors/{service + timestamp}", "/tmp/appnet/interceptors")

    GRAPH_BACKEND_LOG.info(
        "Element compilation complete. The generated element is deployed."
    )

# Extracts full method name from elements who all share same method
def extract_full_method_name(elements: list[AbsElement]) -> str:
    first_el = elements[0]
    assert all(e.proto == first_el.proto for e in elements), "Unsupported: same application has identical method names in different proto services"
    proto = first_el.proto
    package_name = extract_proto_package_name(proto)
    service_name = extract_proto_service_name(proto)
    return f"/{package_name}.{service_name}/{first_el.method}"


def attach_volumes(app_manifest_file: str, deploy_dir: str) -> list[any]:
    
    with open(app_manifest_file, "r") as f:
        yml_list = list(yaml.safe_load_all(f))
        
    # Find all services
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
    
    # Load pv and pvc template
    with open(os.path.join(BACKEND_CONFIG_DIR, "volume_template.yml"), "r") as f:
        pv, pvc = list(yaml.safe_load_all(f))
    
    # Create and attach volume
    for service in services:
        pv_copy, pvc_copy = deepcopy(pv), deepcopy(pvc)
        pv_copy["metadata"]["name"] = f"{service}-interceptor-pv"
        pv_copy["spec"]["hostPath"]["path"] = "/tmp/appnet/interceptors"
        pvc_copy["metadata"]["name"] = f"{service}-interceptor-pvc"
        pvc_copy["spec"]["volumeName"] = f"{service}-interceptor-pv"
        yml_list.append(pv_copy)
        yml_list.append(pvc_copy)
        
        # Find the corresponding service in the manifest
        target_service_yml = find_target_yml(yml_list, service)

        # Attach the element to the sidecar using volumes
        if "volumes" not in target_service_yml["spec"]["template"]["spec"]:
            target_service_yml["spec"]["template"]["spec"]["volumes"] = []
        
        if "volumeMounts" not in target_service_yml["spec"]["template"]["spec"]["containers"][0]:
            target_service_yml["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = []
        
        target_service_yml["spec"]["template"]["spec"]["containers"][0][
                "volumeMounts"
            ].append(
                {
                    "mountPath": "/interceptors",
                    "name": f"{service}-interceptor-volume",
                }
            )
        target_service_yml["spec"]["template"]["spec"]["volumes"].append(
            {
                "persistentVolumeClaim": {
                    "claimName": f"{service}-interceptor-pvc"
                },
                "name": f"{service}-interceptor-volume",
            }
        )

    return yml_list
