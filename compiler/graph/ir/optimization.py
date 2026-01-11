from copy import deepcopy
from itertools import permutations, product
from pprint import pprint
from typing import Dict, List, Tuple
import os, yaml

from compiler.graph.ir.element import AbsElement
from compiler import graph_base_dir

def init_dependency(chain: List[AbsElement], path: str):
    for element in chain:
        if element.has_prop(path, "record"):
            element.add_prop(path, "record", ["droptrace", "blocktrace", "copytrace"])
        if element.has_prop(path, "drop"):
            element.add_prop(path, "write", "droptrace")
        if element.has_prop(path, "block"):
            element.add_prop(path, "write", "blocktrace")
        if element.has_prop(path, "copy"):
            element.add_prop(path, "write", "copytrace")


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

    # droptrace and blocktrace are sets, not list
    for _t, d in dep.items():
        for ename_fname, contents in d.items():
            if ename_fname[1] in ["droptrace", "blocktrace", "copytrace"]:
                d[ename_fname] = set(contents)
    return dep


def position_valid(chain: List[AbsElement]) -> bool:
    server_side = False
    for element in chain:
        if element.position == "N":
            server_side = True
        if element.position == "S" and not server_side:
            return False
        if element.position == "C" and server_side:
            return False
    return True


def equivalent(
    chain: List[AbsElement], new_chain: List[AbsElement], path: str, opt_level: str
) -> bool:
    if opt_level == "ignore":
        return True
    dep, new_dep = gen_dependency(chain, path), gen_dependency(new_chain, path)
    if opt_level == "weak":
        return dep["read"] == new_dep["read"]
    elif opt_level == "strong":
        return dep == new_dep
    else:
        raise ValueError(f"Unexpected optimization level {opt_level}")
    # return dep == new_dep


class OptimizedLabel(Exception):
    pass


# def reorder(chain: List[AbsElement], path: str, opt_level: str) -> List[AbsElement]:
#     # preparation: add some properties for analysis
#     init_dependency(chain, path)
#     # reorder
#     optimized = True
#     while optimized:
#         optimized = False
#         drop_list, non_drop_list, copy_list, non_copy_list = [], [], [], []
#         for i, element in enumerate(chain):
#             if element.has_prop(path, "drop", "block"):
#                 drop_list.append(i)
#             else:
#                 non_drop_list.append(i)
#             if element.has_prop(path, "copy"):
#                 copy_list.append(i)
#             else:
#                 non_copy_list.append(i)
#         try:
#             for i in non_drop_list:
#                 for j in drop_list[::-1]:
#                     if i > j:
#                         break
#                     # strategy 1: move drop element at the front of non-drop ones
#                     new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
#                     if equivalent(chain, new_chain, path, opt_level):
#                         chain = new_chain
#                         optimized = True
#                         raise OptimizedLabel()
#                     # strategy 2: move non-drop element behind drop ones
#                     new_chain = (
#                         chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
#                     )
#                     if equivalent(chain, new_chain, path, opt_level):
#                         chain = new_chain
#                         optimized = True
#                         raise OptimizedLabel()
#             for i in copy_list:
#                 for j in non_copy_list[::-1]:
#                     if i > j:
#                         break
#                     # strategy 1: move copy element behind non-copy ones
#                     new_chain = (
#                         chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
#                     )
#                     if equivalent(chain, new_chain, path, opt_level):
#                         chain = new_chain
#                         optimized = True
#                         raise OptimizedLabel()
#                     # strategy 2: move non-copy element at the front of copy ones
#                     new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
#                     if equivalent(chain, new_chain, path, opt_level):
#                         chain = new_chain
#                         optimized = True
#                         raise OptimizedLabel()
#         except OptimizedLabel:
#             pass
#     return chain


