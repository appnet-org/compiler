import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.istio_native.nativegen import NativeContext
from compiler.element.logger import ELEMENT_LOG as LOG


def codegen_from_template(output_dir, ctx: NativeContext, lib_name, proto_path):

    template_path = f"{COMPILER_ROOT}/element/backend/istio_native/template"

    # check if the template directory exists, if not, git clone.
    if os.path.exists(template_path) == False or len(os.listdir(template_path)) == 0:
        # git clone from git@github.com:appnet-org/envoy-appnet.git, master branch
        os.system(
            f"git clone git@github.com:appnet-org/envoy-appnet.git {template_path} --branch master"
        )
        LOG.info(f"New template cloned from git repo to {template_path}")

    # check if the output directory exists, if not, copy the template to the output directory
    # if the directory exists and non-empty, just rewrite the appnet_filter/appnet_filter.cc file and its .h file
    if os.path.exists(output_dir) == False or len(os.listdir(output_dir)) == 0:
        os.system(f"mkdir -p {output_dir}")
        os.system(
            f"bash -c 'cp -r {COMPILER_ROOT}/element/backend/istio_native/template/{{.,}}* {output_dir}'"
        )
        LOG.info(
            f"New template copied from {COMPILER_ROOT}/element/backend/istio_native/template to {output_dir}"
        )
    else:
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter.cc")
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter.h")
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter_config.cc")
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/istio_native/template/appnet_filter/appnet_filter.cc {output_dir}/appnet_filter/appnet_filter.cc"
        )
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/istio_native/template/appnet_filter/appnet_filter.h {output_dir}/appnet_filter/appnet_filter.h"
        )
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/istio_native/template/appnet_filter/appnet_filter_config.cc {output_dir}/appnet_filter/appnet_filter_config.cc"
        )

    if ctx.on_tick_code != []:
        # acquire the global_state_lock
        ctx.on_tick_code = [
            "std::unique_lock<std::mutex> lock(global_state_lock);"
        ] + ctx.on_tick_code

    if ctx.envoy_verbose:  # type: ignore
        ctx.insert_envoy_log()

    replace_dict = {
        "// !APPNET_STATE": ctx.global_var_def,
        "// !APPNET_INIT": ctx.init_code,
        "// !APPNET_REQUEST": ["{ // req header begin. "]
        + ctx.req_hdr_code
        + ["} // req header end."]
        + ["{ // req body begin. "]
        + ctx.req_body_code
        + ["} // req body end."],
        "// !APPNET_RESPONSE": ["{ // resp header begin. "]
        + ctx.resp_hdr_code
        + ["} // resp header end."]
        + ["{ // resp body begin. "]
        + ctx.resp_body_code
        + ["} // resp body end."],
        "// !APPNET_ONTICK": ctx.on_tick_code,
    }

    # rewrite appnet_filter/appnet_filter.cc according to the replace dict
    with open(f"{output_dir}/appnet_filter/appnet_filter.cc", "r") as file:
        appnet_filter = file.read()

    for key, value in replace_dict.items():
        appnet_filter = appnet_filter.replace(key, "\n".join(value))

    with open(f"{output_dir}/appnet_filter/appnet_filter.cc", "w") as file:
        file.write(appnet_filter)

    # remove .git to prevent strange bazel build behavior
    os.system(f"rm -rf {output_dir}/.git")

    # clang format
    os.system(f"clang-format -i {output_dir}/appnet_filter/appnet_filter.cc")

    # TODO: smarter way to define unique symbol name
    # Rename base64_encode and base64_decode to avoid symbol confliction
    files = [
        os.path.join(output_dir, "appnet_filter/appnet_filter.cc"),
        os.path.join(output_dir, "appnet_filter/thirdparty/base64.h"),
    ]
    for filename in files:
        with open(filename, "r") as f:
            content = f.read()
        content = content.replace("base64_encode", f"base64_encode_{lib_name}")
        content = content.replace("base64_decode", f"base64_decode_{lib_name}")
        with open(filename, "w") as f:
            f.write(content)

    LOG.info(
        f"Backend code for {lib_name} generated. You can find the source code at {output_dir}"
    )


def finalize(
    name: str, ctx: NativeContext, output_dir: str, placement: str, proto_path: str
):
    codegen_from_template(output_dir, ctx, name, proto_path)
