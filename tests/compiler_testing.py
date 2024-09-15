from copy import deepcopy
from pathlib import Path
from typing import List, Callable
import argparse
import os
import sys
import yaml

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler.graph.backend.utils import execute_local
from compiler.graph.logger import TEST_LOG, GRAPH_LOG, init_logging
from compiler import root_base_dir

element_tested = [
    "admissioncontrol",
    "bandwidthlimit",
    "cache",
    "cachestrong",
    "cacheweak",
    "circuitbreaker",
    "fault",
    "firewall",
    "firewallstrong",
    "firewallweak",
    "lbsticky",
    "lbstickystrong",
    "lbstickyweak",
    "logging",
    "metrics",
    "mutation",
    "ratelimit",
    "ratelimitstrong",
    "ratelimitweak",
]

yaml_template_echo = {
    "app_name": "echo",
    "app_manifest": "config/samples/echo/echo.yaml",
    "app_structure": [
        "frontend->server"
    ],
    "edge": {
        "frontend->server": []
    }
}

yaml_template_hotel = {
    "app_name": "hotel_reservation",
    "app_manifest": "config/samples/hotel/hotel_reservation.yaml",
    "app_structure": [
        "frontend->search",
        "frontend->reservation",
        "frontend->profile",
        "search->geo",
        "search->rate",
        "rate->memcached-rate",
        "rate->mongodb-rate",
        "reservation->memcached-reserve",
        "reservation->mongodb-reservation",
        "profile->memcached-profile",
        "profile->mongodb-profile",
        "geo->mongodb-geo",
    ],
    "edge": {
        "frontend->search": [],
        "search->geo": [],
        "search->rate": [],
        "frontend->profile": [],
    }
}

element_template_echo = {
    "method": "echo",
    "name": "TBD",
    "path": os.path.join(root_base_dir, "examples/elements/echo_elements"),
    "processor": [],
    "position": "any",
    "upgrade": True,
    "proto": "go-lib/sample/echo-pb/echo.proto",
    "proto_mod_name": "github.com/appnet-org/golib/sample/echo-pb",
    "proto_mod_location": "go-lib/sample/echo-pb",
}

element_template_hotel = {
    "method": "TBD",
    "name": "TBD",
    "path": os.path.join(root_base_dir, "examples/elements/SERVICE_elements"),
    "processor": [],
    "position": "any",
    "upgrade": True,
    "proto": os.path.join(root_base_dir, "examples/proto/SERVICE/SERVICE.proto"),
    "proto_mod_name": "github.com/appnet-org/compiler/examples/proto/SERVICE",
    "proto_mod_location": os.path.join(root_base_dir, "examples/proto/SERVICE"),
}

def make_element_dict_echo(element_name: str, appnet_root_dir: str, processor: List[str], is_native: bool, service: str) -> dict:
    element_dict = deepcopy(element_template_echo)
    element_dict["name"] = element_name
    element_dict["path"] = os.path.join(element_dict["path"], f"{element_name}.appnet")
    element_dict["processor"] = processor
    if is_native:
        element_dict["envoy_native"] = True
    for k, p in element_dict.items():
        if isinstance(p, str) and "go-lib" in p:
            element_dict[k] = os.path.join(appnet_root_dir, p)
    return element_dict


def make_spec_echo(elements: List[str], appnet_root_dir: str, processor: List[str], is_native: bool, service: str) -> dict:
    yaml_dict = deepcopy(yaml_template_echo)
    yaml_dict["app_manifest"] = os.path.join(appnet_root_dir, yaml_dict["app_manifest"])
    for element_name in elements:
        yaml_dict["edge"]["frontend->server"].append(make_element_dict_echo(element_name, appnet_root_dir, processor, is_native))
    return yaml_dict


