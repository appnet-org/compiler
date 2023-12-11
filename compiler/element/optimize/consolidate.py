from compiler.element.node import *
from compiler.element.node import Expr, Identifier, MethodCall


def consolidate(irs: List[Program]):

    while len(irs) > 1:
        ir1 = irs.pop(0)
        ir2 = irs.pop(0)
        irs.append(merge_program(ir1, ir2))
