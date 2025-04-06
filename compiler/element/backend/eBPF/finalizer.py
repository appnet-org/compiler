import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.eBPF.nativegen import eBPFContext
from compiler.element.logger import ELEMENT_LOG as LOG


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
    user_space_init = '''
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
    pod_map = {pod.metadata.name: pod.metadata.labels for pod in pods.items}
    service_pod_mapping = {}
    for svc in services.items:
        svc_name = svc.metadata.name
        svc_ip = svc.spec.cluster_ip
        svc_selector = svc.spec.selector
        if not svc_selector:
            continue
        label_selector = ",".join([f"{k}={v}" for k, v in svc_selector.items()])
        matching_pods = [
            pod_name for pod_name, labels in pod_map.items()
            if labels and all(labels.get(k) == v for k, v in svc_selector.items())
        ]
        service_pod_mapping[svc_name] = matching_pods
    return service_pod_mapping, services, pods
service_pod_mapping, services, pods = get_kubernetes_info()
for svc, all_pods in service_pod_mapping.items():
    service_pod_map = b[svc + "_pod"]
    for i in range(len(all_pods)):
        for pod in pods.items:
            if all_pods[i] == pod.metadata.name:
                service_pod_map[ctypes.c_uint32(i)] = ctypes.c_uint32(ip_to_hex(pod.status.pod_ip))
                break '''
    
    user_space_running = '''
interface = "cni0"
b.attach_xdp(interface, b.load_func("drop_packet", bcc.BPF.XDP))
print(f"eBPF program attached to {interface}. Dropping packets from 10.244.0.4...")
try: 
    while True:
        b.trace_print()
except KeyboardInterrupt:
    print("Detaching eBPF program")
    b.remove_xdp(interface)
'''
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
        [user_space_init]
        + ["b = BPF(text=bpf_code)"]
        + ctx.init_code
        + [user_space_running],
        "// !APPNET_REQUEST": 
        # ["{ // req header begin. "]
        # + ctx.req_hdr_code
        # + ["} // req header end."]
        [f"int {eBPF_func_name}(struct xdp_md *ctx)"] 
        + ["{ // req body begin. "]
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