def make_element_dict_hotel(element_name: str, appnet_root_dir: str, processor: List[str], is_native: bool, service: str) -> dict:
    if service in ["search", "geo"]:
        method_name = "Nearby"
    elif service == "profile":
        method_name = "GetProfiles"
    elif service == "rate":
        method_name = "GetRates"
    else:
        raise NotImplementedError
    element_dict = deepcopy(element_template_hotel)
    element_dict["name"] = element_name
    element_dict["method"] = method_name
    element_dict["path"] = os.path.join(element_dict["path"].replace("SERVICE", service), f"{element_name}.appnet")
    element_dict["processor"] = processor
    element_dict["proto"] = element_dict["proto"].replace("SERVICE", service)
    element_dict["proto_mod_name"] = element_dict["proto_mod_name"].replace("SERVICE", service)
    element_dict["proto_mod_location"] = element_dict["proto_mod_location"].replace("SERVICE", service)

    return element_dict


def make_spec_hotel(elements: List[str], appnet_root_dir: str, processor: List[str], is_native: bool, service: str) -> dict:
    yaml_dict = deepcopy(yaml_template_hotel)
    yaml_dict["app_manifest"] = os.path.join(appnet_root_dir, yaml_dict["app_manifest"])
    if service == "search":
        edge_name = "frontend->search"
    elif service == "geo":
        edge_name = "search->geo"
    elif service == "rate":
        edge_name = "search->rate"
    elif service == "profile":
        edge_name = "frontend->profile"
    else:
        raise NotImplementedError
    for element_name in elements:
        yaml_dict["edge"][edge_name].append(make_element_dict_hotel(element_name, appnet_root_dir, processor, is_native, service))
    return yaml_dict

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        choices=["compile", "compile_and_deploy"],
        default="compile"
    )
    parser.add_argument(
        "--comb",
        type=str,
        choices=["single", "double"],
        default="single"
    )
    parser.add_argument(
        "--app",
        type=str ,
        choices=["echo", "hotel"],
        default="echo"
    )
    parser.add_argument(
        "--service",
        type=str,
        choices=["", "search", "geo", "rate", "profile"],
        default=""
    )
    parser.add_argument(
        "--appnet_root_dir",
        type=str,
        default=os.path.join(os.path.expanduser("~"), "appnet")
    )
    parser.add_argument(
        "--processor",
        "-p",
        default="sidecar",
        choices=["grpc", "sidecar", "ambient"]
    )
    parser.add_argument(
        "--backend_mode", 
        "-b",
        default="wasm",
        choices=["wasm", "native"]
    )
    args = parser.parse_args()
    init_logging(False)

    if args.app == "hotel" and args.service == "":
        raise ValueError("No specified service")

    tmp_gen_dir = os.path.join(str(Path(__file__).parent), "tmp_gen")
    os.makedirs(tmp_gen_dir, exist_ok=True)

    element_group = args.app + f"-{args.service}" if args.service != "" else ""
    TEST_LOG.info(f"Testing {element_group}'s elements")
    success_elements, failed_elements = [], []
    if args.comb == "single":
        make_spec: Callable = globals()[f"make_spec_{args.app}"]
        for element_name in element_tested:
            TEST_LOG.info(f"testing {element_name}")
            yaml_dict = make_spec(
                [element_name],
                args.appnet_root_dir,
                [args.processor],
                True if args.backend_mode == "native" else False,
                args.service,
            )
            with open(os.path.join(tmp_gen_dir, f"{element_name}.yaml"), "w") as f:
                yaml.dump(yaml_dict, f, default_flow_style=False)
            try:
                execute_local([
                    "python3", 
                    os.path.join(root_base_dir, "compiler", "main.py"),
                    "-s",
                    os.path.join(tmp_gen_dir, f"{element_name}.yaml"),
                    "--opt_level",
                    "weak",
                ])
                TEST_LOG.info(f"{element_name} succeeded")
            except:
                TEST_LOG.critical(f"{element_name} failed")
                failed_elements.append(element_name)
    # TEST_LOG.info(f"failed elements: {failed_elements}")
    print(f"{failed_elements=}")
    # os.system(f"rm {tmp_gen_dir} -rf")