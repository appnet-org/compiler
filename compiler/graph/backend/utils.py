"""
Utility functions for executing commands in remote hosts/containers.
"""
import json
import os
import subprocess
import time
from typing import Dict, List

from kubernetes import client, config

from compiler.graph.logger import GRAPH_BACKEND_LOG


def find_target_yml(yml_list, sname):
    return next(
        (
            yml
            for yml in yml_list
            if yml["kind"] == "Deployment" and yml["metadata"]["name"] == sname
        ),
        None,
    )


def extract_service_pos(yml_list: List[Dict]) -> Dict[str, str]:
    """Extract the service name to hostname mapping from the application manifest file.

    Args:
        app_manifest_file: The application manifest file.

    Returns:
        A dictionary mapping service name to hostname.
    """
    service_pos = {}
    for yml in yml_list:
        if yml and yml["kind"] == "Deployment":
            if "nodeName" in yml["spec"]["template"]["spec"]:
                service_pos[yml["metadata"]["name"]] = yml["spec"]["template"]["spec"][
                    "nodeName"
                ]
            else:
                service_pos[yml["metadata"]["name"]] = None
    return service_pos


def extract_service_port(yml_list: List[Dict]) -> Dict[str, str]:
    """
    Extract the service name to port number mapping from a list of service YAML definitions.

    Args:
        yml_list: A list of dictionaries representing the parsed YAML content of the service files.

    Returns:
        A dictionary mapping each service name to its port number.
    """
    service_ports = {}
    for yml in yml_list:
        if yml and yml["kind"] == "Service":
            service_name = yml["metadata"]["name"]
            ports = yml["spec"]["ports"]
            if ports and isinstance(ports, list):
                # Assuming the first port is the relevant one
                service_ports[service_name] = str(ports[0]["port"])
            else:
                service_ports[service_name] = None  # or some default value

    return service_ports


def extract_service_label(yml_list: List[Dict]) -> Dict[str, str]:
    """
    Extract the service name to label mapping from a list of service YAML definitions.

    Args:
        yml_list: A list of dictionaries representing the parsed YAML content of the service files.

    Returns:
        A dictionary mapping each service name to its port number.
    """
    service_labels = {}
    for yml in yml_list:
        if yml and yml["kind"] == "Service":
            service_name = yml["metadata"]["name"]
            # We assume the service label value is the same as the service name
            for k, v in yml["metadata"]["labels"].items():
                if v == service_name:
                    label_name = k
            service_labels[service_name] = label_name

    return service_labels


def extract_service_account_mapping(yaml_list: List[Dict]) -> Dict[str, str]:
    """
    Extract the deployment name to service account mapping from a list of deployment YAML definitions.

    Args:
        yaml_list: A list of dictionaries representing the parsed YAML content of the deployment files.

    Returns:
        A dictionary mapping each deployment name to its service account name.
    """
    mapping = {}
    for yml in yaml_list:
        if yml is not None and yml.get("kind", "") == "Deployment":
            deployment_name = yml["metadata"]["name"]
            service_account_name = yml["spec"]["template"]["spec"].get(
                "serviceAccountName", ""
            )
            if service_account_name:
                mapping[deployment_name] = service_account_name

    return mapping


def error_handling(res, msg):
    """Output the given error message and the stderr contents if the subprocess exits abnormally.

    Args:
        res (CompletedProcess[bytes]): the returned object from subproces.run().
        msg: error message printed before the stderr contents.
    """
    if res.returncode != 0:
        GRAPH_BACKEND_LOG.error(f"{msg}\nError msg: {res.stderr.decode('utf-8')}")
        raise Exception


def execute_remote_host(host: str, cmd: List[str]) -> str:
    """Execute commands on remote host.

    Args:
        host: hostname.
        cmd: A list including the command and all options.

    Returns:
        The output of the command, or "xxx"if "--dry_run" is provided.
    """
    if os.getenv("DRY_RUN") == "1":
        return "xxx"
    GRAPH_BACKEND_LOG.debug(f"Executing command \"{' '.join(cmd)}\" on host {host}...")
    res = subprocess.run(["ssh", host] + cmd, capture_output=True)
    error_handling(res, f"Error when executing command")
    return res.stdout.decode("utf-8")


