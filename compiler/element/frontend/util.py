import re
from typing import Dict, Optional, Tuple


def find_type_index(list, target_type) -> int:
    """
    Finds the index of the first occurrence of a specified type in a list.

    Parameters:
    list : list
        The list to search through.
    target_type : type
        The type to find in the list.

    Returns:
    int
        The index of the first occurrence of the specified type in the list.
        Returns -1 if the type is not found in the list.
    """
    for i, item in enumerate(list):
        # Check if the current item is an instance of the target_type
        if isinstance(item, target_type):
            return i  # Return the index of the first occurrence
    return -1  # Return -1 if the type is not found


def extract_proto_message_names(
    proto_file: str, target_method_name: str
) -> Tuple[Optional[str], Optional[str]]:
    with open(proto_file, "r") as file:
        proto_content = file.read()

    # Regular expression to find service definitions
    services = re.findall(r"service\s+\w+\s+{[^}]+}", proto_content)
    assert len(services) == 1, "Only one service definition is supported"

    # Regular expression to find rpc definitions, including stream
    rpcs = re.findall(
        r"rpc\s+(\w+)\s*\((stream\s+)?(\w+)\)\s*returns\s*\((stream\s+)?(\w+)\)",
        services[0],
    )
    for rpc in rpcs:
        method_name, _, request_message_name, _, response_message_name = rpc
        if method_name == target_method_name:
            return request_message_name, response_message_name

    return None, None


def extract_proto_service_name(proto_file: str) -> str:
    with open(proto_file, "r") as file:
        proto_content = file.read()

    # Regular expression to find service definitions
    services = re.findall(r"service\s+(\w+)\s+{", proto_content)
    assert len(services) == 1, "Only one service definition is supported"

    return services[0]


def extract_proto_package_name(proto_file: str) -> str:
    with open(proto_file, "r") as file:
        proto_content = file.read()

    packages = re.findall(r"package\s+(\w+);", proto_content)
    assert len(packages) == 1, "Only one package definition is supported"

    return packages[0]


def camel_to_snake(name: str) -> str:
    # Insert an underscore before each uppercase letter and convert to lowercase
    return "".join(["_" + i.lower() if i.isupper() else i for i in name]).lstrip("_")


def extract_message_field_types(
    proto_file: str, request_message_name: str, response_message_name: str
) -> Dict[str, Dict[str, str]]:
    with open(proto_file, "r") as file:
        proto_content = file.read()

    # Regular expressions to match message blocks and field lines within message blocks
    message_block_pattern = re.compile(r"message\s+(\w+)\s+\{([\s\S]*?)\}")
    field_pattern = re.compile(r"\s+(\w+)\s+(\w+)\s+=\s+\d+;")

    field_mapping = {
        "request": {},
        "response": {},
    }

    # Find all message blocks
    message_blocks = message_block_pattern.findall(proto_content)

    # Process each message block
    for message, fields_block in message_blocks:
        if message == request_message_name:
            # Find all fields in the message block......
            fields = field_pattern.findall(fields_block)

            # Process each field
            for field_type, field_name in fields:
                field_mapping["request"][camel_to_snake(field_name)] = field_type
        if message == response_message_name:
            # Find all fields in the message block
            fields = field_pattern.findall(fields_block)

            # Process each field
            for field_type, field_name in fields:
                field_mapping["response"][camel_to_snake(field_name)] = field_type
    return field_mapping
