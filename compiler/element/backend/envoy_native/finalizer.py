import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.envoy_native.nativegen import NativeContext
from compiler.element.backend.envoy_native.nativetype import NativeGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG



def codegen_from_template(output_dir, ctx: NativeContext, lib_name, proto_path):


    # check if the output directory exists, if not, copy the template to the output directory
    # if the directory exists, just rewrite the appnet_filter/appnet_filter.cc file
    if os.path.exists(output_dir) == False:
        os.system(f"mkdir -p {output_dir}")
        os.system(f"bash -c 'cp -r {COMPILER_ROOT}/element/backend/envoy_native/template/{{.,}}* {output_dir}'")
    else:
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter.cc")
        os.system(f"cp {COMPILER_ROOT}/element/backend/envoy_native/template/appnet_filter/appnet_filter.cc {output_dir}/appnet_filter/appnet_filter.cc")

    replace_dict = {
        "// !APPNET_STATE": ctx.global_var_def,
        "// !APPNET_INIT": ctx.init_code,
        "// !APPNET_REQUEST": 
            ["{ // req header begin. "] 
                + ctx.req_hdr_code
            + ["} // req header end."]
            + ["{ // req body begin. "] 
                + ctx.req_body_code
            + ["} // req body end.`"],

        "// !APPNET_RESPONSE": 
            ["{ // resp header begin. "] 
                + ctx.resp_hdr_code
            + ["} // resp header end."]
            + ["{ // resp body begin. "] 
                + ctx.resp_body_code
            + ["} // resp body end."],
    }

    # rewrite appnet_filter/appnet_filter.cc according to the replace dict
    with open(f"{output_dir}/appnet_filter/appnet_filter.cc", "r") as file:
        appnet_filter = file.read()

    for key, value in replace_dict.items():
        appnet_filter = appnet_filter.replace(key, "\n".join(value))
        
    with open(f"{output_dir}/appnet_filter/appnet_filter.cc", "w") as file:
        file.write(appnet_filter)

    LOG.info(f"Backend code for {lib_name} generated. You can find the source code at {output_dir}")


def finalize(
    name: str, ctx: NativeContext, output_dir: str, placement: str, proto_path: str
):
    codegen_from_template(output_dir, ctx, name, proto_path)