def execute_remote_container(service: str, host: str, cmd: List[str]) -> str:
    """Execute commands in remote docker container.

    Args:
        service: Service name (determines the container name).
        host: hostname.
        cmd: A list including the command and all arguments.

    Returns:
        The output of the command, or "xxx" if "--dry_run" is provided.
    """
    GRAPH_BACKEND_LOG.debug(
        f"Executing command {' '.join(cmd)} in {service.lower()}..."
    )
    if os.getenv("DRY_RUN") == "1":
        return "xxx"
    res = subprocess.run(
        ["ssh", host, "docker", "exec", service.lower()] + cmd,
        capture_output=True,
    )
    error_handling(res, f"Error when executing command {cmd} in container")
    return res.stdout.decode("utf-8")


def execute_local(cmd: List[str], *, cwd=None) -> str:
    """Execute commands in localhost

    Args:
        cmd: A list including the command and all arguments.

    Returns:
        The output of the command, or "xxx" if "--dry_run" is provided.
    """
    GRAPH_BACKEND_LOG.debug(f"Executing command \"{' '.join(cmd)}\"...")
    if cwd:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True)
    else:
        res = subprocess.run(cmd, capture_output=True)
    error_handling(res, f"Error when executing command {cmd}")
    return res.stdout.decode("utf-8")


def copy_remote_host(host: str, local_path: str, remote_path: str):
    """Copy local files/directories into remote host.

    Args:
        host: hostname.
        local_path: Path to the local file/directory.
        remote_path: The target path in the remote host.
    """
    GRAPH_BACKEND_LOG.debug(f"Copy file {local_path} to {host}")
    if os.getenv("DRY_RUN") == "1":
        return
    res = subprocess.run(
        ["rsync", "-avz", local_path, f"{host}:{remote_path}"], capture_output=True
    )
    error_handling(res, f"Error when rsync-ing file {local_path}")


def copy_remote_container(service: str, host: str, local_path: str, remote_path: str):
    """Copy local files/directories into remote containers.

    Args:
        service: Servie name.
        host: hostname.
        local_path: Path to the local file/directory.
        remote_path: The target path in the remote container.
    """
    GRAPH_BACKEND_LOG.debug(f"Copy file {local_path} to {service.lower()}")
    if os.getenv("DRY_RUN") == "1":
        return
    filename = local_path.split("/")[-1]
    res = subprocess.run(
        ["rsync", "-avz", local_path, f"{host}:/tmp"], capture_output=True
    )
    error_handling(res, f"Error when rsync-ing file {local_path}")
    execute_remote_host(
        host,
        ["docker", "cp", f"/tmp/{filename}", f"{service.lower()}:{remote_path}"],
    )
    execute_remote_host(host, ["rm", "-r", f"/tmp/{filename}"])


def wait_until_running(namespace: str = "default"):
    """Wait until all pods are running. Ususally used after `kubectl delete` to ensure synchronization.

    Args:
        namespace(optional): the pod namespace to monitor.
    """
    config.load_kube_config()

    v1 = client.CoreV1Api()

    # Find the status of echo server and wait for it.
    while True:
        ret = v1.list_namespaced_pod(namespace=namespace)
        status = [i.status.phase == "Running" for i in ret.items]
        if False not in status:
            GRAPH_BACKEND_LOG.debug("kpods check done")
            return
        else:
            time.sleep(2)


def get_node_names(control_plane=True):
    # Load kube config from default location (`~/.kube/config`)
    config.load_kube_config()

    # Create a client for the CoreV1Api
    v1 = client.CoreV1Api()

    # Retrieve a list of all nodes
    nodes = v1.list_node()

    if not control_plane:
        return [
            node.metadata.name
            for node in nodes.items
            if "node-role.kubernetes.io/control-plane"
            not in node.metadata.labels.keys()
        ]

    return [node.metadata.name for node in nodes.items]


