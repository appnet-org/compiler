import os
from typing import Dict

from compiler import root_base_dir
from compiler.ir.frontend import IRCompiler, Printer
from compiler.ir.props.flow import FlowGraph


def compile_element_property(engine_name: str, verbose: bool = False) -> Dict:
    compiler = IRCompiler()
    printer = Printer()

    with open(os.path.join(root_base_dir, f"elements/ir/{engine_name}.adn")) as f:
        spec = f.read()
        ir = compiler.compile(spec)
        p = ir.accept(printer, None)
        if verbose:
            print(p)

        req = FlowGraph().analyze(ir.req, verbose)
        resp = FlowGraph().analyze(ir.resp, verbose)

        yaml = "request:\n" + req.to_yaml() + "response:\n" + resp.to_yaml()
        if verbose:
            print(yaml)
        return {
            "request": {
                "read": req.read,
                "write": req.write,
                "drop": req.drop,
            },
            "response": {
                "read": resp.read,
                "write": resp.write,
                "drop": resp.drop,
            },
        }
