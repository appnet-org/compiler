import os
from typing import Dict, List

from compiler import *
from compiler.element.backend.grpc.analyzer import AccessAnalyzer as GoAccessAnalyzer
from compiler.element.backend.grpc.finalizer import finalize as GoFinalize
from compiler.element.backend.grpc.gogen import GoContext, GoGenerator
from compiler.element.backend.istio_native.finalizer import finalize as NativeFinalize
from compiler.element.backend.istio_native.nativegen import (
    NativeContext,
    NativeGenerator,
)
from compiler.element.backend.istio_wasm.analyzer import (
    AccessAnalyzer as WasmAccessAnalyzer,
)
from compiler.element.backend.istio_wasm.finalizer import finalize as WasmFinalize
from compiler.element.backend.istio_wasm.wasmgen import WasmContext, WasmGenerator
from compiler.element.backend.mrpc.finalizer import finalize as RustFinalize
from compiler.element.backend.mrpc.rustgen import RustContext, RustGenerator
from compiler.element.frontend import ElementCompiler
from compiler.element.frontend.printer import Printer
from compiler.element.frontend.util import (
    extract_message_field_types,
    extract_proto_message_names,
    extract_proto_package_name,
)
from compiler.element.ir.consolidate import consolidate
from compiler.element.ir.props.flow import FlowGraph, Property
from compiler.element.logger import ELEMENT_LOG as LOG


# TODO: unified naming convention for services in proto
def generate_service_name(mod_name: str, server: str) -> str:
    if "boutique" not in mod_name:
        return ""
    if "product" in server:
        return "ProductCatalogService"
    else:
        return server.capitalize() + "Service"


def gen_code(
    element_names: List[str],
    element_paths: List[str],
    output_name: str,
    output_dir: str,
    backend_name: str,
    placement: str,
    proto_path: str,
    method_name: str,
    server: str,
    tag: str,
    proto_module_name: str = "",
    proto_module_location: str = "",
    verbose: bool = False,
    envoy_verbose: bool = False,
) -> str:
    """
    Generates backend code.

    Args:
        element_names (List[str]): List of element names to generate code for.
        output_name (str): The name of the output file.
        output_dir (str): The directory where the output will be stored.
        backend_name (str): The name of the backend to be used (supports 'mrpc' or 'envoy').
        placement (str): The placement for the code generation.
        proto_path: (str):  The path to the proto file (e.g., hello.proto).
        method_name: (str): The name of the method to be used in the proto file.
        verbose (bool, optional): If True, provides detailed logging. Defaults to False.
        tag (str): The tag number for the current version.

    Raises:
        FileNotFoundError: If the proto file deos not exist.
        ValueError: If the method name does not exist in the proto file.
        AssertionError: If the backend_name is not in ['mrpc', 'envoy', 'grpc', 'ambient'].
    """

    # Check if the proto file and method name exists
    if not os.path.exists(proto_path):
        raise FileNotFoundError(f"The proto file {proto_path} does not exist.")

    with open(proto_path, "r") as file:
        proto_def = file.read()

        if method_name not in proto_def:
            raise ValueError(f"Method {method_name} not found in {proto_path}.")
    # proto = os.path.basename(proto_path).replace(".proto", "")
    proto = extract_proto_package_name(proto_path)

    assert backend_name in (
        "mrpc",
        "grpc",
        "sidecar_wasm",
        "sidecar_native",
        "ambient_wasm",
        "ambient_native",
    )
    compiler = ElementCompiler()

    # Find the request and response message names.
    service_name = generate_service_name(proto_module_name, server)
    request_message_name, response_message_name = extract_proto_message_names(
        proto_path, method_name, service_name=service_name
    )
    assert request_message_name is not None and response_message_name is not None

    # Create a mapping from message field names to their types
    message_field_types = extract_message_field_types(
        proto_path, request_message_name, response_message_name
    )
    # admission control uses a header field 'meta_status'
    message_field_types["response"]["meta_status"] = "string"

    # Choose the appropriate generator and context based on the backend
    if backend_name == "mrpc":
        generator = RustGenerator(placement)
        finalize = RustFinalize
        # TODO(XZ): Add configurable proto for mRPC codegen
        ctx = RustContext()
    elif "wasm" in backend_name:
        generator = WasmGenerator(placement)
        finalize = WasmFinalize
        # TODO(XZ): We assume there will be only one method being used in an element.
        ctx = WasmContext(
            proto=proto,
            method_name=method_name,
            element_name=output_name,
            request_message_name=request_message_name,
            response_message_name=response_message_name,
            message_field_types=message_field_types,
            mode=backend_name,
            tag=tag,
        )
    elif backend_name == "grpc":
        assert proto_module_name != "" and proto_module_location != ""
        generator = GoGenerator(placement)
        finalize = GoFinalize
        ctx = GoContext(
            proto=proto,
            proto_module_name=proto_module_name,
            proto_module_location=proto_module_location,
            method_name=method_name,
            element_name=output_name,
            request_message_name=request_message_name,
            response_message_name=response_message_name,
            message_field_types=message_field_types,
            tag=tag,
        )
    elif "native" in backend_name:
        generator = NativeGenerator(placement)
        finalize = NativeFinalize
        ctx = NativeContext(
            proto=proto,
            method_name=method_name,
            request_message_name=request_message_name,
            response_message_name=response_message_name,
            message_field_types=message_field_types,
            mode="sidecar",
            element_name=output_name,
            tag=tag,
            envoy_verbose=envoy_verbose,
        )

    printer = Printer()

    # Generate element IR for each element.
    eirs = []
    for element_name, element_path in zip(element_names, element_paths):
        LOG.info(f"(CodeGen) Parsing {element_name}")

        with open(element_path, "r") as f:
            spec = f.read()
            ir = compiler.parse_and_transform(spec)
            if verbose:
                p = ir.accept(printer, None)
                print("showing IR:")
                print(p)
            eirs.append(ir)

    # Consolidate IRs if multiple engines are specified
    if len(element_names) > 1:
        LOG.info(f"Consolidating IRs for {element_names}")
        consolidated = consolidate(eirs)
        if verbose:
            p = consolidated.accept(printer, None)
            LOG.info("Consolidated IR:")
            print(p)
    else:
        consolidated = eirs[0]

    LOG.info(f"Generating {backend_name} code")
    # TODO: Extend access analysis to all backends
    if "wasm" in backend_name:
        assert isinstance(ctx, WasmContext), "Inconsistent context type"
        # Do a pass to analyze the IR and generate the access operation
        consolidated.accept(WasmAccessAnalyzer(placement), ctx)
    elif backend_name == "grpc":
        assert isinstance(ctx, GoContext), "Inconsistent context type"
        consolidated.accept(GoAccessAnalyzer(placement), ctx)
    elif "native" in backend_name:
        pass

    # Second pass to generate the code
    consolidated.accept(generator, ctx)

    # Finalize the generated code
    finalize(output_name, ctx, output_dir, placement, proto_path)


