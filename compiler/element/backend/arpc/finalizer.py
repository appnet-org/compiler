import os
from typing import Dict

from compiler.element.backend.arpc.gogen import ArpcContext
from compiler.element.backend.arpc.template import sidecar_arpc_template

def retrieve(ctx: ArpcContext) -> Dict[str, str]:
    return {
        "Imports": f"{ctx.proto.package_name} \"{ctx.proto_module_name}\"\n",
        "ElementName": ctx.element_name,
        "GlobalVarDec": "\n".join(ctx.global_var_dec),
        "GlobalVarInit": "\n".join(ctx.global_var_init),
        "InitCode": "\n".join(ctx.procedure_code["init"]),
        "ReqCode": "\n".join(ctx.procedure_code["req"]),
        "RespCode": "\n".join(ctx.procedure_code["resp"]),
        "GlobalFunc": "\n".join(ctx.global_var_helper_code.values()) + "\n" + "\n".join(ctx.global_func_code),
    }

def codegen_from_template(output_dir: str, snippet: Dict[str, str], gen_name: str, placement: str):
    os.system(f"mkdir -p {output_dir}")
    with open(f"{output_dir}/element.go", "w") as f:
        f.write(sidecar_arpc_template.format(**snippet))
    os.system(f"goimports -w {output_dir}")

def finalize(gen_name: str, ctx: ArpcContext, output_dir: str, placement: str, proot_path: str):
    snippet = retrieve(ctx)
    codegen_from_template(output_dir, snippet, gen_name, placement)