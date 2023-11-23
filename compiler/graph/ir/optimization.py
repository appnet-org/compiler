from copy import deepcopy
from typing import List, Tuple

from compiler.graph.ir.element import AbsElement


def gen_dependency(chain: List[AbsElement], path: str):
    fields = {"droptrace", "blocktrace"}
    for element in chain:
        for f in element.prop[path]["read"] + element.prop[path]["write"]:
            fields.add(f)
    writer_table = {f: ["INPUT"] for f in fields}
    dep = dict()
    for element in chain:
        rfields, wfields = element.prop[path]["read"], element.prop[path]["write"]
        if rfields == "*":
            rfields = list(fields)
        if wfields == "*":
            wfields = list(fields)
        for f in rfields:
            dep[(element.deploy_name, f)] = deepcopy(writer_table[f])
        for f in wfields:
            writer_table[f].append(element.deploy_name)
    for f in fields:
        dep[("OUTPUT", f)] = deepcopy(writer_table[f])
    return dep


def equivalent(chain: List[AbsElement], new_chain: List[AbsElement], path: str) -> bool:
    server_element = False
    for element in new_chain:
        if element.position == "S":
            server_element = True
        if element.position == "C" and server_element:
            return False
    dep, new_dep = gen_dependency(chain, path), gen_dependency(new_chain, path)
    return dep == new_dep


class OptimizedLabel(Exception):
    pass


def reorder(chain: List[AbsElement], path: str) -> List[AbsElement]:
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


def chain_optimize(
    chain: List[AbsElement], path: str
) -> Tuple[List[AbsElement], List[AbsElement]]:
    chain = reorder(chain, path)
    latest = 0
    while latest < len(chain) and chain[latest].position != "S":
        latest += 1
    return chain[:latest], chain[latest:]
