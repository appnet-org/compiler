import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.grpc.boilerplate import *
from compiler.element.backend.grpc.gogen import GoContext
from compiler.element.backend.grpc.gotype import GoGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG

def retrieve(ctx: GoContext, name: str) -> Dict:
    #!todo init
    return {
        "FilterName": name,
        "GlobalVariables": ctx.gen_global_var_def(),
        "GlobalFuncDef": ";".join([f.definition for f in GoGlobalFunctions.values()]),
        "Init": "".join(ctx.init_code),
        # "ProtoFuncDef": "".join([f for f in ctx.wasm_self_functions]),
        # "Init": "".join(ctx.init_code),
        # "OnTick": "".join(ctx.on_tick_code),
        "Request": "".join(ctx.req_code),
        "Response": "".join(ctx.resp_code),
        # "ExternalCallResponse": "".join(ctx.external_call_response_code),
        # "ProtoName": ctx.proto,
    }

def codegen_from_template(output_dir, snippet, lib_name, placement):
    # This method generates the backend code from the template
    os.system(f"rm -rf {output_dir}")
    os.system(f"mkdir -p {output_dir}")

    with open(f"{output_dir}/interceptor.go", "w") as f:
        if placement == "client":
            f.write(client_interceptor.format(**snippet))
        else:
            raise NotImplementedError

    os.system(f"go fmt {output_dir}/interceptor.go")

    LOG.info(
        f"Backend code for {lib_name} generated. You can find the source code at {output_dir}"
    )

def finalize(
    name: str, ctx: GoContext, output_dir: str, placement: str, proto_path: str
):
    snippet = retrieve(ctx, name)
    codegen_from_template(output_dir, snippet, name, placement)
