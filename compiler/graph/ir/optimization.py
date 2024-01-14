from copy import deepcopy
from pprint import pprint
from typing import List, Tuple

from compiler.graph.ir.element import AbsElement


def gen_dependency(chain: List[AbsElement], path: str):
    fields = {"droptrace", "blocktrace", "copytrace"}
    for element in chain:
        for f in (
            element.get_prop(path, "read")
            + element.get_prop(path, "write")
            + element.get_prop(path, "record")
        ):
            fields.add(f)
    writer_table = {f: ["INPUT"] for f in fields}
    dep = {"read": dict(), "record": dict()}
    for element in chain:
        rfields, wfields, rec_fields = (
            element.get_prop(path, "read"),
            element.get_prop(path, "write"),
            element.get_prop(path, "record"),
        )
        assert len(set(rfields)) == len(rfields), "duplicate fields"
        assert len(set(wfields)) == len(wfields), "duplicate fields"
        assert len(set(rec_fields)) == len(rec_fields), "duplicate fields"
        if rfields == "*":
            rfields = list(fields)
        if wfields == "*":
            wfields = list(fields)
        for f in rfields:
            dep["read"][(element.lib_name, f)] = deepcopy(writer_table[f])
        for f in rec_fields:
            dep["record"][(element.lib_name, f)] = deepcopy(writer_table[f])
        for f in wfields:
            if element.partner in writer_table[f]:
                writer_table[f].remove(element.partner)
            else:
                writer_table[f].append(element.lib_name)
    for f in fields:
        dep["read"][("OUTPUT", f)] = deepcopy(writer_table[f])
    return dep


def equivalent(chain: List[AbsElement], new_chain: List[AbsElement], path: str) -> bool:
    server_element = False
    for element in new_chain:
        if element.position == "N":
            server_element = True
        if element.position == "S" and not server_element:
            return False
        if element.position == "C" and server_element:
            return False
    dep, new_dep = gen_dependency(chain, path), gen_dependency(new_chain, path)
    return dep["read"] == new_dep["read"]
    # return dep == new_dep


class OptimizedLabel(Exception):
    pass


def reorder(chain: List[AbsElement], path: str) -> List[AbsElement]:
    # preparation: add some properties for analysis
    for element in chain:
        if element.has_prop(path, "record"):
            element.add_prop(path, "record", ["droptrace", "blocktrace", "copytrace"])
        if element.has_prop(path, "drop"):
            element.add_prop(path, "write", "droptrace")
        if element.has_prop(path, "block"):
            element.add_prop(path, "write", "blocktrace")
        if element.has_prop(path, "copy"):
            element.add_prop(path, "write", "copytrace")
    # reorder
    optimized = True
    while optimized:
        optimized = False
        drop_list, non_drop_list, copy_list, non_copy_list = [], [], [], []
        for i, element in enumerate(chain):
            if element.has_prop(path, "drop", "block"):
                drop_list.append(i)
            else:
                non_drop_list.append(i)
            if element.has_prop(path, "copy"):
                copy_list.append(i)
            else:
                non_copy_list.append(i)
        try:
            for i in non_drop_list:
                for j in drop_list[::-1]:
                    if i > j:
                        break
                    # strategy 1: move drop element at the front of non-drop ones
                    new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
                    if equivalent(chain, new_chain, path):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
                    # strategy 2: move non-drop element behind drop ones
                    new_chain = (
                        chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
                    )
                    if equivalent(chain, new_chain, path):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
            for i in copy_list:
                for j in non_copy_list[::-1]:
                    if i > j:
                        break
                    # strategy 1: move copy element behind non-copy ones
                    new_chain = (
                        chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
                    )
                    if equivalent(chain, new_chain, path):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
                    # strategy 2: move non-copy element at the front of copy ones
                    new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
                    if equivalent(chain, new_chain, path):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
        except OptimizedLabel:
            pass
    return chain


def gather(chain: List[AbsElement]) -> List[AbsElement]:
    has_client, has_server, np = False, False, 0
    for i, element in enumerate(chain):
        if element.position == "C":
            has_client = True
        elif element.position == "S":
            has_server = True
        elif element.position == "N":
            np = i
    if not has_server:
        # migrate all to client side
        return chain[:np] + chain[np + 1 :] + [chain[np]]
    if not has_client:
        # migrate all to server side
        return [chain[np]] + chain[:np] + chain[np + 1 :]
    return chain


def chain_optimize(
    chain: List[AbsElement],
    path: str,
    pseudo_property: bool,
) -> Tuple[List[AbsElement], List[AbsElement]]:
    """Optimize an element chain

    Args:
        chain: A list of AbsElement
        path: "request" or "response"
        pseudo_property: if true, use hand-coded properties for analysis

    Returns:
        client chain and server chain
    """
    # Step 1: Reorder + Migration
    chain = reorder(chain, path)

    # Step 2: Further migration - opportunity to turn off sidecars
    chain = gather(chain)

    # split the chain into client + server
    network_pos = 0
    while network_pos < len(chain) and chain[network_pos].position != "N":
        network_pos += 1
    client_chain, server_chain = chain[:network_pos], chain[network_pos + 1 :]

    # Step 3: consolidation
    for i in range(1, len(client_chain)):
        client_chain[0].fuse(client_chain[i])
    for i in range(1, len(server_chain)):
        server_chain[0].fuse(server_chain[i])
    client_chain, server_chain = client_chain[:1], server_chain[:1]

    return client_chain, server_chain
