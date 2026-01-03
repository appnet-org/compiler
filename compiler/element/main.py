import argparse

from compiler.element import compile_element_property

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--element_spec", type=str)
    parser.add_argument("-b", "--backend", type=str)
    parser.add_argument("-p", "--proto", type=str)
    return parser.parse_args()

def augment_proto(proto_path):
    pass

if __name__ == "__main__":
    args = parse_args()
    if args.backend == "arpc":
        property_dict = compile_element_property(args.element_spec.split(".")[0], args.element_spec)
        print(property_dict)