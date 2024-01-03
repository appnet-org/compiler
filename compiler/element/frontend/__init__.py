from compiler.element.frontend.parser import IRParser
from compiler.element.frontend.printer import Printer
from compiler.element.frontend.transformer import IRTransformer
from compiler.element.node import Program


class IRCompiler:
    def __init__(self):
        self.parser = IRParser()
        self.transformer = IRTransformer()

    def compile(self, spec: str) -> Program:
        # Step 1: Generate a parse tree based on our grammar
        ast = self.parser.parse(spec)
        # print(ast.pretty())
        
        # Step 2: Transforme traverses the parse tree and applies transformation to its nodes.
        ir = self.transformer.transform(ast)
        return ir
