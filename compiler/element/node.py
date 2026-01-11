from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from compiler.element.ir.type_inference.type import AbstractType


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
    
    def get_type(self) -> Optional[AbstractType]:
        if hasattr(self, "_type"):
            return self._type
        return None
    
    def set_type(self, t: AbstractType):
        if hasattr(self, "_type"):
            self._type = t
    

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
        self._type: Optional[AbstractType] = None


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
        self._type: Optional[AbstractType] = None


class Pair(Expr):
    def __init__(self, first: Expr, second: Expr):
        self.first = first
        self.second = second
        self._type: Optional[AbstractType] = None


class Identifier(Expr):
    def __init__(self, name: str):
        self.name = name
        self._type: Optional[AbstractType] = None
        self.declare = False
    

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


class RandomFunc(FuncCall):
    def __init__(self, lower: Expr, upper: Expr):
        super().__init__(Identifier("randomf"), [lower, upper])
        self.lower = lower
        self.upper = upper
        self._type: Optional[AbstractType] = None


class CurrentTimeFunc(FuncCall):
    def __init__(self):
        super().__init__(Identifier("current_time"), [])
        self._type: Optional[AbstractType] = None


class TimeDiffFunc(FuncCall):
    def __init__(self, a: Expr, b: Expr):
        super().__init__(Identifier("time_diff"), [a, b])
        self.a = a
        self.b = b
        self._type: Optional[AbstractType] = None


class MinFunc(FuncCall):
    def __init__(self, a: Expr, b: Expr):
        super().__init__(Identifier("min"), [a, b])
        self.a = a
        self.b = b
        self._type: Optional[AbstractType] = None


class MaxFunc(FuncCall):
    def __init__(self, a: Expr, b: Expr):
        super().__init__(Identifier("max"), [a, b])
        self.a = a
        self.b = b
        self._type: Optional[AbstractType] = None


class ByteSizeFunc(FuncCall):
    def __init__(self, var: Identifier):
        super().__init__(Identifier("byte_size"), [var])
        self.var = var
        self._type: Optional[AbstractType] = None


class MethodCall(Expr):
    def __init__(self, method: MethodType, obj: Identifier, args: List[Expr]):
        self.method = method
        self.obj = obj
        self.args = args
        self._type: Optional[AbstractType] = None


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


class Literal(Node):
    def __init__(self, value: str):
        self.value = value
        # TODO: complete type inference for Literal
        # currently only String and Bool are supported.
        if value.startswith("'") and value.endswith("'"):
            self.type = DataType.STR
        elif value in ["true", "false"]:
            self.type = DataType.BOOL
        else:
            self.type = DataType.NONE
        self._type: Optional[AbstractType] = None


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
