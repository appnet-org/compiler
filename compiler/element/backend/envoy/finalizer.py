import os
import sys
from pprint import pprint
from string import Formatter
from typing import Dict, List

from compiler.config import COMPILER_ROOT
from compiler.element.backend.envoy.boilerplate import *
from compiler.element.backend.envoy.wasmgen import WasmContext
from compiler.element.backend.envoy.wasmtype import WasmGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG


def retrieve(ctx: WasmContext, name: str) -> Dict:
    #!todo init
    return {
        "FilterName": name,
        "GlobalVariables": ctx.gen_global_var_def(),
        "Init": "".join(ctx.init_code),
        "RequestHeaders": "".join(ctx.req_hdr_code),
        "RequestBody": "".join(ctx.req_body_code),
        "ResponseHeaders": "".join(ctx.resp_hdr_code),
        "ResponseBody": "".join(ctx.resp_body_code),
    }


def gen_template(_placement, output_dir, snippet, lib_name):
    os.system(f"mkdir -p {output_dir}")
    with open(f"{output_dir}/lib.rs", "w") as f:
        f.write(lib_rs.format(**snippet))
    os.system(f"rustfmt --edition 2018  {output_dir}/lib.rs")
    LOG.info("Template {} generated".format(lib_name))


def finalize(name: str, ctx: WasmContext, output_dir: str, placement: str):
    snippet = retrieve(ctx, name)
    gen_template(placement, output_dir, snippet, name)
