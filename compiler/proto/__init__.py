import re
from typing import Dict, List, Tuple

ANNOTATION_HEADER = """
import "google/protobuf/descriptor.proto";
extend google.protobuf.MethodOptions {
    bool is_public = 50001;
}
"""

def find_closing_brace(proto_content: str, start_pos: int) -> int:
    brace_count = 1
    pos = start_pos
    while pos < len(proto_content) and brace_count > 0:
        if proto_content[pos] == '{':
            brace_count += 1
        elif proto_content[pos] == '}':
            brace_count -= 1
        pos += 1
    return pos - 1


class ProtoMessageField:
    def __init__(self, content: str):
        words = content.strip().split(" ")
        self.type = words[0]
        self.name = words[1]
        self._annotation_pkg = None
    
    def annotate(self, pkg: str):
        self._annotation_pkg = pkg
    
    def export(self, tag: int) -> str:
        proto_content = f"{self.type} {self.name} = {tag}"
        if self._annotation_pkg is not None:
            proto_content += f" [({self._annotation_pkg}.is_public) = true]"
        proto_content += ";"
        return proto_content


class ProtoMessage:
    def __init__(self, content: str):
        message_match = re.search(r"message\s+(\w+)\s+\{", content)
        if not message_match:
            raise ValueError(f"Could not find message name in content: {content[:50]}...")
        self._message_name = message_match.group(1)
        self._fields: Dict[str, ProtoMessageField] = {}
        
        field_pattern = re.compile(r"\s+(\w+)\s+(\w+)\s+=\s+\d+;")
        for match in field_pattern.finditer(content):
            field = ProtoMessageField(match.group(0).strip())
            self._fields[field.name] = field
    
    @property
    def name(self) -> str:
        return self._message_name
        
    def export(self) -> str:
        proto_content = f"message {self._message_name} {{\n"
        tag = 1
        for field in self._fields.values():
            proto_content += "    " + field.export(tag) + "\n"
            tag += 1
        proto_content += "}\n"
        return proto_content
    
    def extend_annotation(self, pkg: str, fields: List[Tuple[str, str]]):
        for field_name, field_type in fields:
            if field_name not in self._fields:
                self._fields[field_name] = ProtoMessageField(f"{field_type} {field_name} = 1;")
            self._fields[field_name].annotate(pkg)


class ProtoRpcMethod:
    def __init__(self, content: str):
        rpc_match = re.match(
            r"rpc\s+(\w+)\s*\((stream\s+)?(\w+)\)\s+returns\s*\((stream\s+)?(\w+)\)\s*;",
            content.strip()
        )
        if not rpc_match:
            raise ValueError(f"Could not parse RPC method: {content}")

        self._method_name = rpc_match.group(1)
        self._request_stream = bool(rpc_match.group(2))
        self._request_msg = rpc_match.group(3)
        self._response_stream = bool(rpc_match.group(4))
        self._response_msg = rpc_match.group(5)

    @property
    def name(self) -> str:
        return self._method_name
    
    @property
    def request_msg(self) -> str:
        return self._request_msg
    
    @property
    def response_msg(self) -> str:
        return self._response_msg
    
    @property
    def request_stream(self) -> bool:
        return self._request_stream
    
    @property
    def response_stream(self) -> bool:
        return self._response_stream
    
    def export(self) -> str:
        result = f"rpc {self._method_name}("
        if self._request_stream:
            result += "stream "
        result += f"{self._request_msg}) returns ("
        if self._response_stream:
            result += "stream "
        result += f"{self._response_msg});"
        return result


class ProtoService:
    def __init__(self, content: str):
        service_match = re.search(r"service\s+(\w+)\s+\{", content)
        if not service_match:
            raise ValueError(f"Could not find service name in content: {content[:50]}...")
        self._service_name = service_match.group(1)
        
        rpc_pattern = re.compile(
            r"rpc\s+\w+\s*\([^)]*\)\s+returns\s*\([^)]*\)\s*;",
            re.MULTILINE | re.DOTALL
        )
        self._rpc_methods: Dict[str, ProtoRpcMethod] = {}
        for match in rpc_pattern.finditer(content):
            method = ProtoRpcMethod(match.group(0).strip())
            self._rpc_methods[method.name] = method
    
    @property
    def name(self) -> str:
        return self._service_name

    def export(self) -> str:
        proto_content = f"service {self._service_name} {{\n"
        for rpc_method in self._rpc_methods.values():
            proto_content += "    " + rpc_method.export() + "\n"
        proto_content += "}\n"
        return proto_content
    
    def get_rpc_method(self, method_name: str) -> ProtoRpcMethod:
        if method_name not in self._rpc_methods:
            raise ValueError(f"RPC method {method_name} not found")
        return self._rpc_methods[method_name]
    

class Proto:
    def __init__(self, proto_path: str):
        self._proto_path = proto_path
        self._package_name = None
        try:
            with open(proto_path, "r") as f:
                proto_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Proto file {proto_path} not found")

        # extract package name 
        packages = re.findall(r"package\s+([\w.]+);", proto_content)
        if len(packages) != 1:
            raise ValueError(f"There should be exactly one package name in {proto_path}")
        self._package_name = packages[0]

        # extract messages 
        self._messages: Dict[str, ProtoMessage] = {}
        message_matches = re.finditer(r"message\s+(\w+)\s+\{", proto_content)
        for message_match in message_matches:
            end_pos = find_closing_brace(proto_content, message_match.end())
            message = ProtoMessage(proto_content[message_match.start():end_pos+1])
            self._messages[message.name] = message

        # extract services 
        service_matches = list(re.finditer(r"service\s+(\w+)\s+\{", proto_content))
        if len(service_matches) != 1:
            raise ValueError(f"There should be exactly one service in {proto_path}")
        end_pos = find_closing_brace(proto_content, service_matches[0].end())
        self._service = ProtoService(proto_content[service_matches[0].start():end_pos+1])

        # _annotation indicates whether the proto is extended with public annotations
        self._annotation = False
    
    @property
    def package_name(self) -> str:
        return self._package_name
    
    @property
    def service_name(self) -> str:
        return self._service.name
    
    def extend_annotation(self, method_name: str, request_fields: List[Tuple[str, str]], response_fields: List[Tuple[str, str]]):
        if len(request_fields) + len(response_fields) > 0:
            self._annotation = True
        rpc_method = self._service.get_rpc_method(method_name)
        if rpc_method is None:
            raise ValueError(f"RPC method {method_name} not found")
        req_msg, resp_msg = self._messages[rpc_method.request_msg], self._messages[rpc_method.response_msg]
        req_msg.extend_annotation(self._package_name, request_fields)
        resp_msg.extend_annotation(self._package_name, response_fields)

    def export(self) -> str: 
        proto_content = "syntax = \"proto3\";\n"
        proto_content += f"package {self._package_name};\n"
        proto_content += f"option go_package = \"./{self._package_name}\";\n"
        if self._annotation:
            proto_content += ANNOTATION_HEADER
        proto_content += self._service.export()
        for message in self._messages.values():
            proto_content += message.export()
        return proto_content
    

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--proto", type=str, required=True)
    args = parser.parse_args()
    proto = Proto(args.proto)
    print(proto.export())