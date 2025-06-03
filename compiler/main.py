import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

import yaml
from rich.columns import Columns
from rich.console import Console

# set up $PYTHONPATH and environment variables
sys.path.append(str(Path(__file__).parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.absolute()))
os.environ["PHOENIX_DIR"] = os.path.join(os.getenv("HOME"), "phoenix")

from compiler import *
from compiler.element import gen_code
from compiler.graph.backend import scriptgen
from compiler.graph.frontend import GraphParser
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_LOG, init_logging
from compiler.graph.pseudo_element_compiler import pseudo_compile

console = Console()
gir_summary = dict()


def parse_args():
    # Parse command line arguments
    parser = argparse.ArgumentParser()

    # Arguments for users
    parser.add_argument(
        "-s",
        "--spec_path",
        help="Path to user specification file.",
        type=str,
        required=True,
    )  
    parser.add_argument(
        "--opt_level",
        help="""Optimization level, default is weak.
                no: no optimization;
                ignore: aggresive, ignore equivalence requirements;
                weak: allow differences in drop rate, records, etc.;
                strong: strict equivalence.""",
        type=str,
        choices=["no", "ignore", "weak", "strong"],
        default="weak",
        # no: no optimization
        # ignore: aggresive, ignore equivalence requirements
        # weak: allow differences in drop rate, records, etc.
        # strong: strict equivalence
    )
    parser.add_argument(
        "--replica",
        type=str,
        help="the number of replicas for each service, default is 1.",
        default="1",
    )
    parser.add_argument(
        "-t",
        "--tag",
        help="Tag number for the current version, used for seamless upgrades. Usually users don't need to manually configure this.",
        type=str,
        default="1",
    )

    # Arguments for developers
    parser.add_argument(
        "-v",
        "--verbose",
        help="[Dev] If added, request graphs (i.e., element chains) on each edge will be printed on the terminal.",
        action="store_true",
    )
    parser.add_argument(
        "--envoy_verbose",
        help="[Dev] If added, verbose logging will be generated in envoy native filter.",
        action="store_true",
    )
    parser.add_argument(
        "--pseudo_property",
        help="[Dev] If added, use hand-coded properties instead of auto-generated ones.",
        action="store_true",
    )
    parser.add_argument(
        "--pseudo_impl",
        help="[Dev] If added, use hand-coded implementations instead of auto-generated ones.",
        action="store_true",
    )
    parser.add_argument(
        "--dry_run",
        help="[Dev] If added, the compilation terminates after optimization (i.e., no backend scriptgen).",
        action="store_true",
    )
    parser.add_argument(
        "--dump_property",
        help="[Dev] If added, dump the properties of each element in yaml format.",
        action="store_true",
    ) 
    parser.add_argument(
        "--opt_algorithm",
        type=str,
        help="[Dev] Optimization algorithm, default is cost. If heuristics is chosen, only intra-element optimizations (i.e., placement and processor changes) will be applied.",
        choices=["cost", "heuristics"],
        default="cost",
    )
    parser.add_argument("--debug", help="[Dev] Print debug info.", action="store_true")

    return parser.parse_args()


def compile_impl(
    element_names: str,
    element_paths: str,
    gen_dir: str,
    backend: str,
    placement: str,
    proto_path: str,
    method: str,
    server: str,
    tag: str,
    proto_module_name: str = "",
    proto_module_location: str = "",
):
    gen_name = (
        server + "".join(element_names)[:24]
    )  # Envoy does not allow long struct names
    os.system(f"mkdir -p {gen_dir}")
    gen_code(
        element_names,
        element_paths,
        gen_name,
        gen_dir,
        backend,
        placement,
        proto_path,
        method,
        server,
        tag,
        proto_module_name=proto_module_name,
        proto_module_location=proto_module_location,
        verbose=False,
        envoy_verbose=args.envoy_verbose,
    )


def generate_element_impl(graphirs: Dict[str, GraphIR], pseudo_impl: bool):
    compiled_name = set()
    gen_dir = os.path.join(graph_base_dir, "generated")
    os.system(f"rm {gen_dir} -rf")
    for gir in graphirs.values():  # For each edge in the application
        for element in gir.complete_chain():
            # For each element in the edge
            identifier = element.lib_name + element.final_position
            gen_name = element.server + "".join(element.name)[:24]
            if element.target in ["mrpc", "grpc"]:
                element.compile_dir = os.path.join(
                    gen_dir, f"{gen_name}_{element.final_position}_{element.target}"
                )
            else:
                element.compile_dir = os.path.join(
                    gen_dir, f"{gen_name}_{element.target}"
                )
            if identifier not in compiled_name:
                if pseudo_impl:
                    pseudo_compile(
                        element.lib_name,
                        gen_dir,
                        element.target,
                        element.final_position,
                    )
                else:
                    compile_impl(
                        element.name,
                        element.path,
                        element.compile_dir,
                        element.target,
                        element.final_position,
                        element.proto,
                        element.method,
                        gir.server,
                        args.tag,
                        proto_module_name=element.proto_mod_name,
                        proto_module_location=element.proto_mod_location,
                    )
                compiled_name.add(identifier)


