import argparse
import datetime
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler import *
from compiler.config import COMPILER_ROOT
from compiler.element import compile_element_property, gen_code
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.logger import init_logging

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e", "--element_path", type=str, help="(Element_path',') *", required=True
    )
    parser.add_argument("-v", "--verbose", help="Print Debug info", action="store_true")
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
    parser.add_argument(
        "-l",
        "--mod_location",
        help="Go Protobuf Module Location",
        type=str,
        required=False,
        default=False,
    )
    parser.add_argument(
        "-n",
        "--mod_name",
        help="Go Protobuf Module Name",
        type=str,
        required=False,
        default="",
    )
    init_logging(True)

    # Some preprocessing
    args = parser.parse_args()
    element_path = args.element_path
    element_name = os.path.splitext(os.path.basename(element_path))[0]
    backend = args.backend
    verbose = args.verbose
    placement = args.placement
    proto_path = args.proto
    proto_module_location = args.mod_location
    proto_module_name = args.mod_name
    method_name = args.method_name
    server = proto_path.split(".")[0]
    if placement == "c" or placement == "client":
        placement = "client"
    elif placement == "s" or placement == "server":
        placement = "server"
    else:
        raise Exception("invalid Placement, c/s expected")
    LOG.info(f"Element: {element_name}, Backend: {backend}, Placement: {placement}")

    # Generate the element properties.
    start = datetime.datetime.now()
    ret = compile_element_property(element_name, element_path, verbose=verbose)
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
    output_name = "Gen" + element_name.capitalize() + placement.lower().capitalize()
    ret = gen_code(
        [element_name],
        [element_path],
        output_name,
        os.path.join(str(COMPILER_ROOT), "element", "generated", str(backend)),
        backend,
        placement,
        proto_path,
        method_name,
        server,
        proto_module_name=proto_module_name,
        proto_module_location=proto_module_location,
        verbose=verbose,
        tag="0",
    )
    end = datetime.datetime.now()
    LOG.info(f"Code Generation took: {(end-start).microseconds/1000}ms")

