from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Set, Tuple

from compiler import graph_base_dir
from compiler.graph.backend.boilerplate import arpc_go_mod, arpc_go_sum
from compiler.graph.backend.utils import (
    copy_remote_host,
    execute_local,
    execute_remote_host,
    get_node_names,
)
from compiler.graph.ir import GraphIR
from compiler.graph.ir.element import AbsElement
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_arpc(
    girs: Dict[str, GraphIR],
    app_name: str,
    _app_install_file: str,
    _app_edges: List[Tuple[str, str]],
):
    """
    Generate deployment scripts for aRPC elements.

    Args:
        girs: A dictionary mapping edge name to corresponding GraphIR.
        app_name: The name of the application (for naming).
        _app_install_file: The path to the application install file.
        _app_edges: The communication edges of the application.
    """
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    os.makedirs(local_gen_dir, exist_ok=True)
    deploy_dir = os.path.join(local_gen_dir, f"{app_name}-deploy")
    os.makedirs(deploy_dir, exist_ok=True)

    GRAPH_BACKEND_LOG.info("Compiling elements for aRPC. This might take a while...")

    # Collect arpc elements from sidecar positions
    client_elements: Dict[str, Set[AbsElement]] = {}  # service -> set of elements
    server_elements: Dict[str, Set[AbsElement]] = {}  # service -> set of elements

    for gir in girs.values():
        # Filter arpc elements from sidecar lists
        client_arpc = [e for e in gir.elements["client_sidecar"] if "arpc" in e.target]
        server_arpc = [e for e in gir.elements["server_sidecar"] if "arpc" in e.target]

        for element in client_arpc:
            if gir.client not in client_elements:
                client_elements[gir.client] = set()
            client_elements[gir.client].add(element)

        for element in server_arpc:
            if gir.server not in server_elements:
                server_elements[gir.server] = set()
            server_elements[gir.server].add(element)

    # Get all services that need arpc elements
    services = set(list(client_elements.keys()) + list(server_elements.keys()))

    for service in services:
        service_dir = os.path.join(deploy_dir, f"{service}-arpc")
        os.makedirs(service_dir, exist_ok=True)

        # Collect all elements for this service
        service_elements = (client_elements.get(service) or set()).union(
            server_elements.get(service) or set()
        )

        # Copy generated element implementations
        for element in service_elements:
            source_path = os.path.join(local_gen_dir, element.compile_dir, "element.go")
            dest_path = os.path.join(service_dir, f"{element.lib_name}.go")
            if os.path.exists(source_path):
                execute_local(["cp", source_path, dest_path])
                os.system(f"goimports -w {dest_path}")
                GRAPH_BACKEND_LOG.debug(f"Copied {element.lib_name} to {service_dir}")

        # Generate go.mod, go.sum for the service
        timestamp = str(datetime.now().strftime("%Y%m%d%H%M%S"))
        service_name = service + timestamp

        # Collect proto module replace directives from elements
        extra_replaces = []
        for element in service_elements:
            if element.proto_mod_name and element.proto_mod_location:
                # Strip trailing subpackage (e.g., /symphony) to get the module root
                mod_name = element.proto_mod_name
                mod_location = element.proto_mod_location
                # The replace should be at the module level, not subpackage
                # e.g., github.com/appnet-org/arpc/benchmark/kv-store-symphony-element
                # not github.com/appnet-org/arpc/benchmark/kv-store-symphony-element/symphony
                if mod_name.endswith("/symphony"):
                    mod_name = mod_name[:-9]  # strip /symphony
                    mod_location = mod_location[:-9]
                replace_line = f"replace {mod_name} => {mod_location}"
                if replace_line not in extra_replaces:
                    extra_replaces.append(replace_line)
        
        extra_replaces_str = "\n".join(extra_replaces)
        if extra_replaces_str:
            extra_replaces_str = extra_replaces_str + "\n"

        with open(f"{service_dir}/go.mod", "w") as f:
            f.write(arpc_go_mod.format(ServiceName=service_name, ExtraReplaces=extra_replaces_str))
        with open(f"{service_dir}/go.sum", "w") as f:
            f.write(arpc_go_sum)

        # Run go mod tidy to resolve dependencies
        execute_local(["go", "mod", "tidy", "-C", service_dir])

        # Build each element as a plugin
        for element in service_elements:
            element_file = f"{element.lib_name}.go"
            # plugin_name = f"{element.lib_name}_{timestamp}"
            plugin_name = f"element-{timestamp}"

            execute_local(
                [
                    "go",
                    "build",
                    "-C",
                    service_dir,
                    "-o",
                    plugin_name,
                    "-buildmode=plugin",
                    "-trimpath",
                    element_file,
                ],
                env={"CGO_ENABLED": "1"},
            )

            # Copy to local interceptors directory
            execute_local(["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
            execute_local(
                [
                    "cp",
                    os.path.join(service_dir, plugin_name),
                    "/tmp/appnet/arpc-plugins",
                ]
            )

            GRAPH_BACKEND_LOG.debug(f"Built aRPC plugin: {plugin_name}")

        # Copy to all nodes
        nodes = get_node_names(control_plane=False)
        for node in nodes:
            execute_remote_host(node, ["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
            for element in service_elements:
                # plugin_name = f"{element.lib_name}_{timestamp}"
                plugin_name = f"element-{timestamp}"
                copy_remote_host(
                    node,
                    f"/tmp/appnet/arpc-plugins/{plugin_name}",
                    "/tmp/appnet/arpc-plugins",
                )

    GRAPH_BACKEND_LOG.info(
        "aRPC compilation complete. The generated elements are deployed."
    )

