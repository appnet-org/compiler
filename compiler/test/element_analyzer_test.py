import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler import *
from compiler.element.frontend.parser import ElementParser
from compiler.element.frontend.transformer import ElementTransformer
from compiler.element.frontend.sensitivity_analysis import *

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

    transformer = ElementTransformer()
    ir = transformer.transform(ast)

    check_idempotent(ir)
    check_ordering_sensitive(ir)
    check_requires_all_rpcs(ir)