import re

from compiler.ir.frontend.parser import IRParser
from compiler.ir.frontend.transformer import IRTransformer
from compiler.ir.frontend.printer import Printer
from compiler.ir.node import Program

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