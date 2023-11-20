import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.ir import compile_element_property, gen_code
from compiler.ir.backend.finalizer import finalize
from compiler.ir.backend.rustgen import RustContext, RustGenerator
from compiler.ir.frontend import IRCompiler, Printer
from compiler.ir.props.flow import FlowGraph

if __name__ == "__main__":

    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e", "--engine", type=str, help="(Engine_name ',') *", required=True
    )
    parser.add_argument(
        "-v", "--verbose", help="Print Debug info", required=False, default=False
    )
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

    ret = gen_code(engine, "fault2", str(COMPILER_ROOT) + "/generated", "mrpc", verbose)
