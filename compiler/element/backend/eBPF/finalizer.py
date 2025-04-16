import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.eBPF.nativegen import eBPFContext
from compiler.element.logger import ELEMENT_LOG as LOG

from compiler.element.backend.eBPF.getkubernetes import *

from compiler.element.backend.eBPF.types import *

def gen_map_access(name : str, idx : int, ctx) -> str:
    """
    u32 {src/dst}Pod{idx}IP_key = 0;
    u32 {src/dst}Pod{idx}IP = 0;
    u32 *{src/dst}Pod{idx}Value = {src/dst}_pod.lookup(&{src/dst}Pod{idx}IP_key);
    if ({src/dst}Pod{idx}Value) {
        {src/dst}Pod{idx}IP = (*{src/dst}Pod{idx}Value);
    }
    """
    ret_val = ""
    ret_val += f"u32 {name}Pod{idx}IP_key = 0;\n"
    ret_val += f"u32 {name}Pod{idx}IP = 0;\n"
    ret_val += f"u32 *{name}Pod{idx}Value = {name}_pod.lookup(&{name}Pod{idx}IP_key);\n"
    ret_val += f"if ({name}Pod{idx}Value) {{\n"
    ret_val += f"    {name}Pod{idx}IP = (*{name}Pod{idx}Value);\n"
    ret_val += f"}}\n"
    return ret_val

