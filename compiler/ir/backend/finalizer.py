import os
import sys
from string import Formatter
from typing import Dict, List
from compiler.ir.backend.boilerplate import *
from compiler.ir.backend.rustgen import RustContext
from compiler.ir.backend.rusttype import RustGlobalFunctions
from compiler.ir.backend.protobuf import HelloProto
from compiler.config import COMPILER_ROOT
from pprint import pprint
# name: table_rpc_events
# type: Vec<struct_rpc_events>
# init: table_rpc_events = Vec::new()

def gen_global_function_includes() -> str:
    prefix = "use crate::engine::{"
    middle = ""
    for (k, v) in RustGlobalFunctions.items():
        name = v.name
        middle += f"{name},"
    suffix = "};"
    return prefix + middle + suffix

def gen_def() -> List[str]:
    ret = []
    for _, func in RustGlobalFunctions.items():
        ret.append(func.gen_def())
    ret = ret + HelloProto.gen_readonly_def()
    return ret

def retrieve_info(ctx: RustContext):
    proto = "hello"
    proto_fc = "Hello"
    def_code = gen_def();
    info = {
        "ProtoDefinition": proto,
        # todo! field name should be configurable
        # todo! multiple type should be supported
        "ProtoGetters": f"""
        """,
        "ProtoRpcRequestType": f"{proto}::{proto_fc}Request",
        "ProtoRpcResponseType": f"{proto}::{proto_fc}Response",
        "GlobalFunctionInclude": gen_global_function_includes(),
        "InternalStatesDefinition": "\n".join(gen_def()),
        "InternalStatesDeclaration": "\n".join(
            [f"use crate::engine::{i};" for i in ctx.gen_struct_names()]
        ),
        "InternalStatesOnBuild": "\n".join(ctx.gen_init_localvar())
        + "\n".join(ctx.init_code),
        "InternalStatesOnRestore": "\n".join(ctx.gen_init_localvar())
        + "\n".join(ctx.init_code),
        "InternalStatesOnDecompose": "",
        "InternalStatesInConstructor": "\n".join(
            [f"{i}," for i in ctx.gen_internal_names()]
        ),
        "InternalStatesInStructDefinition": "\n".join(
            [f"pub(crate) {i}," for i in ctx.gen_struct_declaration()]
        ),
        "RpcRequest": "".join(ctx.req_code),
        # !todo resp
        "RpcResponse": ""#"".join(ctx.resp_code),
    }
    # for k,v in info.items():
    #     print(k)
    #     print(v)
    return info

def gen_template(
    ctx,
    template_name,
    template_name_toml,
    template_name_first_cap,
    template_name_all_cap,
):
    target_dir = os.path.join(COMPILER_ROOT, f"generated/{template_name}")
    os.system(f"rm -rf {target_dir}")
    os.system(f"mkdir -p {target_dir}")
    os.chdir(target_dir)
    ctx["TemplateName"] = template_name
    ctx["TemplateNameFirstCap"] = template_name_first_cap
    ctx["TemplateNameAllCap"] = template_name_all_cap
    ctx["TemplateNameCap"] = template_name_first_cap
    # print("Current dir: {}".format(os.getcwd()))
    with open("config.rs", "w") as f:
        f.write(config_rs.format(Include=include, **ctx))
    with open("lib.rs", "w") as f:
        f.write(lib_rs.format(Include=include, **ctx))
    with open("module.rs", "w") as f:
        f.write(module_rs.format(Include=include, **ctx))
    with open("engine.rs", "w") as f:
        # print([i[1] for i in Formatter().parse(engine_rs)  if i[1] is not None])
        f.write(engine_rs.format(Include=include, **ctx))
    with open("proto.rs", "w") as f:
        f.write(proto_rs)
    with open("Cargo.toml.api", "w") as f:
        f.write(api_toml.format(TemplateName=template_name_toml))
    with open("Cargo.toml.policy", "w") as f:
        f.write(policy_toml.format(TemplateName=template_name_toml))
    
    
    os.system(f"rustfmt --edition 2018  ./config.rs")
    os.system(f"rustfmt --edition 2018  ./lib.rs")
    os.system(f"rustfmt --edition 2018  ./module.rs")
    os.system(f"rustfmt --edition 2018  ./engine.rs")
    os.system(f"rustfmt --edition 2018  ./proto.rs")
    
    print("Template {} generated".format(template_name))


