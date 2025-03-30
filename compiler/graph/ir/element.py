from __future__ import annotations

from typing import Any, Dict, List, Union

from rich.panel import Panel

from compiler.element import compile_element_property
from compiler.graph.pseudo_element_compiler import pseudo_gen_property

global_element_id = 0


def fetch_global_id() -> str:
    """Assign a globally-unique id to the new element instance."""
    global global_element_id
    global_element_id += 1
    return global_element_id


class AbsElement:
    def __init__(
        self,
        info: Union[Dict[str, Any], str],
        partner: str = "",
        server: str = "",
        initial_position: str = "",
        initial_target: str = "",
    ):
        """
        Args:
            info(dict): basic element information, including name, config, proto, method, etc.
            partner(str): the name of its partner, used for optimization
            server(str): used for generating unique element name
                consider "cache" on both A->B and A->C
            initial_position(str): "client" or "server" or "ambient"
            initial_target(str): "grpc" or ["sidecar", "ambient"] * ["wasm", "native"]
        """
        if info == "NETWORK" or info == "IPC":
            self.name = info
            self.position = info[0]
        else:
            self.id = fetch_global_id()
            self.name: List[str] = [info["name"]]
            self.path: List[str] = [info["path"]]
            self.server = server  # the server side of the edge, used for generating unique file name
            self.config = info["config"] if "config" in info else []
            self.position = info["position"] if "position" in info else "any"
            self.processor = (
                info["processor"]
                if "processor" in info
                else ["grpc", "sidecar", "ambient"]
            )
            if "envoy_native" in info and info["envoy_native"] == True:
                self.upgrade = "no"
            elif "upgrade" in info and info["upgrade"] == True:
                self.upgrade = "yes"
            else:
                self.upgrade = "any"
            self.target = initial_target
            if self.upgrade == "yes":
                self.target = self.target.replace("native", "wasm")
            elif self.upgrade == "no":
                self.target = self.target.replace("wasm", "native")
            self.final_position = initial_position
            self.proto = info["proto"]
            self.method = info["method"]
            self.proto_mod_name = (
                info["proto_mod_name"] if "proto_mod_name" in info else ""
            )
            self.proto_mod_location = (
                info["proto_mod_location"] if "proto_mod_location" in info else ""
            )
            self.partner = partner
            self.compile_dir = ""

    @property
    def desc(self) -> str:
        return "_".join(self.name) + "_" + str(self.id)

    @property
    def deploy_name(self) -> str:
        return "".join([self.name[0].capitalize()] + self.name[1:])

    @property
    def lib_name(self) -> str:
        return self.server + "".join(self.name)[:24]

    @property
    def configs(self) -> str:
        return "\n".join(self.config)

    def __str__(self):
        s = "+".join(self.name)
        if "wasm" in self.target:
            s += "(wasm)"
        elif "native" in self.target:
            s += "(native)"
        return s

    def to_rich(self, processor):
        if processor == "client_grpc":
            color = "dark_green"
        elif processor == "client_sidecar":
            color = "light_green"
        elif processor == "ambient":
            color = "brown"
        elif processor == "server_sidecar":
            color = "dark_blue"
        elif processor == "server_grpc":
            color = "blue"
        else:
            color = "black"
        return Panel(
            self.deploy_name,
            style=color,
            expand=False,
        )

    def set_property_source(self, pseudo_property: bool):
        self.pseudo_property = pseudo_property

    @property
    def prop(self):
        if not hasattr(self, "_prop"):
            if self.name == "NETWORK":
                self._prop = {
                    "request": {
                        "delay": True,
                    },
                    "response": {
                        "delay": True,
                    },
                }
            else:
                assert hasattr(self, "pseudo_property"), "property source not set"
                if self.pseudo_property:
                    self._prop = pseudo_gen_property(self)
                else:
                    self._prop = compile_element_property(
                        self.name, self.path, server=self.server
                    )
                # TODO: remove this after property compiler has deduplication
                for path in ["request", "response"]:
                    for p in self._prop[path].keys():
                        if isinstance(self._prop[path][p], list):
                            self._prop[path][p] = list(set(self._prop[path][p]))
        return self._prop

    def has_prop(self, path: str, *props) -> bool:
        """Check whether the element has at least one of the listed properties.

        Args:
            path: "request" or "response"
            props: several property names

        Returns:
            at least one property exist => True
            all property not exist => False
        """
        assert path in ["request", "response"], f"path = {path} not exist"
        for p in props:
            if p in self.prop[path]:
                if isinstance(self.prop[path][p], list):
                    return True
                elif self.prop[path][p] is True:
                    return True
        return False

    def get_prop(self, path: str, p: str) -> Union[List[str], bool]:
        """Get property

        Args:
            path: "request" or "response"
            p: property name

        Returns:
        """
        assert path in ["request", "response"], f"path = {path} not exist"
        if p in self.prop[path]:
            return self.prop[path][p]
        else:
            return []

    def add_prop(self, path: str, p: str, contents: Union[str, List[str]]):
        """Add property

        Args:
            path: "request" or "response"
            p: property name
            contents: new contents to be added
        """
        assert path in ["request", "response"], f"path = {path} not exist"
        if p not in self.prop[path]:
            self.prop[path][p] = []
        if isinstance(contents, str):
            self.prop[path][p].append(contents)
        elif isinstance(contents, list):
            self.prop[path][p].extend(contents)
        else:
            raise ValueError

    def fuse(self, other: AbsElement):
        """Fuse another element in

        Args:
            other: the element to be fused.
        """
        self.name.extend(other.name)
        self.path.extend(other.path)
        self.config.extend(other.config)
        self.position = (
            self.position
            if len(self.position) < len(other.position)
            else other.position
        )
        # Fuse properties
        # Consolidation is the last step of optimization. Therefore, only state
        # properties need to be merged.
        self.prop["state"]["stateful"] |= other.prop["state"]["stateful"]
        if other.prop["state"]["consistency"] == "strong":
            self.prop["state"]["consistency"] = "strong"
