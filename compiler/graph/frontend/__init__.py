from __future__ import annotations

import os
from typing import Dict, Tuple, Union

import yaml

from compiler import *
from compiler.graph.ir import GraphIR


class GraphParser:
    def __init__(self):
        self.services = set()
        self.app_edges = []

    def parse(self, spec_path: str) -> Tuple[Union[Dict[str, GraphIR], str, str]]:
        """Parse the user specification file and produce graphirs & service locations.

        Args:
            spec_path (str): Path to the user specification file.

        Returns:
            * A dictionary mapping edge name to corresponding graphir.
            * Application name.
            * Path to application manifest file.
            * Edges between microservices.

        Raises:
            FileNotFoundError: If app manifest file does not exist.
        """
        with open(spec_path, "r") as f:
            spec_dict = yaml.safe_load(f)

        # TODO: temporarily disable ingress & egress spec tpye
        for edge in spec_dict["app_structure"]:
            client, server = edge.split("->")
            client, server = client.strip(), server.strip()
            self.services.add(client)
            self.services.add(server)
            self.app_edges.append((client, server))

        graphir: Dict[str, GraphIR] = dict()
        for client, server in self.app_edges:
            chain, pair, transport, edge_id = [], [], [], f"{client}->{server}"
            
            # Client's egress
            if "egress" in spec_dict and client in spec_dict["egress"]:
                chain.extend(spec_dict["egress"][client])
            # Client->server edge
            if "edge" in spec_dict and f"{client}->{server}" in spec_dict["edge"]:
                chain.extend(spec_dict["edge"][edge_id])
            # Server's ingress
            if "ingress" in spec_dict and server in spec_dict["ingress"]:
                chain.extend(spec_dict["ingress"][server])
            # Client->server link (for paired elements)
            if "link" in spec_dict and f"{client}->{server}" in spec_dict["link"]:
                pair.extend(spec_dict["link"][edge_id])
            # Transport elements
            if "transport" in spec_dict and f"{client}->{server}" in spec_dict["edge"]:
                transport.extend(spec_dict["transport"][edge_id])
            
            if any([chain, pair, transport]):
                graphir[edge_id] = GraphIR(client, server, chain, pair, transport)

        # Get file path for application's manifest file
        app_name = spec_dict["app_name"]
        app_manifest_file = spec_dict["app_manifest"]

        # Check if the application manifest file exists
        if not os.path.exists(app_manifest_file):
            raise FileNotFoundError(app_manifest_file)

        return graphir, app_name, app_manifest_file, self.app_edges
