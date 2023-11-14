import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict

from compiler.ir.frontend import IRCompiler, Printer
from compiler.ir.props.flow import FlowGraph


def compile_element(engine_name: str, verbose: bool = False) -> Dict:
    compiler = IRCompiler()
    printer = Printer()

    with open(f"../elements/ir/{engine_name}.adn") as f:
        spec = f.read()
        ir = compiler.compile(spec)
        p = ir.accept(printer, None)
        if verbose:
            print(p)

        req = FlowGraph().analyze(ir.req, verbose)
        resp = FlowGraph().analyze(ir.resp, verbose)

        return {
            "request": {
                "read": req.read,
                "write": req.write,
                "drop": req.drop,
                "copy": req.copy,
            },
            "response": {
                "read": resp.read,
                "write": resp.write,
                "drop": resp.drop,
                "copy": resp.copy,
            },
        }


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

    ret = compile_element(engine, verbose)
    print(ret)