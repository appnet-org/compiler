import re

class Proto:
    def __init__(self, proto_path: str):
        self.proto_path = proto_path
        self.package_name = None
        try:
            with open(proto_path, "r") as f:
                proto_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Proto file {proto_path} not found")

        # extract package name 
        packages = re.findall(r"^package\s+(\w+);", proto_content)
        if len(packages) != 1:
            raise ValueError(f"There should be exactly one package name in {proto_path}")
        self.package_name = packages[0]
        
        self.extend = False

    def export(self) -> str: 
        proto_content = "syntax = \"proto3\"\n"
        proto_content += f"package {self.package_name};\n"
        if self.extend:
            proto_content += "extend google.protobuf.MethodOptions {\n"
            proto_content += "    bool is_public = 50001\n"
            proto_content += "}\n"
    
    @property
    def package_name(self) -> str:
        return self.package_name