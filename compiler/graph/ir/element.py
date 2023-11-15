from __future__ import annotations

from typing import Any, Dict, List

from rich.panel import Panel

from compiler.graph.pseudo_element_compiler import pseudo_gen_property
from compiler.ir import compile_element_property

global_element_id = 0


def fetch_global_id() -> str:
    """Assign a globally-unique id to the new element instance."""
    global global_element_id
    global_element_id += 1
    return global_element_id


class AbsElement:
    def __init__(self, edict: Dict[str, Any]):
        self.id = fetch_global_id()
        self.name: List[str] = [edict["name"]]
        self.spec: List[str] = [edict["spec"]]
        self.config = edict["config"]
        self.position = [edict["position"]]

    @property
    def desc(self) -> str:
        return "_".join(self.name) + "_" + str(self.id)

    @property
    def deploy_name(self) -> str:
        return "".join(self.name)

    @property
    def lib_name(self) -> str:
        names = [sname.split("/")[-1].split(".")[0] for sname in self.spec]
        return "_".join(names)

    @property
    def configs(self) -> str:
        return "\n".join(self.config)

    def __str__(self):
        return "+".join(self.name)

    def gen_property(self, pseudo: bool):
        """Generate properties of the element.

        Args:
            pseudo: If true, call the pseudo element compiler to generate properties.
        """
        self.property = compile_element_property(self.lib_name)
        # if pseudo:
        #     self.property = pseudo_gen_property(self)
        # else:
        #     # self.property: Dict[str, Dict[str, Any]] = {
        #     #     "request": dict(),
        #     #     "response": dict(),
        #     # }
        #     self.property = compile_element_property(self.lib_name)
        #     print(self.property)
        #     assert 0
        #     # TODO: call element compiler to generate properties

    def to_rich(self, position):
        color = "dark_green" if position == "client" else "blue"
        return Panel(
            self.deploy_name,
            style=color,
        )

    def fuse(self, other: AbsElement):
        """Fuse another element in

        Args:
            other: the element to be fused.
        """
        self.name.extend(other.name)
        self.spec.extend(other.spec)
        self.config.extend(other.config)
        self.position.extend(other.position)
        # TODO: fuse properties
