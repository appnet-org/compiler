import argparse
import datetime
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.absolute()))

from compiler import *
from compiler.config import COMPILER_ROOT
from compiler.element import compile_element_property, gen_code
from compiler.element.deploy import install, move_template
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.logger import init_logging

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e", "--element", type=str, help="(Element_name',') *", required=True
    )
    parser.add_argument("-v", "--verbose", help="Print Debug info", action="store_true")
    parser.add_argument(
        "-d",
        "--deploy",
        help="Deploy to the target directory",
        required=False,
        default=False,
    )
    parser.add_argument(
        "-p",
        "--placement",
        help="Placement of the generated code",
        required=True,
        default="c",
    )
    parser.add_argument(
        "-r",
        "--proto",
        type=str,
        help="Filename of the Protobuf definition (e.g., hello.proto)",
        required=True,
    )

    parser.add_argument(
        "-m",
        "--method_name",
        type=str,
        help="Method Name (must be defined in proto)",
        required=True,
    )
    parser.add_argument("-b", "--backend", help="Backend Code Target", required=True)
    init_logging(True)

    # Some preprocessing
    args = parser.parse_args()
    elements = args.element.split(",")
    backend = args.backend
    verbose = args.verbose
    deploy = args.deploy
    placement = args.placement
    proto_path = args.proto
    method_name = args.method_name
    server = proto_path.split(".")[0]
    if placement == "c" or placement == "client":
        placement = "client"
    elif placement == "s" or placement == "server":
        placement = "server"
    else:
        raise Exception("invalid Placement, c/s expected")
    LOG.info(f"Elements: {elements}, Backend: {backend}, Placement: {placement}")

    # Generate the element properties.
    start = datetime.datetime.now()
    ret = compile_element_property(elements, verbose=verbose, server=server)
    end = datetime.datetime.now()
    LOG.info(f"Element properties: {ret}")
    LOG.info(f"Property Analysis took: {(end-start).microseconds/1000}ms")

    # Check if proto file exists
    if not os.path.exists(proto_path):
        proto_path = os.path.join(
            root_base_dir,
            "examples/proto",
            proto_path,
        )

    # Generate real element code
    output_name = (
        "Gen" + "".join(elements).capitalize() + placement.lower().capitalize()
    )
    ret = gen_code(
        elements,
        output_name,
        str(COMPILER_ROOT) + "/generated/" + str(backend),
        backend,
        placement,
        proto_path,
        method_name,
        server,
        verbose,
    )
    end = datetime.datetime.now()
    LOG.info(f"Code Generation took: {(end-start).microseconds/1000}ms")

    if deploy:
        move_template("/home/banruo/phoenix", output_name)
        install([output_name], "/home/banruo/phoenix")
