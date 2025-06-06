from kubernetes import client, config

def ip_to_hex(ip):
    """Convert IP string (e.g., 10.244.0.4) to hex integer."""
    parts = ip.split(".")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])

'''Get IPs for all services and pods; get the mapping from service to all its pods'''
def get_kubernetes_info():
    # Load Kubernetes config (use `config.load_incluster_config()` if running inside a cluster)
    config.load_kube_config()

    v1 = client.CoreV1Api()

    namespace = "default"  # Change this to your namespace

    # Get all services in the namespace
    services = v1.list_namespaced_service(namespace)

    # Get all pods in the namespace
    pods = v1.list_namespaced_pod(namespace)

    # for pod in pods.items:
    #     print(f"Pod: {pod.metadata.name}, IP: {pod.status.pod_ip}", "hex_ip", ip_to_hex(pod.status.pod_ip))

    # Get all services in the same namespace
    services = v1.list_namespaced_service(namespace)
    # for svc in services.items:
    #     print(f"Service: {svc.metadata.name}, Cluster IP: {svc.spec.cluster_ip}", "hex_ip", ip_to_hex(svc.spec.cluster_ip))


    # Create a mapping of pod name -> labels
    pod_map = {pod.metadata.name: pod.metadata.labels for pod in pods.items}

    # Iterate over each service to find matching pods
    service_pod_mapping = {}

    for svc in services.items:
        svc_name = svc.metadata.name
        svc_ip = svc.spec.cluster_ip
        svc_selector = svc.spec.selector

        if not svc_selector:
            # print(f"Service {svc_name} has no selectors (it may be an ExternalName service).")
            continue

        # Convert service selectors to key=value format
        label_selector = ",".join([f"{k}={v}" for k, v in svc_selector.items()])

        # Find matching pods
        matching_pods = [
            pod_name for pod_name, labels in pod_map.items()
            if labels and all(labels.get(k) == v for k, v in svc_selector.items())
        ]

        service_pod_mapping[svc_name] = matching_pods
    return service_pod_mapping, services, pods

service_pod_mapping, services, pods = get_kubernetes_info()
for svc, all_pods in service_pod_mapping.items():
    print(f"svc={svc}, all_pods={all_pods}")
    print("svc=frontend is", svc=="frontend")
    for i in range(len(all_pods)):
        for pod in pods.items:
            if all_pods[i] == pod.metadata.name:
                print(f"all_pods[i] = {all_pods[i]}, ip_to_hex(pod.status.pod_ip) = {ip_to_hex(pod.status.pod_ip)}")
                # break