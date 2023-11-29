import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element import compile_element_property, gen_code
from compiler.element.backend.finalizer import finalize
from compiler.element.backend.rustgen import RustContext, RustGenerator
from compiler.element.frontend import IRCompiler, Printer
from compiler.element.props.flow import FlowGraph
from compiler.element.logger import ELEMENT_LOG, init_logging
from compiler.element.deploy import install, move_template

if __name__ == "__main__":

    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e", "--engine", type=str, help="(Engine_name ',') *", required=True
    )
    parser.add_argument(
        "-v", "--verbose", help="Print Debug info", required=False, default=False
    )
    
    init_logging(True)
    # parser.add_argument("--verbose", help="Print Debug info", action="store_true")
    # parser.add_argument(
    #     "--mrpc_dir",
    #     type=str,
    #     default=f"../../phoenix/experimental/mrpc",
    # )
    # parser.add_argument(
    #     "-o", "--output", type=str, help="Output type: ast, ir, mrpc", default="mrpc"
    # )
    args = parser.parse_args()
    engine = args.engine
    verbose = args.verbose

    # ret = compile_element(engine, verbose)
    # pprint(ret)
    output_name = "gen" + engine + "receiver"
    ret = gen_code(engine, output_name, str(COMPILER_ROOT) + "/generated", "mrpc", "receiver", verbose)
    move_template("/home/banruo/phoenix", output_name)
    install([output_name], "/home/banruo/phoenix")