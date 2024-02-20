import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.absolute()))

from compiler import *
from compiler.element.frontend.parser import ElementParser

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--element_path", type=str, required=True)
    args = parser.parse_args()

    # Parse the elements
    parser = ElementParser()
    with open(args.element_path) as f:
        spec = f.read()
        ast = parser.parse(spec)
        print(ast.pretty())