def print_gir_summary(graphirs: Dict[str, GraphIR]):
    GRAPH_LOG.info("Graph IR summary:")
    for gir in graphirs.values():
        gir_summary[gir.name]["post-optimized"] = gir.to_rich()

    for gname, summary in gir_summary.items():
        console.print()
        console.print(gname, style="underline bold italic")
        console.print(Columns(["\n :snail: :\n"] + summary["pre-optimized"]))
        console.print(Columns(["\n :rocket: :\n"] + summary["post-optimized"]))


def replace_state(lst, state_name):
    strong_found = False
    for i in range(len(lst)):
        if "strong" in lst[i]:
            if strong_found:
                lst[i] = lst[i].replace(state_name, "")
            else:
                strong_found = True
    return lst


def handle_state(graphirs: Dict[str, GraphIR]):
    for gir in graphirs.values():
        for chain in gir.elements.values():
            for element in chain:
                replace_state(element.name, "strong")
                replace_state(element.path, "strong")
                replace_state(element.name, "weak")
                replace_state(element.path, "weak")


def main(args):
    # Step 1: Parse the spec file and generate graph IRs (see examples/chain for details about spec format)
    GRAPH_LOG.info(f"Parsing graph spec file {args.spec_path}...")
    parser = GraphParser()
    graphirs, app_name, app_manifest_file, app_edges = parser.parse(args.spec_path)

    if args.verbose:
        for gir in graphirs.values():
            if gir.name not in gir_summary:
                gir_summary[gir.name] = {"pre-optimized": [], "post-optimized": []}
            gir_summary[gir.name]["pre-optimized"] = gir.to_rich()

    # Step 2: Extract element properties via element compiler and optimize the graph IR.
    GRAPH_LOG.info("Generating element properties and optimizing the graph IR...")
    for gir in graphirs.values():
        # Each gir represests an edge in the application (a pair of communicating services)
        # pseudo_property is set to True when we want to use user-provided properties instead of auto-generated ones
        for element in gir.complete_chain():
            element.set_property_source(args.pseudo_property)
        gir.optimize(args.opt_level, args.opt_algorithm, args.dump_property)
    
    if args.opt_level != "no":
        handle_state(graphirs)

    # Step 3: Generate backend code for the elements and deployment scripts.
    if not args.dry_run:
        GRAPH_LOG.info(
            "Generating backend code for the elements and deployment scripts..."
        )
        # Step 3.1: Generate backend code for the elements
        # pseudo_impl is set to True when we want to use user-provided implementations instead of auto-generated ones
        generate_element_impl(graphirs, args.pseudo_impl)
        # Step 3.2: Generate deployment scripts
        scriptgen(graphirs, app_name, app_manifest_file, app_edges)

    # Dump graphir summary (in yaml)
    gen_dir = os.path.join(graph_base_dir, "generated")
    os.makedirs(gen_dir, exist_ok=True)

    graphir_summary = ""
    for gir in graphirs.values():
        graphir_summary += str(gir)
    print(graphir_summary)
    graphir_summary_dict = {}
    for edge_name, gir in graphirs.items():
        graphir_summary_dict[edge_name] = gir.export_summary()
        
    # We should safe them as yaml file, but it messes up the kubectl apply command.
    with open(os.path.join(gen_dir, "gir_summary"), "w") as f:
        yaml.safe_dump(graphir_summary_dict, f, default_flow_style=False)

    # Display a rich-formatted comparison of pre and post-optimized GraphIRs in the terminal
    if args.verbose:
        print_gir_summary(graphirs)


if __name__ == "__main__":
    args = parse_args()
    init_logging(args.debug)

    os.environ["SERVICE_REPLICA"] = args.replica
    if args.dry_run:
        os.environ["DRY_RUN"] = "1"
    if args.opt_level == "no":
        os.environ["APPNET_NO_OPTIMIZE"] = "1"

    main(args)