def move_template(
    mrpc_root, template_name, template_name_toml, template_name_first_cap
):
    mrpc_api = mrpc_root + "/generated/api"
    original_api = mrpc_root + "/phoenix-api/policy"

    os.system("mkdir -p {}".format(mrpc_api))

    os.system(f"rm -rf {mrpc_api}/{template_name_toml}")
    os.system(f"cp -r {original_api}/logging {mrpc_api}/{template_name_toml}")
    os.system(f"rm {mrpc_api}/{template_name_toml}/Cargo.toml")
    os.system(f"cp ./Cargo.toml.api {mrpc_api}/{template_name_toml}/Cargo.toml")

    mrpc_plugin = mrpc_root + "/generated/plugin"
    os.system("mkdir -p {}".format(mrpc_plugin))

    os.system(f"rm -rf {mrpc_plugin}/{template_name_toml}")
    os.system(f"mkdir -p {mrpc_plugin}/{template_name_toml}/src")
    os.system(f"cp ./Cargo.toml.policy {mrpc_plugin}/{template_name_toml}/Cargo.toml")


    os.system(f"cp ./config.rs {mrpc_plugin}/{template_name_toml}/src/config.rs")
    os.system(f"cp ./lib.rs {mrpc_plugin}/{template_name_toml}/src/lib.rs")
    os.system(f"cp ./module.rs {mrpc_plugin}/{template_name_toml}/src/module.rs")
    os.system(f"cp ./engine.rs {mrpc_plugin}/{template_name_toml}/src/engine.rs")
    os.system(f"cp ./proto.rs {mrpc_plugin}/{template_name_toml}/src/proto.rs")
    print("Template {} moved to mrpc folder".format(template_name))


def gen_attach_detach(name: str, ctx):
    with open(f"{name}_attach.toml", "w") as f:
        f.write(attach_toml.format(**ctx))

    with open(f"{name}_detach.toml", "w") as f:
        f.write(detach_toml.format(**ctx))


def finalize(name: str, ctx: RustContext, output_dir: str):
    if name == "logging":
        template_name = "file_logging"
        template_name_toml = "file-logging"
        template_name_first_cap = "FileLogging"
        template_name_all_cap = "FILE_LOGGING"
    elif name == "acl":
        template_name = "hello_acl"
        template_name_toml = "hello-acl"
        template_name_first_cap = "HelloAcl"
        template_name_all_cap = "HELLO_ACL"
    elif name == "fault":
        template_name = "fault"
        template_name_toml = "fault"
        template_name_first_cap = "Fault"
        template_name_all_cap = "FAULT"
    else:
        name = name.split("_")
        template_name = "_".join(name)
        template_name_toml = "-".join(name)
        cap = [i[0].upper() + i[1:] for i in name]
        template_name_first_cap = "".join(cap)
        template_name_all_cap = "_".join(name).upper()

    info = retrieve_info(ctx)
    gen_template(
        info,
        template_name,
        template_name_toml,
        template_name_first_cap,
        template_name_all_cap,
    )
    return;
    move_template(
        output_dir,
        template_name,
        template_name_toml,
        template_name_first_cap,
    )


def finalize_graph(ctx: Dict[str, object], mrpc_dir: str):
    output_dir = f"{mrpc_dir}/generated"
    os.chdir(COMPILER_ROOT)

    os.system("rm -rf ./generated/addonctl")
    os.system("mkdir ./generated/addonctl")
    os.chdir("./generated/addonctl")
    for k, v in ctx.items():
        gen_attach_detach(k, v)
        print(f"Generated {k} attach/detach toml")
    os.chdir(COMPILER_ROOT)

    os.system(f"rm -rf {output_dir}/addonctl")
    os.system(f"mkdir -p {output_dir}/addonctl")
    os.system(f"cp -r ./generated/addonctl {output_dir}/")
