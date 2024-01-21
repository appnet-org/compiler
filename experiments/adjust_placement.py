import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).parent.parent

application = "hotel_reservation"
cluster_name = "hotelbench"

placement_dict = {
    "hotel_reservation": {
        "frontend": "h2",
        "search": "h2",
        "geo": "h3",
        "rate": "h3",
        "reservation": "h4",
        "profile": "h5",
    }
}


def get_placement(meta_name: str) -> str:
    node = "h2"
    for service, pos in placement_dict[application].items():
        if service in meta_name:
            node = pos
    return node + "." + cluster_name + ".meshbench-pg0.clemson.cloudlab.us"


if __name__ == "__main__":
    manifest_path = os.path.join(ROOT_DIR, "examples/applications", application)
    for subdir, dirs, files in os.walk(manifest_path):
        for file in files:
            filepath = os.path.join(subdir, file)
            if filepath.endswith(".yaml") or filepath.endswith(".yml"):
                with open(filepath, "r") as f:
                    yml_list = list(yaml.safe_load_all(f))
                for yml in yml_list:
                    node = get_placement(yml["metadata"]["name"])
                    if yml["kind"] == "Deployment":
                        yml["spec"]["template"]["spec"]["nodeName"] = node
                    elif yml["kind"] == "PersistentVolume":
                        yml["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0][
                            "matchExpressions"
                        ][0]["values"][0] = node
                with open(filepath, "w") as f:
                    f.write(yaml.safe_dump_all(yml_list))