def compile_element_property(
    element_names: List[str],
    element_paths: List[str],
    verbose: bool = False,
    server: str = "",
) -> Dict:
    """
    Compiles and analyzes properties of elements defined using AppNet syntax.

    Each .appnet file contains the specification of an element's behavior. The function
    uses an ElementCompiler to compile these specifications into an intermediate representation (IR),
    and then analyzes the properties of the request and response flows using FlowGraph.

    The function aggregates properties (like read, write, block, copy, drop operations) for
    both request and response flows across all the provided element specifications. It also
    determines if the overall behavior is stateful based on the state definitions in the IR.

    If 'verbose' is true, it prints the compiled intermediate representation for each element.

    Args:
        element_names (List[str]): List of element names for which to compile and analyze properties.
        verbose (bool): Flag to enable verbose logging of the compilation process.

    Returns:
        Dict: A dictionary containing the stateful flag, and the aggregated properties for
              both request and response processing.
    """
    compiler = ElementCompiler()
    printer = Printer()

    # Initialize a tuple of Property objects to hold request and response properties
    LOG.info(f"Analyzing element properties. Element list: {element_names}")
    ret = (Property(), Property())

    # Default properties
    stateful = False
    consistency = None
    combiner = "LWW"
    persistence = False
    state_dependence = []

    for element_name, element_path in zip(element_names, element_paths):
        LOG.info(f"(Property Analyzer) Parsing {element_name}")

        with open(element_path) as f:
            # Read the specification from file and generate the intermediate representation
            spec = f.read()
            ir = compiler.parse_and_transform(spec)

            if verbose:
                p = ir.accept(printer, None)
                print(p)

            # Analyze the IR and get the element properties
            # The request and reponse logics are analyzed seperately
            req = FlowGraph().analyze(ir.req, verbose)
            resp = FlowGraph().analyze(ir.resp, verbose)

            # Update request properties
            ret[0].block = ret[0].block or req.block
            ret[0].copy = ret[0].copy or req.copy
            ret[0].drop = ret[0].drop or req.drop
            ret[0].read = ret[0].read + req.read
            ret[0].write = ret[0].write + req.write
            ret[0].check()  # XZ: what does check do?

            # Update response properties
            ret[1].block = ret[1].block or resp.block
            ret[1].copy = ret[1].copy or resp.copy
            ret[1].drop = ret[1].drop or resp.drop
            ret[1].read = ret[1].read + resp.read
            ret[1].write = ret[1].write + resp.write
            ret[1].check()

            stateful = stateful or len(ir.definition.state) > 0

            # TODO: might want want to do a more fine-grained check state variables. (incl. conflict requirements)
            for state in ir.definition.state:
                consistency = consistency or state[2].name
                # TODO: this won't work if we use the combiner in the future
                combiner = combiner or state[3].name
                persistence = persistence or state[4].name
                # TODO: this is a temp hack
                if "client_service" in state[0].name:
                    state_dependence.append("client_service")
                if "server_service" in state[0].name:
                    state_dependence.append("server_service")

    ret[0].check()
    ret[1].check()

    # Determine if the operation should be recorded based on the element name
    # TODO(xz): this is a temporary hack.
    record = len(element_names) == 1 and (
        element_names[0] == "logging" or element_names[0] == "metrics"
    )

    return {
        "state": {
            "stateful": stateful,
            "consistency": consistency,
            "combiner": combiner,
            "persistence": persistence,
            "state_dependence": state_dependence,
        },
        "request": {
            "record" if record else "read": ret[0].read,
            "write": ret[0].write,
            "drop": ret[0].drop,
            "block": ret[0].block,
            "copy": ret[0].copy,
        },
        "response": {
            "record" if record else "read": ret[1].read,
            "write": ret[1].write,
            "drop": ret[1].drop,
            "block": ret[1].block,
            "copy": ret[1].copy,
        },
    }