# def gather(chain: List[AbsElement]) -> List[AbsElement]:
#     last_client, first_server, np = -1, len(chain), 0
#     client_strong, cs_strong, server_strong = False, False, False
#     for i, element in enumerate(chain):
#         if element.position == "C":
#             last_client = max(last_client, i)
#             if element.prop["state"]["consistency"] == "strong":
#                 client_strong = True
#         elif element.position == "S":
#             first_server = min(first_server, i)
#             if element.prop["state"]["consistency"] == "strong":
#                 server_strong = True
#         elif element.position == "N":
#             np = i
#         else:
#             if element.prop["state"]["consistency"] == "strong":
#                 cs_strong = True
#     if first_server == len(chain):
#         # migrate all elements to the client side
#         chain = chain[:np] + chain[np + 1 :] + [chain[np]]
#     elif last_client == -1:
#         # migrate all elements to the server side
#         chain = [chain[np]] + chain[:np] + chain[np + 1 :]
#     else:
#         if server_strong and not client_strong and cs_strong:
#             # migrate all C/S elements to the server side
#             chain = (
#                 chain[: last_client + 1]
#                 + [chain[np]]
#                 + chain[last_client + 1 : np]
#                 + chain[np + 1 :]
#             )
#         else:
#             # migrate all C/S elements to the client side
#             chain = (
#                 chain[:np]
#                 + chain[np + 1 : first_server]
#                 + [chain[np]]
#                 + chain[first_server:]
#             )
#     return chain


# def split_and_consolidate(
#     chain: List[AbsElement],
# ) -> Tuple[List[AbsElement], List[AbsElement]]:
#     network_pos = 0
#     while network_pos < len(chain) and chain[network_pos].position != "N":
#         network_pos += 1
#     client_chain, server_chain = chain[:network_pos], chain[network_pos + 1 :]

#     for i in range(1, len(client_chain)):
#         client_chain[0].fuse(client_chain[i])
#     for i in range(1, len(server_chain)):
#         server_chain[0].fuse(server_chain[i])
#     client_chain, server_chain = client_chain[:1], server_chain[:1]

#     return client_chain, server_chain


# TODO: update heuristic optimization
# def chain_optimize(
#     chain: List[AbsElement],
#     path: str,
#     opt_level: str,
#     dump_property: bool,
# ) -> Tuple[List[AbsElement], List[AbsElement]]:
#     """Optimize an element chain

#     Args:
#         chain: A list of AbsElement
#         path: "request" or "response"
#         pseudo_property: if true, use hand-coded properties for analysis

#     Returns:
#         client chain and server chain
#     """
#     # Step 1: Reorder + Migration
#     chain = reorder(chain, path, opt_level)

#     # Step 2: Further migration - more opportunities for state consolidation
#     # and turning off sidecars
#     chain = gather(chain)

#     return split_and_consolidate(chain)


# def cost(chain: List[AbsElement], path: str = "request") -> float:
#     # Parameters
#     # TODO: different parameters for different backends
#     e = 1.0
#     n = 1.0
#     d = 0.1
#     s = 5.0
#     r = 5.0

#     cost = 0

#     workload = 1.0
#     for element in chain:
#         cost += workload * (n if element.position == "N" else e)
#         if element.has_prop(path, "drop", "block"):
#             workload *= 1 - d

#     network_pos = -1
#     for i in range(len(chain)):
#         if chain[i].position == "N":
#             network_pos = i
#     assert network_pos != -1, "network element not found"
#     client_chain, server_chain = chain[:network_pos], chain[network_pos + 1 :]

#     for element in client_chain:
#         if (
#             element.prop["state"]["consistency"] == "strong"
#             and element.prop["state"]["state_dependence"] != "client_replica"
#         ):
#             cost += s
#             break
#     for element in server_chain:
#         if (
#             element.prop["state"]["consistency"] == "strong"
#             and element.prop["state"]["state_dependence"] != "server_replica"
#         ):
#             cost += s
#             break

#     if len(client_chain) > 0:
#         cost += r
#     if len(server_chain) > 0:
#         cost += r

#     return cost


def split_chain(chain: List[AbsElement]) -> Dict[str, List[AbsElement]]:
    subchains = {
        "client_grpc": [],
        "client_sidecar": [],
        "ambient": [],
        "server_sidecar": [],
        "server_grpc": [],
    }
    for element in chain:
        if element.final_position == "ambient":
            subchains["ambient"].append(element)
        else:
            position = element.final_position
            processor = "grpc" if "grpc" in element.target else "sidecar"
            subchains[f"{position}_{processor}"].append(element)
    return subchains


