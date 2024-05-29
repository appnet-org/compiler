import unittest
import subprocess
import sys
from pathlib import Path
import random
import colorlog
import os
import logging

sys.path.append(str(Path(__file__).parent.parent.absolute()))
APPNET_COMPILER_ROOT = Path(__file__).parent.parent
APPNET_ROOT = APPNET_COMPILER_ROOT.parent

from tests import *

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(asctime)s - %(message)s",
    )
)
logger.addHandler(stream_handler)
TEST_LOG = logging.getLogger("COMPILER TEST")

element_pool = [
    "cachestrong",
    "cacheweak",
    "aclstrong",
    "aclweak",
    "lbstickystrong",
    "lbstickyweak",
    "fault",
    "ratelimit",
    "logging",
    "mutation",
    "metrics",
    "admissioncontrol",
    "bandwidthlimit",
    "circuitbreaker",
    # "encryptping-decryptping",
]

apps = {
    "ping": {
        "proto_file": os.path.join(proto_base_dir, "ping.proto"),   
        "method_name": "PingEcho",
        "mod_name": "github.com/appnet-org/golib/sample/echo-pb",
        "mod_location": os.path.join(APPNET_ROOT, "go-lib/sample/ping-pb"),
    },
    # "reservation": {
    #     "proto_file": os.path.join(proto_base_dir, "reservation.proto"),   
    #     "method_name": "CheckAvailability",
    # },
    # "search": {
    #     "proto_file": os.path.join(proto_base_dir, "search.proto"),   
    #     "method_name": "Nearby",
    # },
    # "rate": {
    #     "proto_file": os.path.join(proto_base_dir, "rate.proto"),   
    #     "method_name": "GetRates",
    # },
    # "profile": {
    #     "proto_file": os.path.join(proto_base_dir, "profile.proto"),   
    #     "method_name": "GetProfiles",
    # },
    # "geo": {
    #     "proto_file": os.path.join(proto_base_dir, "geo.proto"),   
    #     "method_name": "Nearby",
    # },
}

backends = ["envoy", "grpc"]

class CompilerTestCase(unittest.TestCase):
    def generate_element_code(self, ename: str, backend: str, p: str, proto_file: str, method_name: str, mod_name: str = None, mod_location: str = None):
        command = [
            "python3.10", os.path.join(ROOT_DIR, "compiler/element_compiler_test.py"),
            "--element", ename,
            "--backend", backend,
            "--placement", p,
            "--proto", proto_file,
            "--method_name", method_name,
        ]
        if backend == "grpc":
            command.extend([ "--mod_name", mod_name, "--mod_location", mod_location])

        # print(" ".join(command))

        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result

    def compile_elements(self, backend):
        command = [
            "bash", os.path.join(ROOT_DIR, f"compiler/element/generated/{backend}/build.sh"),
        ]

        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result

    # Dynamically create a test method for each element
    def create_test_method(app, element, backend, proto_file, method_name, mod_name, mod_location):
        def test_method(self):
            # os.environ['ELEMENT_SPEC_BASE_DIR'] = os.path.join(ROOT_DIR, f"experiments/elements/{app}_elements")
            position_pool = ["client"] if backend == "envoy" else ["client", "server"]
            for position in position_pool:
                TEST_LOG.info(f"Testing {backend} backend: {app} element: {element} at position: {position}")
                
                # Generate element code
                result = self.generate_element_code(element, backend, position, proto_file, method_name, mod_name, mod_location)
                self.assertEqual(result.returncode, 0)
                self.assertIn('Code Generation took:', result.stderr)
                
                # Compile elements
                result = self.compile_elements(backend)
                self.assertEqual(result.returncode, 0)
                if backend == "envoy": self.assertIn("Finished", result.stderr)
        
        return test_method
    

# Dynamically add test methods to CompilerTestCase
for backend in backends:
    for app_name in apps.keys():
        for element in element_pool:
            test_method_name = f"test_{backend}_{app_name}_{element}_element_compilation"
            element_path = os.path.join(APPNET_COMPILER_ROOT, f"examples/elements/{app_name}_elements/{element}.appnet")
            app = apps[app_name]
            test_method = CompilerTestCase.create_test_method(app_name, element_path, backend, app["proto_file"], app["method_name"], app["mod_name"], app["mod_location"])
            setattr(CompilerTestCase, test_method_name, test_method)

if __name__ == "__main__":
    unittest.main()


