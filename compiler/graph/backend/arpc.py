from __future__ import annotations

import argparse
import os
from datetime import datetime
from typing import Dict, List, Set, Tuple

import yaml

from compiler import graph_base_dir
from compiler.graph.backend.utils import (
    copy_remote_host,
    execute_local,
    execute_remote_host,
    get_node_names,
)
from compiler.graph.ir import GraphIR
from compiler.graph.ir.element import AbsElement
from compiler.graph.logger import GRAPH_BACKEND_LOG

# Path to the arpc proxy module - plugins MUST be built from here
# to ensure they use the exact same package versions as the proxy binary
username = os.getenv("USER")

ARPC_PROXY_DIR = f"/users/{username}/arpc/cmd/proxy"


def add_element_plugin_prefix_to_symphony_proxies(app_manifest_file: str) -> None:
    """
    Read the application yaml file and for each symphony proxy container,
    add an env variable ELEMENT_PLUGIN_PREFIX set to the service name.

    Args:
        app_manifest_file: The path to the application manifest file.
    """
    # Load application manifest
    with open(app_manifest_file, "r") as f:
        yml_list = list(yaml.safe_load_all(f))

    # Process each YAML document
    for yml in yml_list:
        if yml and yml.get("kind") == "Deployment":
            deployment_name = yml["metadata"]["name"]
            containers = yml["spec"]["template"]["spec"].get("containers", [])

            # Find symphony proxy containers
            for container in containers:
                if container.get("name") == "symphony-proxy":
                    # Initialize env list if it doesn't exist
                    if "env" not in container:
                        container["env"] = []

                    # Check if ELEMENT_PLUGIN_PREFIX already exists
                    env_exists = any(
                        env_var.get("name") == "ELEMENT_PLUGIN_PREFIX"
                        for env_var in container["env"]
                    )

                    if not env_exists:
                        # Add the environment variable
                        container["env"].append(
                            {
                                "name": "ELEMENT_PLUGIN_PREFIX",
                                "value": deployment_name,
                            }
                        )
                        GRAPH_BACKEND_LOG.debug(
                            f"Added ELEMENT_PLUGIN_PREFIX={deployment_name} to symphony-proxy container in deployment {deployment_name}"
                        )

    # Write the modified YAML back to the file
    with open(app_manifest_file, "w") as f:
        yaml.dump_all(yml_list, f, default_flow_style=False)


