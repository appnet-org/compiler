from __future__ import annotations

import importlib
import os
from copy import deepcopy
from pathlib import Path
from typing import Dict

import yaml

from compiler import graph_base_dir
from compiler.graph.backend.utils import (
    execute_local,
    execute_remote_host,
    find_target_yml,
    get_node_names,
)
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG

# backends = ["grpc", "sidecar", "ambient"]
backends = ["grpc", "sidecar", "ambient"]
element_count = {
    "grpc": 0,
    "sidecar": 0,
    "ambient": 0,
}

BACKEND_CONFIG_DIR = os.path.join(Path(__file__).parent, "config")


def attach_volumes_and_adjust_replica(app_manifest_file: str) -> list[any]:
    # Load application manifest
    with open(app_manifest_file, "r") as f:
        yml_list = list(yaml.safe_load_all(f))

    # Find all services (execept storage or tracing services)
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
        pv_copy["metadata"]["name"] = f"{service}-appnet-pv"
        pv_copy["spec"]["hostPath"]["path"] = "/tmp/appnet"
        pvc_copy["metadata"]["name"] = f"{service}-appnet-pvc"
        pvc_copy["spec"]["volumeName"] = f"{service}-appnet-pv"
        yml_list.append(pv_copy)
        yml_list.append(pvc_copy)

        # Find the corresponding service in the manifest
        target_service_yml = find_target_yml(yml_list, service)

        # Adjust replica count if SERVICE_REPLICA exists
        replica = os.getenv("SERVICE_REPLICA")
        if replica is not None:
            target_service_yml["spec"]["replicas"] = int(replica)

        # Attach the element to the sidecar using volumes
        if "volumes" not in target_service_yml["spec"]["template"]["spec"]:
            target_service_yml["spec"]["template"]["spec"]["volumes"] = []

        if (
            "volumeMounts"
            not in target_service_yml["spec"]["template"]["spec"]["containers"][0]
        ):
            target_service_yml["spec"]["template"]["spec"]["containers"][0][
                "volumeMounts"
            ] = []

        for d in target_service_yml["spec"]["template"]["spec"]["containers"]:
            d["volumeMounts"].append(
                {"mountPath": "/appnet", "name": f"{service}-appnet-volume"}
            )

        target_service_yml["spec"]["template"]["spec"]["volumes"].append(
            {
                "persistentVolumeClaim": {"claimName": f"{service}-appnet-pvc"},
                "name": f"{service}-appnet-volume",
            }
        )

    return [yml for yml in yml_list if yml is not None]


def scriptgen(
    girs: Dict[str, GraphIR],
    app_name: str,
    app_manifest_file: str,
    app_edges: list,
):
    """
    Call corresponding script generation procedure according to the backend name.

    Args:
        girs: A dictionary mapping edge name to corresponding graphir.
        app_name: the name of the application (for naming)
        app_manifest_file: the path to the application manifest file
        app_edges: the communication edges of the application
    """
    deploy_dir = os.path.join(graph_base_dir, "generated", f"{app_name}-deploy")
    os.makedirs(deploy_dir, exist_ok=True)
    app_install_file = os.path.join(deploy_dir, "app-install.yml")
    execute_local(["cp", app_manifest_file, app_install_file])

    GRAPH_BACKEND_LOG.info("Clear gRPC interceptor history files")
    execute_local(["rm", "-rf", "/tmp/appnet/interceptors/*"])
    nodes = get_node_names(control_plane=False)
    for node in nodes:
        execute_remote_host(node, ["rm", "-rf", "/tmp/appnet/interceptors/*"])

    for gir in girs.values():
        element_count["grpc"] += len(gir.elements["client_grpc"]) + len(
            gir.elements["server_grpc"]
        )
        element_count["sidecar"] += len(gir.elements["client_sidecar"]) + len(
            gir.elements["server_sidecar"]
        )
        element_count["ambient"] += len(gir.elements["ambient"])

    for target in backends:
        if element_count[target] > 0:
            module = importlib.import_module(f"compiler.graph.backend.{target}")
            generator = getattr(module, f"scriptgen_{target}")
            generator(girs, app_name, app_install_file, app_edges)

    app_yml_list = attach_volumes_and_adjust_replica(app_install_file)

    with open(app_install_file, "w") as f:
        yaml.dump_all(app_yml_list, f, default_flow_style=False)