def ksync():
    """Restart pods to ensure all changes are synchronized"""
    execute_local(["kubectl", "delete", "pods", "--all"])
    wait_until_running()


def kapply_and_sync(file_or_dir: str):
    """Apply changes in file to knodes.

    Args:
        file: configuration filename.
    """
    execute_local(["kubectl", "apply", "-Rf", file_or_dir])
    ksync()


def kdestroy():
    """Destroy all deployments"""
    execute_local(["kubectl", "delete", "envoyfilters,all,pvc,pv", "--all"])


def run_remote_command(server: str, command: str):
    """Run a command on a remote server via SSH"""
    ssh_command = f"ssh {server} '{command}'"
    result = subprocess.run(ssh_command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise Exception(f"Command failed on {server}: {ssh_command}\n{result.stderr}")
    return result.stdout


def get_container_pids(server: str, service_name: str):
    """Get PIDs of sidecar proxies for a given microservice on a remote server"""
    containers_output = run_remote_command(
        server,
        "sudo crictl --runtime-endpoint unix:///run/containerd/containerd.sock ps",
    )

    # Adjust the following logic based on your container identification method
    sidecar_containers = []
    for line in containers_output.splitlines()[1:]:
        if service_name in line and "istio-proxy" in line:
            container_id = line.split()[0]
            sidecar_containers.append(container_id)

    pids = []
    for container_id in sidecar_containers:
        inspect_output = run_remote_command(
            server,
            f"sudo crictl --runtime-endpoint unix:///run/containerd/containerd.sock inspect {container_id}",
        )
        pid = json.loads(inspect_output)["info"]["pid"]
        pids.append(pid)

    return pids


def bypass_sidecar(hostname: str, service_name: str, port: str, direction: str):
    """Set up iptables rules for each container on a remote server"""
    pids = get_container_pids(hostname, service_name)
    for pid in pids:
        # print(f"Setting up {direction} iptables on server {hostname} with PID {pid}")
        if direction == "S":
            # inbound traffic
            run_remote_command(
                hostname,
                f"sudo nsenter -t {pid} -n iptables -t nat -I PREROUTING 1 -p tcp --dport {port} -j ACCEPT -w",
            )
        elif direction == "C":
            # outbound traffic
            run_remote_command(
                hostname,
                f"sudo nsenter -t {pid} -n iptables -t nat -I OUTPUT 1 -p tcp --dport {port} -j RETURN -w",
            )
        else:
            raise ValueError


bypass_script = """
import os
import sys

sys.path.append(os.path.join(os.getenv("HOME"), "compiler"))
from compiler.graph.backend.utils import bypass_sidecar

bypass_info_dict = {bypass_info_dict}

element_deploy_count = bypass_info_dict["element_deploy_count"]
service_to_hostname = bypass_info_dict["service_to_hostname"]
service_to_port_number = bypass_info_dict["service_to_port_number"]

for current_service, count_dict in element_deploy_count.items():
    for other_service_placement in count_dict.keys():
        other_service, placement = "_".join(other_service_placement.split("_")[:-1]), other_service_placement.split("_")[-1]
        count = count_dict[other_service_placement]
        if count == 0:
            # no element, need to bypass sidecar
            host = service_to_hostname[current_service]
            port = service_to_port_number[other_service] if placement == "C" else service_to_port_number[current_service]
            bypass_sidecar(host, current_service, port, placement)
"""


# if __name__ == "__main__":
# Example usage
#     try:
#         remote_servers = ["h2"]  # List of remote servers
#         for server in remote_servers:
#             setup_iptables(server, "ping", 8081, "inbound")
#             setup_iptables(server, "frontend", 8081, "outbound")
#             setup_iptables(server, "frontend", 8080, "inbound")
#     except Exception as e:
#         print(f"Error: {e}")