def scriptgen_arpc(
    girs: Dict[str, GraphIR],
    app_name: str,
    _app_install_file: str,
    _app_edges: List[Tuple[str, str]],
    args: argparse.Namespace,
):
    global ARPC_PROXY_DIR
    if os.getenv("ARPC_PROXY_DIR") is not None:
        ARPC_PROXY_DIR = os.getenv("ARPC_PROXY_DIR")
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

    # TODO: same element on different edges (client -> server1, client -> server2) should be separately compiled, as the serialization stub can differ.
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

    for gir in girs.values():
        for element in gir.complete_chain():
            service = gir.client if element in gir.elements["client_sidecar"] else gir.server
            service_dir = os.path.join(deploy_dir, f"{service}-arpc")
            os.makedirs(service_dir, exist_ok=True)
            if "arpc" in element.target:
                source_path = os.path.join(local_gen_dir, element.compile_dir, "element.go")
                dest_path = os.path.join(service_dir, f"{element.lib_name}.go")
                if os.path.exists(source_path):
                    execute_local(["cp", source_path, dest_path])
                    os.system(f"goimports -w {dest_path}")
                    GRAPH_BACKEND_LOG.debug(f"Copied {element.lib_name} to {service_dir}")
                timestamp = str(datetime.now().strftime("%Y%m%d%H%M%S"))

                element_src = os.path.join(service_dir, f"{element.lib_name}.go")
                plugin_name = f"{service}-{timestamp}"
                plugin_output = os.path.join(service_dir, plugin_name)

                proto_file_name = f"{app_name}_{gir.client}-{gir.server}_arpc.proto"
                execute_local(["cp", os.path.join(local_gen_dir, proto_file_name), args.arpc_stub_dir])
                execute_local([
                    "protoc",
                    f"--proto_path={args.arpc_stub_dir}",
                    "--symphony_out=paths=source_relative:.", "--arpc_out=paths=source_relative:.", "--go_out=paths=source_relative:.", 
                    proto_file_name,
                ], cwd=args.arpc_stub_dir)

                # Build from proxy directory with absolute path to element source file
                execute_local(
                    [
                        "go",
                        "build",
                        "-C",
                        ARPC_PROXY_DIR, # the proxy core directory contains dependencies for the plugins
                        "-o",
                        plugin_output,
                        "-buildmode=plugin",
                        "-trimpath",
                        element_src,
                    ],
                    env={"CGO_ENABLED": "1"},
                )

                # Copy to local interceptors directory
                execute_local(["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
                execute_local(
                    [
                        "cp",
                        plugin_output,
                        "/tmp/appnet/arpc-plugins",
                    ]
                )

                GRAPH_BACKEND_LOG.debug(f"Built aRPC plugin: {plugin_name}")
    
    nodes = get_node_names(control_plane=False)
    for node in nodes:
        execute_remote_host(node, ["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
        copy_remote_host(
            node,
            "/tmp/appnet/arpc-plugins",
            "/tmp/appnet/arpc-plugins",
        )
    GRAPH_BACKEND_LOG.info("aRPC element plugins are copied to all nodes")


    # for service in services:
    #     service_dir = os.path.join(deploy_dir, f"{service}-arpc")
    #     os.makedirs(service_dir, exist_ok=True)

    #     # Collect all elements for this service
    #     service_elements = (client_elements.get(service) or set()).union(
    #         server_elements.get(service) or set()
    #     )

    #     # Copy generated element implementations to service_dir for reference
    #     # and to the proxy module directory for building
    #     for element in service_elements:
    #         source_path = os.path.join(local_gen_dir, element.compile_dir, "element.go")
    #         dest_path = os.path.join(service_dir, f"{element.lib_name}.go")
    #         if os.path.exists(source_path):
    #             execute_local(["cp", source_path, dest_path])
    #             os.system(f"goimports -w {dest_path}")
    #             GRAPH_BACKEND_LOG.debug(f"Copied {element.lib_name} to {service_dir}")

    #     timestamp = str(datetime.now().strftime("%Y%m%d%H%M%S"))

    #     for element in service_elements:
    #         element_src = os.path.join(service_dir, f"{element.lib_name}.go")
    #         plugin_name = f"{service}-{timestamp}"
    #         plugin_output = os.path.join(service_dir, plugin_name)

    #         # generate the serialization stub code using the annotated proto file
    #         proto_dir = args.arpc_stub_dir
    #         execute_local([
    #             "protoc",
    #             f"--proto_path={proto_dir}",
    #             "--symphony_out=paths=source_relative:.", "--arpc_out=paths=source_relative:.", "--go_out=paths=source_relative:.",
    #             "kv_arpc.proto"
    #         ], cwd=proto_dir)

    #         # Build from proxy directory with absolute path to element source file
    #         execute_local(
    #             [
    #                 "go",
    #                 "build",
    #                 "-C",
    #                 ARPC_PROXY_DIR,
    #                 "-o",
    #                 plugin_output,
    #                 "-buildmode=plugin",
    #                 "-trimpath",
    #                 element_src,
    #             ],
    #             env={"CGO_ENABLED": "1"},
    #         )

    #         # Copy to local interceptors directory
    #         execute_local(["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
    #         execute_local(
    #             [
    #                 "cp",
    #                 plugin_output,
    #                 "/tmp/appnet/arpc-plugins",
    #             ]
    #         )

    #         GRAPH_BACKEND_LOG.debug(f"Built aRPC plugin: {plugin_name}")

    #     # Copy to all nodes
    #     nodes = get_node_names(control_plane=False)
    #     for node in nodes:
    #         execute_remote_host(node, ["mkdir", "-p", "/tmp/appnet/arpc-plugins"])
    #         for element in service_elements:
    #             plugin_name = f"{service}-{timestamp}"
    #             copy_remote_host(
    #                 node,
    #                 f"/tmp/appnet/arpc-plugins/{plugin_name}",
    #                 "/tmp/appnet/arpc-plugins",
    #             )

    # Add ELEMENT_PLUGIN_PREFIX environment variable to symphony proxy containers
    add_element_plugin_prefix_to_symphony_proxies(_app_install_file)

    GRAPH_BACKEND_LOG.info(
        "aRPC compilation complete. The generated elements are deployed."
    )

