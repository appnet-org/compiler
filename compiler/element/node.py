from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import List, Optional, Tuple, Union


class Node:
    def __init__(self):
        pass

    def __str__(self):
        return self.__class__.__name__

    def accept(self, visitor, ctx=None):
        class_list = type(self).__mro__
        for cls in class_list:
            func_name = "visit" + cls.__name__
            visit_func = getattr(visitor, func_name, None)
            if visit_func is not None:
                return visit_func(self, ctx)
        raise Exception(f"visit function for {self.__class__.__name__} not implemented")


class Program(Node):
    def __init__(
        self, definition: State, init: Procedure, req: Procedure, resp: Procedure
    ):
        self.definition = definition
        self.init = init
        self.req = req
        self.resp = resp


class State(Node):
    def __init__(
        self,
        state: List[
            Tuple[
                Identifier,
                Type,
                ConsistencyDecorator,
                CombinerDecorator,
                PersistenceDecorator,
            ]
        ],
    ):
        self.state = state


class Procedure(Node):
    def __init__(self, name: str, params: List[Identifier], body: List[Statement]):
        self.name = name
        self.params = params
        self.body = body


class Statement(Node):
    def __init__(self, stmt: Optional[Union[Match, Assign, Send, Expr]] = None):
        self.stmt = stmt


class Match(Statement):
    def __init__(self, match: Expr, actions: List[Tuple[Pattern, List[Statement]]]):
        self.expr = match
        self.actions = actions


class Assign(Statement):
    def __init__(self, left: Union[Identifier, Pair], right: Expr):
        self.left = left
        self.right = right


class Pattern(Node):
    def __init__(self, value: Union[Identifier, Literal, Error], some: bool):
        assert (
            isinstance(value, Identifier)
            or isinstance(value, Literal)
            or isinstance(value, Error)
        )
        self.value = value
        self.some = some


class Foreach(Statement):
    def __init__(self, var: Identifier, func: LambdaFunc):
        self.var = var
        self.func = func


class LambdaFunc(Node):
    def __init__(self, arg: Identifier, body: List[Statement]):
        self.arg = arg
        self.body = body


class Expr(Node):
    def __init__(self, lhs: Expr, op: Operator, rhs: Expr):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        self.type = "unknown"


class Pair(Expr):
    def __init__(self, first: Expr, second: Expr):
        self.first = first
        self.second = second


class Identifier(Expr):
    def __init__(self, name: str):
        self.name = name


class ConsistencyDecorator(Node):
    def __init__(self, name: str):
        self.name = name


class CombinerDecorator(Node):
    def __init__(self, name: str):
        self.name = name


class PersistenceDecorator(Node):
    def __init__(self, name: str):
        self.name = name


class Error(Node):
    def __init__(self, msg: Literal):
        self.msg = msg


class FuncCall(Expr):
    def __init__(self, name: Identifier, args: List[Expr]):
        self.name = name
        self.args = args


class MethodCall(Expr):
    def __init__(self, method: MethodType, obj: Identifier, args: List[Expr]):
        self.method = method
        self.obj = obj
        self.args = args


class Send(Statement):
    def __init__(self, direction: str, msg: Expr):
        self.direction = direction
        self.msg = msg


class Type(Node):
    def __init__(self, name: str, consistency: str, combiner: str, persistence: bool):
        self.name = name
        self.consistency = consistency
        self.combiner = combiner
        self.persistence = persistence


import re
def is_integer(s):
    return re.fullmatch(r"-?\d+", s) is not None
def is_float(s):
    return re.fullmatch(r"-?\d+\.\d+", s) is not None

class Literal(Node):
    def __init__(self, value: str):
        self.value = value
        # TODO: complete type inference for Literal
        # currently only String and Bool are supported.
        if value.startswith("'") and value.endswith("'"):
            self.type = DataType.STR
        elif is_integer(value):
            self.type = DataType.INT
        elif is_float(value):
            self.type = DataType.FLOAT
        elif value in ["true", "false"]:
            self.type = DataType.BOOL
        else:
            self.type = DataType.NONE


class Start(Node):
    def __init__(self):
        pass


class End(Node):
    def __init__(self):
        pass


START_NODE = Start()
END_NODE = End()
PASS_NODE = Statement()


class EnumNode(Enum):
    def accept(self, visitor, ctx):
        class_list = type(self).__mro__
        for cls in class_list:
            func_name = "visit" + cls.__name__
            visit_func = getattr(visitor, func_name, None)
            if visit_func is not None:
                return visit_func(self, ctx)
        raise Exception(f"visit function for {self.name} not implemented")


class Operator(EnumNode):
    ADD = 1
    SUB = 2
    MUL = 3
    DIV = 4
    EQ = 5
    NEQ = 6
    LE = 7
    GE = 8
    LT = 9
    GT = 10
    LOR = 11
    LAND = 12
    OR = 13  # bitwise
    AND = 14  # bitwise
    XOR = 15  # bitwise


class DataType(EnumNode):
    INT = 1
    FLOAT = 2
    STR = 3
    BOOL = 4
    NONE = 5
    BYTE = 6


class MethodType(EnumNode):
    GET = 1
    METAGET = 2
    SET = 3
    DELETE = 4
    SIZE = 5
    BYTE_SIZE = 6
    FOR_EACH = 7


class ContainerType(EnumNode):
    VEC = 1
    MAP = 2
