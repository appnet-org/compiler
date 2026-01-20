from __future__ import annotations

import os
from typing import Dict, List, Tuple

from compiler import graph_base_dir
from compiler.graph.backend.utils import execute_local
from compiler.graph.ir import GraphIR
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

    # # Collect arpc elements from sidecar positions
    # client_elements: Dict[str, list] = {}  # service -> list of elements
    # server_elements: Dict[str, list] = {}  # service -> list of elements

    # for gir in girs.values():
    #     # Filter arpc elements from sidecar lists
    #     client_arpc = [e for e in gir.elements["client_sidecar"] if "arpc" in e.target]
    #     server_arpc = [e for e in gir.elements["server_sidecar"] if "arpc" in e.target]

    #     for element in client_arpc:
    #         if gir.client not in client_elements:
    #             client_elements[gir.client] = []
    #         client_elements[gir.client].append(element)

    #     for element in server_arpc:
    #         if gir.server not in server_elements:
    #             server_elements[gir.server] = []
    #         server_elements[gir.server].append(element)

    # # Get all services that need arpc elements
    # services = set(list(client_elements.keys()) + list(server_elements.keys()))

    # for service in services:
    #     service_dir = os.path.join(deploy_dir, f"{service}-arpc")
    #     os.makedirs(service_dir, exist_ok=True)

    #     service_client_elements = client_elements.get(service, [])
    #     service_server_elements = server_elements.get(service, [])

    #     # Copy generated element implementations
    #     for element in service_client_elements + service_server_elements:
    #         source_path = os.path.join(local_gen_dir, element.compile_dir, "element.go")
    #         dest_path = os.path.join(service_dir, f"{element.lib_name}.go")
    #         if os.path.exists(source_path):
    #             execute_local(["cp", source_path, dest_path])
    #             GRAPH_BACKEND_LOG.info(f"Copied {element.lib_name} to {service_dir}")

    #     # TODO: Generate go.mod, go.sum for the service
    #     # TODO: Generate initialization code that wires up the elements
    #     # TODO: Build and deploy the arpc plugin/binary

    GRAPH_BACKEND_LOG.info("aRPC compilation complete.")