def in_nonlocal_position(element: AbsElement, pos: str) -> bool:
    state_dependence = element.prop["state"]["state_dependence"]
    if "client" in pos and state_dependence == ["client_service"]:
        return False
    if "server" in pos and state_dependence == ["server_service"]:
        return False
    if pos == "ambient" and (
        "client_service" in state_dependence or "server_service" in state_dependence
    ):
        return False
    return True


def cost(chain: List[AbsElement]) -> float:
    c = 0
    element_overhead_config = {
        "grpc": 1.0,
        "interceptor_arpc": 1.0,
        "sidecar_native": 1.0,
        "sidecar_wasm": 3.0,
        "sidecar_arpc": 1.0,
        "ambient_native": 1.0,
        "ambient_wasm": 3.0,
    }
    basic_overhead_config = {
        "client_grpc": 0.5,
        "client_sidecar": 5.0,
        "ambient": 5.0,
        "server_sidecar": 5.0,
        "server_grpc": 0.5,
    }
    transmission_overhead_config = {
        "ipc": 0.8,
        "network": 1,
    }
    state_sync_config = {
        "strong": {
            "client_grpc": 5.0,
            "client_sidecar": 5.0,
            "ambient": 2.0,
            "server_sidecar": 5.0,
            "server_grpc": 5.0,
        },
        "weak": {
            "client_grpc": 1.0,
            "client_sidecar": 1.0,
            "ambient": 1.0,
            "server_sidecar": 1.0,
            "server_grpc": 1.0,
        },
    }
    d = 0.1
    wasm_invocation = 0.5

    workload = 1.0

    # element overhead
    for i, element in enumerate(chain):
        e = element_overhead_config[element.target]
        c += e * workload
        if element.has_prop("request", "drop", "block"):
            workload *= 1.0 - d

    subchains = split_chain(chain)

    # network overhead
    if len(subchains["ambient"]) > 0:
        c += transmission_overhead_config["network"] * 2
    else:
        c += transmission_overhead_config["network"]
    if len(subchains["client_sidecar"]) > 0:
        c += transmission_overhead_config["ipc"]
    if len(subchains["server_sidecar"]) > 0:
        c += transmission_overhead_config["ipc"]
    for pos, subchain in subchains.items():
        # basic processor overhead
        if len(subchain) > 0:
            c += basic_overhead_config[pos]
        # state sync overhead
        l_pt, r_pt = 0, 0
        while l_pt < len(subchain):
            r_pt = l_pt
            while (
                r_pt < len(subchain) - 1
                and subchain[r_pt + 1].target == subchain[r_pt].target
            ):
                r_pt += 1
            sync_level = "no"
            for i in range(l_pt, r_pt + 1):
                consistency = subchain[i].prop["state"]["consistency"]
                if in_nonlocal_position(subchain[i], pos):
                    if consistency == "strong":
                        sync_level = "strong"
                    elif consistency == "weak" and sync_level != "strong":
                        sync_level = "weak"
            if sync_level in ["strong", "weak"]:
                c += state_sync_config[sync_level][pos]
            l_pt = r_pt + 1
        # wasm invocation overhead
        if "sidecar" in pos or "ambient" in pos:
            for i, element in enumerate(subchain):
                if "wasm" in element.target and (
                    i == 0 or "wasm" not in subchain[i - 1].target
                ):
                    c += wasm_invocation

    return c


