import re

import os
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.client import V1Volume, V1PersistentVolumeClaimVolumeSource, V1VolumeMount


def find_waypoint_name(file_name):
    try:
        with open(file_name, 'r') as file:
            # Create a regular expression to match the service account
            pattern = re.compile(r'--name\s+(\S+)')

            # Iterate through each line of the file
            for line in file:
                # Check if the line contains the service account
                match = pattern.search(line)
                if match:
                    # Extract the service account from the matched line
                    waypoint = match.group(1)
                    return waypoint
    except Exception as e:
        print(f"Error opening file: {e}")
        return ""

    return ""


def attach_volume_to_waypoint(service_name, waypoint_name):
    # Set up kubeconfig path
    home = os.path.expanduser("~")
    kubeconfig = os.path.join(home, ".kube", "config") if home else ""

    # Load kubeconfig
    try:
        config.load_kube_config(config_file=kubeconfig)
    except Exception as e:
        raise Exception(f"Failed to load kubeconfig: {e}")

    # Create the clientset
    apps_v1 = client.AppsV1Api()

    # Set deployment details
    namespace = "default"
    deployment_name = waypoint_name
    pvc_name = f"{service_name}-appnet-pvc"
    mount_path = "/appnet"

    max_attempts = 20

    # Retry on failure
    for attempt in range(max_attempts):
        try:
            # Get the specified deployment
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)

            # Define the volume and volume mount
            volume = V1Volume(
                name=f"{service_name}-storage",
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name)
            )
            volume_mount = V1VolumeMount(
                name=f"{service_name}-storage",
                mount_path=mount_path
            )

            # Check if the volume and volume mount already exist to avoid duplicates
            volume_exists = any(v.name == volume.name for v in deployment.spec.template.spec.volumes)
            if not volume_exists:
                deployment.spec.template.spec.volumes.append(volume)

            for container in deployment.spec.template.spec.containers:
                volume_mount_exists = any(vm.name == volume_mount.name for vm in container.volume_mounts)
                if not volume_mount_exists:
                    container.volume_mounts.append(volume_mount)

            # Update the deployment
            apps_v1.patch_namespaced_deployment(deployment_name, namespace, deployment)
            break
        except ApiException as e:
            print(f"Attempt {attempt + 1}: failed to get/update deployment: {e}")
            time.sleep(2)
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

if __name__ == "__main__":
    # Server service name / waypoint create script path
    attach_volume_to_waypoint("server", find_waypoint_name("/mnt/appnet/compiler/compiler/graph/generated/echo-deploy/waypoint_create.sh"))
    # print(find_waypoint_name("/mnt/appnet/compiler/compiler/graph/generated/echo-deploy/waypoint_create.sh"))