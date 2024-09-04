from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Union

from rich import box
from rich.panel import Panel

from compiler.graph.ir.element import AbsElement
from compiler.graph.ir.optimization import chain_optimize, cost_chain_optimize


def make_service_rich(name: str) -> Panel:
    """Generate rich.panel objects of a service for visualization.

    Args:
        name: Service name.

    Returns:
        A rich.panel object.
    """
    return Panel(
        name,
        box=box.SQUARE,
        border_style="bold",
        style="bold",
        expand=False,
    )


class GraphIR:
    def __init__(self, client: str, server: str, chain: List[Dict], pair: List[Dict]):
        """Initiate an unoptimized graphir according to the specified elements.

        Args:
            client: Client service name.
            server: Server service name.
            chain: A list of dictionaries including user-specified element configs.
            pair: A list of dictionaries including user-specified paired-element configs.
                  Pair elements are deployed on the client and server sides which cancel
                  out each other.

        Raises:
            ValueError: if user specification is invalid.
        """
        self.client = client
        self.server = server
        self.elements: Dict[str, List[AbsElement]] = {
            "client_grpc": [],
            "client_sidecar": [],
            "ambient": [],
            "server_sidecar": [],
            "server_grpc": [],
        }
        # determine an initial assignment
        # principle:
        # valid ("C" goes to client, "S" goes to server, "C/S" goes to ambient)
        # balanced #element in grpc/sidecar
        c_id, s_id = -1, len(chain)
        for i, element in enumerate(chain):
            if "position" in element and element["position"] == "client":
                c_id = max(c_id, i)
            elif "position" in element and element["position"] == "server":
                s_id = min(s_id, i)
        if c_id >= s_id:
            raise ValueError("invalid client/server position requirements")
        # "C/S" goes to ambient
        # for i in range(c_id + 1, s_id):
        #     self.elements["ambient"].append(
        #         AbsElement(
        #             chain[i],
        #             server=server,
        #             initial_position="ambient",
        #             initial_target="ambient_wasm",
        #         )
        #     )
        mid = (c_id + s_id) // 2
        client_chain, server_chain = chain[: mid + 1], chain[mid + 1 :]
        current_mode = "sidecar"
        for element in client_chain[::-1]:
            if (
                "processor" in element
                and "grpc" in element["processor"]
                and "sidecar" not in element["processor"]
            ):
                current_mode = "grpc"
            if "processor" in element and current_mode not in element["processor"]:
                raise ValueError("invalid grpc/sidecar requirements")
            self.elements["client_" + current_mode].insert(
                0,
                AbsElement(
                    element,
                    server=server,
                    initial_position="client",
                    initial_target="grpc" if "grpc" in current_mode else "sidecar_wasm",
                ),
            )
        current_mode = "sidecar"
        for i, element in enumerate(server_chain):
            if (
                "processor" in element
                and "grpc" in element["processor"]
                and "sidecar" not in element["processor"]
            ):
                current_mode = "grpc"
            if "processor" in element and current_mode not in element["processor"]:
                raise ValueError("invalid grpc/sidecar requirements")
            self.elements["server_" + current_mode].append(
                AbsElement(
                    element,
                    server=server,
                    initial_position="server",
                    initial_target="grpc" if "grpc" in current_mode else "sidecar_wasm",
                )
            )

        # add element pairs to c/s sides
        for pdict in pair:
            edict1 = {
                "name": pdict["name1"],
                "config": pdict["config1"] if "config1" in pdict else [],
                "position": "C",
                "proto": pdict["proto"],
                "method": pdict["method"],
                "path": pdict["path1"],
            }
            edict2 = {
                "name": pdict["name2"],
                "config": pdict["config2"] if "config2" in pdict else [],
                "position": "S",
                "proto": pdict["proto"],
                "method": pdict["method"],
                "path": pdict["path2"],
            }
            self.elements["client_sidecar"].append(
                AbsElement(
                    edict1,
                    partner=pdict["name2"],
                    server=server,
                    initial_position="client",
                    initial_target="sidecar_wasm",
                )
            )
            self.elements["server_sidecar"].insert(
                0,
                AbsElement(
                    edict2,
                    partner=pdict["name1"],
                    server=server,
                    initial_position="server",
                    initial_target="sidecar_wasm",
                ),
            )

    @property
    def name(self) -> str:
        return f"{self.client}->{self.server}"

    def __str__(self):
        s = f"{self.client}->{self.server} GraphIR: \n"
        for pos, subchain in self.elements.items():
            s += pos + ": " + " -> ".join(map(str, subchain)) + "\n"
        return s

    def to_rich(self) -> List[Union[Panel, str]]:
        # TODO: better visualization
        """Generate rich.panel objects for visualization.

        Returns:
            A list of rich.panel objects/strings.
        """
        panel_list = [make_service_rich(self.client), "\n~\n"]
        for e in (
            self.elements["client_grpc"]
            + self.elements["client_sidecar"]
            + self.elements["ambient"]
            + self.elements["server_sidecar"]
            + self.elements["server_grpc"]
        ):
            panel_list.append(e.to_rich("TBD"))
        # for i, e in enumerate(self.elements["req_client"]):
        #     if i != 0:
        #         panel_list.append("\n→\n")
        #     panel_list.append(e.to_rich("client"))
        # panel_list.append("\n(network)\n")
        # for i, e in enumerate(self.elements["req_server"]):
        #     if i != 0:
        #         panel_list.append("\n→\n")
        #     panel_list.append(e.to_rich("server"))
        # panel_list.append("\n~\n")
        panel_list.append(make_service_rich(self.server))
        return panel_list

    def complete_chain(self) -> List[AbsElement]:
        return (
            self.elements["client_grpc"]
            + self.elements["client_sidecar"]
            + self.elements["ambient"]
            + self.elements["server_sidecar"]
            + self.elements["server_grpc"]
        )

    def optimize(self, opt_level: str, algorithm: str):
        """Run optimization algorithm on the graphir."""
        optimize_func = cost_chain_optimize if algorithm == "cost" else chain_optimize
        self.elements = optimize_func(
            self.complete_chain(),
            "request",
            opt_level,
        )