def find_min_cost(chain: List[AbsElement]):
    class InvalidConfigLabel(Exception):
        pass

    def get_processor_and_position(
        index: int, ipc1: int, network1: int, network2: int, ipc2: int
    ) -> str:
        if index < ipc1:
            return "client", "grpc"
        elif ipc1 <= index < network1:
            return "client", "sidecar"
        elif network1 <= index < network2:
            return "ambient", "ambient"
        elif network2 <= index < ipc2:
            return "server", "sidecar"
        else:
            return "server", "grpc"

    length = len(chain)
    min_cost = 1000000
    best_processor_list, best_position_list = [], []
    # Enumerate positions of ipc_client/server and network_client/server
    # * ipc_client: client application ~ client sidecar
    # * network_client: client sidecar ~ ambient
    # * network_server: ambient ~ server sidecar
    # * ipc_server: server_sidecar ~ server application
    for ipc_client in range(length + 1):
        for network_client in range(ipc_client, length + 1):
            for network_server in range(network_client, length + 1):
                for ipc_server in range(network_server, length + 1):
                    options_list = []
                    position_list = []
                    try:
                        for i in range(length):
                            position, processor = get_processor_and_position(
                                i,
                                ipc_client,
                                network_client,
                                network_server,
                                ipc_server,
                            )
                            position_list.append(position)
                            if (
                                chain[i].position != "any"
                                and chain[i].position != position
                            ):
                                raise InvalidConfigLabel()
                            if not any(processor in p for p in chain[i].processor):
                                raise InvalidConfigLabel()
                            options = []
                            if len(chain[i].processor) > 0 and any("arpc" in p for p in chain[i].processor): 
                                if len(chain[i].processor) != 1:
                                    raise ValueError(f"{chain[i].name}: aRPC should be the only choice for processor")
                                options.append(chain[i].processor[0])
                            elif processor == "grpc":
                                options.append("grpc")
                            else:
                                if (
                                    chain[i].upgrade == "yes"
                                    or chain[i].upgrade == "any"
                                ):
                                    options.append(processor + "_wasm")
                                if (
                                    chain[i].upgrade == "any"
                                    or chain[i].upgrade == "no"
                                ):
                                    options.append(processor + "_native")
                            options_list.append(options)
                    except InvalidConfigLabel:
                        continue
                    for processor_list in list(product(*options_list)):
                        for i, element in enumerate(chain):
                            element.target = processor_list[i]
                            element.final_position = position_list[i]
                        new_cost = cost(chain)
                        if new_cost < min_cost:
                            min_cost = new_cost
                            best_processor_list = deepcopy(processor_list)
                            best_position_list = deepcopy(position_list)

    if best_processor_list != []:
        for i in range(length):
            chain[i].target = best_processor_list[i]
            chain[i].final_position = best_position_list[i]

    return min_cost


def cost_chain_optimize(chain: List[AbsElement], path: str, opt_level: str, dump_property: bool):
    init_dependency(chain, path)
    if dump_property:
        properties = []
        for element in chain:
            properties.append({
                "name": element.lib_name,
                "partner": element.partner,
                "position": element.position,
                "processor": element.processor,
                "upgrade": element.upgrade,
                "read": element.get_prop("request", "read"),
                "write": element.get_prop("request", "write"),
                "record": element.get_prop("request", "record"),
                "drop_or_block": element.has_prop("request", "drop", "block"),
                "state_consistency": element.prop["state"]["consistency"],
                "state_dependency": element.prop["state"]["state_dependence"],
            })
        # translate partner name into index
        for d in properties:
            if d["partner"] != "":
                for i, element in enumerate(chain):
                    if element.lib_name == d["partner"]:
                        d["partner"] = i
                        break
            else:
                d["partner"] = -1
            assert isinstance(d["partner"], int)
        gen_dir = os.path.join(graph_base_dir, "generated")
        os.makedirs(gen_dir, exist_ok=True)
        with open(os.path.join(gen_dir, "properties.yaml"), "w") as f:
            yaml.safe_dump(properties, f, default_flow_style=False, indent=4)

    min_cost = cost(chain)
    final_chain = deepcopy(chain)
    if opt_level != "no" and not dump_property:
        for new_chain in permutations(chain):
            if equivalent(chain, new_chain, path, opt_level):
                new_chain = deepcopy(new_chain)
                new_min_cost = find_min_cost(new_chain)
                if new_min_cost < min_cost:
                    min_cost = new_min_cost
                    final_chain = new_chain

    # split and consolidate
    subchains = split_chain(final_chain)

    # modify ambient element sync level
    # modify sync level of element w/ correct state dependency - position
    subchains = modify_sync_level(subchains)

    for pos, subchain in subchains.items():
        l_pt, r_pt = 0, 0
        consolidated_chain = []
        while l_pt < len(subchain):
            r_pt = l_pt
            while (
                r_pt < len(subchain) - 1
                and subchain[r_pt + 1].target == subchain[r_pt].target
            ):
                r_pt += 1
            for i in range(l_pt + 1, r_pt + 1):
                subchain[l_pt].fuse(subchain[i])
            consolidated_chain.append(subchain[l_pt])
            l_pt = r_pt + 1
        subchains[pos] = consolidated_chain

    return subchains


