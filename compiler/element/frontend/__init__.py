import re

from compiler.element.frontend.parser import IRParser
from compiler.element.frontend.printer import Printer
from compiler.element.frontend.transformer import IRTransformer
from compiler.element.node import Program


class IRCompiler:
    def __init__(self):
        self.parser = IRParser()
        self.transformer = IRTransformer()

    def compile(self, spec: str) -> Program:
        # parsing
        ast = self.parser.parse(spec)
        # print(ast.pretty())
        ir = self.transformer.transform(ast)
        return ir
