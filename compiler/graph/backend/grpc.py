from __future__ import annotations

from itertools import groupby
import json
from operator import attrgetter
import os
from copy import deepcopy
from pprint import pprint
from typing import Dict, Iterator, List, Tuple

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

    GRAPH_BACKEND_LOG.info("Compiling elements for GRPC. This might take a while...")

    # Map elements to the applications they will be injected into
    client_elements: Dict[str, set[AbsElement]] = {}
    server_elements: Dict[str, set[AbsElement]] = {}
    for gir in girs.values():
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
            os.system(f"goimports -w {os.path.join(service_dir, f"{element.lib_name}.go")}")
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

        with open(f"{service_dir}/go.mod", "w") as f:
            f.write(go_mod.format(ServiceName = service, ProtoModuleRequires = proto_module_requires, ProtoModuleReplaces = proto_module_replaces))
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
                f"{service}",
                "-buildmode=plugin",
                ".",
            ]
        )

        execute_local(
            [
                "cp",
                os.path.join(
                    service_dir,
                    f"{service}",
                ),
                "/tmp/interceptors",
            ]
        )

        # Copy to all nodes
        nodes = get_node_names(control_plane=False)
        for node in nodes:
            copy_remote_host(node, f"/tmp/interceptors/{service}", "/tmp/interceptors")
        

        # for element in gir.elements["req_client"] + gir.elements["req_server"]:
        #     if element.lib_name not in compiled_elements:
        #         compiled_elements.add(element.lib_name)
        #         impl_dir = os.path.join(local_gen_dir, f"{element.lib_name}_grpc")
        #         # Compile
        #         execute_local(
        #             [
        #                 "go",
        #                 "build",
        #                 "-C",
        #                 impl_dir,
        #                 "-o",
        #                 f"{element.lib_name}.so",
        #                 "-buildmode=plugin",
        #                 ".",
        #             ]
        #         )
        #         # copy binary to /tmp
        #         execute_local(
        #             [
        #                 "cp",
        #                 os.path.join(
        #                     impl_dir,
        #                     f"{element.lib_name}.so",
        #                 ),
        #                 "/tmp",
        #             ]
        #         )

    # Attach elements to the sidecar pods using volumes
    # for gir in girs.values():
    #     elist = [(e, gir.client) for e in gir.elements["req_client"]] + [
    #         (e, gir.server) for e in gir.elements["req_server"]
    #     ]
    #     for (element, sname) in elist:
    #         placement = "C" if sname == gir.client else "S"

    #         # Copy the interceptor plugin to the remote hosts (except the control plane node)
    #         # We need to copy to all hosts because we don't know where the service will be scheduled
    #         nodes = get_node_names(control_plane=False)
    #         for node in nodes:
    #             copy_remote_host(node, f"/tmp/{element.lib_name}.so", "/tmp/")

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