def codegen_from_template(output_dir, ctx: eBPFContext, lib_name, proto_path):
    print(f"in codegen_from_template(), output_dir = {output_dir}")
    print(f"in codegen_from_template(), ctx = {ctx}")
    template_path = f"{COMPILER_ROOT}/element/backend/eBPF/template"

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
            f"bash -c 'cp -r {COMPILER_ROOT}/element/backend/eBPF/template/{{.,}}* {output_dir}'"
        )
        LOG.info(
            f"New template copied from {COMPILER_ROOT}/element/backend/eBPF/template to {output_dir}"
        )
    else:
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter.cc")
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter.h")
        os.system(f"rm -f {output_dir}/appnet_filter/appnet_filter_config.cc")
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/eBPF/template/appnet_filter/appnet_filter.cc {output_dir}/appnet_filter/appnet_filter.cc"
        )
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/eBPF/template/appnet_filter/appnet_filter.h {output_dir}/appnet_filter/appnet_filter.h"
        )
        os.system(
            f"cp {COMPILER_ROOT}/element/backend/eBPF/template/appnet_filter/appnet_filter_config.cc {output_dir}/appnet_filter/appnet_filter_config.cc"
        )

    # if ctx.on_tick_code != []:
    #     # acquire the global_state_lock
    #     ctx.on_tick_code = [
    #         "std::unique_lock<std::mutex> lock(global_state_lock);"
    #     ] + ctx.on_tick_code

    # if ctx.envoy_verbose:  # type: ignore
    #     ctx.insert_envoy_log()
    print(f"ctx.global_var_def = {ctx.global_var_def}, ctx.init_code = {ctx.init_code}, ctx.req_hdr_code = {ctx.req_hdr_code}, ctx.req_body_code = {ctx.req_body_code}")
    eBPF_func_name = output_dir.split('/')[-1]
    # TODO: get edgeN1, edgeN2 from the graph
    edgeN1 = "frontend"
    edgeN1Idx = 0
    conditionEdgeN1 = ""
    edgeN2 = "server"
    edgeN2Idx = 0
    conditionEdgeN2 = ""
    user_space_init = f'''
def ip_to_hex(ip):
    parts = ip.split(".")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
def get_kubernetes_info():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    namespace = "default"
    services = v1.list_namespaced_service(namespace)
    pods = v1.list_namespaced_pod(namespace)
    services = v1.list_namespaced_service(namespace)
    pod_map = {{pod.metadata.name: pod.metadata.labels for pod in pods.items}}
    service_pod_mapping = {{}}
    for svc in services.items:
        svc_name = svc.metadata.name
        svc_ip = svc.spec.cluster_ip
        svc_selector = svc.spec.selector
        if not svc_selector:
            continue
        label_selector = ",".join([f"{{k}}={{v}}" for k, v in svc_selector.items()])
        matching_pods = [
            pod_name for pod_name, labels in pod_map.items()
            if labels and all(labels.get(k) == v for k, v in svc_selector.items())
        ]
        service_pod_mapping[svc_name] = matching_pods
    return service_pod_mapping, services, pods
service_pod_mapping, services, pods = get_kubernetes_info()
for svc, all_pods in service_pod_mapping.items():
    if svc == "{edgeN1}":
        service_pod_map = b["src_pod"]
    elif svc == "{edgeN2}":
        service_pod_map = b["dst_pod"]
    for i in range(len(all_pods)):
        for pod in pods.items:
            if all_pods[i] == pod.metadata.name:
                service_pod_map[ctypes.c_uint32(i)] = ctypes.c_uint32(ip_to_hex(pod.status.pod_ip))
                break '''
    # TODO: set interface as a parameter
    curr_interface = "cni0"
    user_space_running = f'''
interface = "{curr_interface}"
b.attach_xdp(interface, b.load_func("{eBPF_func_name}", bcc.BPF.XDP))
print(f"{eBPF_func_name} eBPF program attached to {{interface}}...")
try: 
    while True:
        b.trace_print()
except KeyboardInterrupt:
    print("Detaching eBPF program")
    b.remove_xdp(interface)
'''
    POPULATEKUBERNETESStr = ""
    # TODO: get edges for POPULATEKUBERNETES
    service_pod_mapping, services, pods = get_kubernetes_info()
    for svc, all_pods in service_pod_mapping.items():
        print("svc=", svc, "all_pods=", all_pods)
        if svc == edgeN1:
            print("come here")
            new_map_var = AppNetMap(AppNetUInt32(), AppNetUInt32())
            _, decl = ctx.declareeBPFVar("src_pod", new_map_var.to_native())
            ctx.push_global_var_def(decl)
            for i in range(len(all_pods)):
                for pod in pods.items:
                    if all_pods[i] == pod.metadata.name:
                        POPULATEKUBERNETESStr += gen_map_access(name="src", idx=edgeN1Idx, ctx=ctx)
                        if conditionEdgeN1 == "":
                            conditionEdgeN1 = f"((src_ip == srcPod{edgeN1Idx}IP)"
                        else:
                            conditionEdgeN1 += f"|| (src_ip == srcPod{edgeN1Idx}IP)"
                        edgeN1Idx += 1
                        break
        elif svc == edgeN2:
            new_map_var = AppNetMap(AppNetUInt32(), AppNetUInt32())
            _, decl = ctx.declareeBPFVar("dst_pod", new_map_var.to_native())
            ctx.push_global_var_def(decl)
            for i in range(len(all_pods)):
                for pod in pods.items:
                    if all_pods[i] == pod.metadata.name:
                        POPULATEKUBERNETESStr += gen_map_access(name="dst", idx=edgeN2Idx, ctx=ctx)
                        if conditionEdgeN2 == "":
                            conditionEdgeN2 = f"((dst_ip == dstPod{edgeN2Idx}IP)"
                        else:
                            conditionEdgeN2 += f"|| (dst_ip == dstPod{edgeN2Idx}IP)"
                        edgeN2Idx += 1
                        break
    if conditionEdgeN1 != "":
        conditionEdgeN1 += ")"
    if conditionEdgeN2 != "":
        conditionEdgeN2 += ")"
    if conditionEdgeN1 != "" and conditionEdgeN2 != "":
        POPULATEKUBERNETESStr += "u32 src_ip = bpf_ntohl(ip->saddr);\n" + "u32 dst_ip = bpf_ntohl(ip->daddr);\n" + f"if (!({conditionEdgeN1} && {conditionEdgeN2})) {{ return XDP_PASS;" + f"}}"
    print(f"POPULATEKUBERNETESStr = {POPULATEKUBERNETESStr}")
    
    replace_dict = {
        "// !APPNET_BEG": 
        ["import bcc"]
        + ["from bcc import BPF"]
        + ["import socket"]
        + ["import ctypes"]
        + ["from kubernetes import client, config"]
        + ["import time"]
        + ["bpf_code = \'\'\'"]
        + ["#include <uapi/linux/bpf.h>"]
        + ["#include <linux/if_ether.h>"]
        + ["#include <linux/ip.h>"]
        + ["#include <linux/if_packet.h>"]
        + ["#include <uapi/linux/tcp.h>"]
        + ["#include <uapi/linux/udp.h>"]
        + ["#include <linux/in.h>"],
        "// !APPNET_STATE": ctx.global_var_def,
        "// !APPNET_INIT": 
        ["b = BPF(text=bpf_code)"]
        + [user_space_init]
        + ctx.init_code
        + [user_space_running],
        "// !APPNET_REQUEST": 
        # ["{ // req header begin. "]
        # + ctx.req_hdr_code
        # + ["} // req header end."]
        [f"int {eBPF_func_name}(struct xdp_md *ctx)"] 
        + ["{ // req body begin. "]
        + ["void *data = (void *)(long)ctx->data;"]
        + ["void *data_end = (void *)(long)ctx->data_end;"]
        + ["struct ethhdr *eth = data;"]
        + ["if ((void *)(eth + 1) > data_end)"]
        + ["    return XDP_PASS;  // If the packet is too short to have an Ethernet header, pass"]
        + ["if (eth->h_proto != htons(ETH_P_IP)) {"]
        + ["    return XDP_PASS;"]
        + ["}"]
        + ["struct iphdr *ip = (struct iphdr *)(eth + 1);"]
        + ["if ((void *)(ip + 1) > data_end)"]
        + ["    return XDP_PASS;"]
        + [POPULATEKUBERNETESStr]
        + ["bpf_trace_printk(\"Hitting appnet program\\\\n\");"]
        + ctx.req_body_code
        + ["} // req body end.\'\'\'"],
        "// !APPNET_RESPONSE": []
        # "// !APPNET_RESPONSE": ["{ // resp header begin. "]
        # + ctx.resp_hdr_code
        # + ["} // resp header end."]
        # + ["{ // resp body begin. "]
        # + ctx.resp_body_code
        # + ["} // resp body end."],
        # "// !APPNET_ONTICK": ctx.on_tick_code,
    }

    # rewrite appnet_filter/appnet_filter.cc according to the replace dict
    with open(f"{output_dir}/appnet_filter/appnet_filter.cc", "r") as file:
        appnet_filter = file.read()
    print(f"Initial appnet_filter = {appnet_filter}")
    for key, value in replace_dict.items():
        appnet_filter = appnet_filter.replace(key, "\n".join(value))
    print(f"After replace appnet_filter = {appnet_filter}")
    print(f"{output_dir}/appnet_filter/appnet_filter.py")
    with open(f"{output_dir}/appnet_filter/appnet_filter.py", "w") as file:
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
    name: str, ctx: eBPFContext, output_dir: str, placement: str, proto_path: str
):
    codegen_from_template(output_dir, ctx, name, proto_path)
