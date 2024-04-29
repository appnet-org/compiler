import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.grpc import FUNC_REQ, FUNC_RESP
from compiler.element.backend.grpc.boilerplate import *
from compiler.element.backend.grpc.gogen import GoContext
from compiler.element.backend.grpc.gotype import GoGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG

def retrieve(ctx: GoContext, name: str, placement: str) -> Dict:
    #!todo init
    return {
        "FilterName": name,
        "GlobalVariables": ctx.gen_global_var_def(),
        "GlobalFuncDef": ";".join([f.definition for f in GoGlobalFunctions.values()]),
        "Init": "".join(ctx.init_code),
        "Request": "".join(ctx.req_code),
        "Response": "".join(ctx.resp_code),
        "ProtoName": ctx.proto,
        "ProtoModuleLocation": ctx.proto_module_location,
        # Import proto module if rpc accessed by element
        "ProtoImport": f"{ctx.proto} \"{ctx.proto_module_name}\"" if "rpc" in ctx.access_ops[FUNC_REQ] or "rpc" in ctx.access_ops[FUNC_RESP] else "",
        "ProtoModuleName": ctx.proto_module_name,
        "ClientInterceptor": "clientInterceptor()" if placement == "client" else "", # TODO(nikolabo): client vs server interceptor generation
        "ServerInterceptor": "serverInterceptor()" if placement == "server" else "",
    }

def codegen_from_template(output_dir: str, snippet: Dict, lib_name: str, placement: str):
    # This method generates the backend code from the template
    os.system(f"rm -rf {output_dir}")
    os.system(f"mkdir -p {output_dir}")

    with open(f"{output_dir}/interceptor.go", "w") as f:
        if placement == "client":
            f.write(client_interceptor.format(**snippet))
        else:
            # assert placement == "client"
            f.write(server_interceptor.format(**snippet))
    with open(f"{output_dir}/interceptinit.go", "w") as f:
        f.write(intercept_init.format(**snippet))
    with open(f"{output_dir}/go.mod", "w") as f:
        f.write(go_mod.format(**snippet))
    with open(f"{output_dir}/go.sum", "w") as f:
        f.write(go_sum.format(**snippet))
    with open(f"{output_dir}/build.sh", "w") as f:
        f.write(build_sh.format(**snippet))

    os.system(f"go fmt {output_dir}/interceptor.go")

    LOG.info(
        f"Backend code for {lib_name} generated. You can find the source code at {output_dir}"
    )

def finalize(
    name: str, ctx: GoContext, output_dir: str, placement: str, proto_path: str
):
    snippet = retrieve(ctx, name, placement)
    codegen_from_template(output_dir, snippet, name, placement)