def modify_sync_level(subchains: Dict[str, List[AbsElement]]) -> Dict[str, List[AbsElement]]:
    replace_strong_weak = lambda s: s.replace("strong", "").replace("weak", "")
    for pos, chain in subchains.items():
        for element in chain:
            if element.prop["state"]["consistency"] in [
                "strong",
                "weak",
            ] and not in_nonlocal_position(element, pos):
                element.name = list(map(replace_strong_weak, element.name))
                element.path = list(map(replace_strong_weak, element.path)) 
    return subchains


def state_dependency_optimization(subchains: Dict[str, List[AbsElement]], target: str) -> Dict[str, List[AbsElement]]:
    incorrect_state_dependency = -1
    for i, element in enumerate(subchains[f"client_{target}"]):
        if element.prop["state"]["consistency"] in ["strong", "weak"] and element.position == "any" and element.prop["state"]["state_dependence"] == ["server_service"]:
            movable = True
            for j in range(i + 1, len(subchains[f"client_{target}"])):
                if subchains[f"client_{target}"][j].position != "any":
                    movable = False
            if movable:
                incorrect_state_dependency = i
                break
    if incorrect_state_dependency >= 0:
        c1, c2 = subchains[f"client_{target}"][:incorrect_state_dependency], subchains[f"client_{target}"][incorrect_state_dependency:]
        subchains[f"client_{target}"], subchains[f"server_{target}"] = c1, (c2 + subchains[f"server_{target}"])
    incorrect_state_dependency = -1
    for i, element in enumerate(subchains[f"server_{target}"]):
        if element.position != "any":
            break
        if element.prop["state"]["consistency"] in ["strong", "weak"] and element.position == "any" and element.prop["state"]["state_dependence"] == ["client_service"]:
            incorrect_state_dependency = i
    if incorrect_state_dependency >= 0:
        c1, c2 = subchains[f"server_{target}"][:incorrect_state_dependency + 1], subchains[f"server_{target}"][incorrect_state_dependency + 1]
        subchains[f"client_{target}"], subchains[f"server_{target}"] = (subchains[f"client_{target}"] + c1), c2 
    
    return subchains


def basic_heuristics(subchains: Dict[str, List[AbsElement]]) -> Dict[str, List[AbsElement]]:
    # heuristics: move more elements into cheap platform and processor
    # move elements into grpc
    while len(subchains["client_sidecar"]) > 0 and "grpc" in subchains["client_sidecar"][0].processor:
        element = subchains["client_sidecar"].pop(0)
        element.target = "grpc"
        subchains["client_grpc"].append(element)
    while len(subchains["server_sidecar"]) > 0 and "grpc" in subchains["server_sidecar"][-1].processor:
        element = subchains["server_sidecar"].pop()
        element.target = "grpc"
        subchains["server_grpc"].insert(0, element)
    # switch to native if possible
    keys = ["client_sidecar", "server_sidecar", "ambient"]
    for key in keys:
        for element in subchains[key]:
            if element.upgrade == "any" and "wasm" in element.target:
                element.target = element.target.replace("wasm", "native")
    # TODO: the state dependency optimization only support single-platform scenario for now
    if len(subchains["client_sidecar"]) + len(subchains["server_sidecar"]) + len(subchains["ambient"]) == 0:
        # grpc only
        subchains = state_dependency_optimization(subchains, "grpc")
    if len(subchains["client_grpc"]) + len(subchains["server_grpc"]) + len(subchains["ambient"]) == 0:
        # sidecar only
        subchains = state_dependency_optimization(subchains, "sidecar")
    
    for key, chain in subchains.items():
        for element in chain:
            element.final_position = key.split("_")[0]
    
    subchains = modify_sync_level(subchains)

    return subchains