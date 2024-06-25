from lark import Transformer

from compiler.element.frontend.util import *
from compiler.element.node import *


class ElementTransformer(Transformer):
    def __init__(self):
        pass

    def appnet(self, a):
        return Program(a[0], a[1], a[2], a[3])

    def state(self, s):
        return State(s)

    def statedef(
        self, d
    ) -> Tuple[
        Identifier, Type, ConsistencyDecorator, CombinerDecorator, PersistenceDecorator
    ]:
        """
        Args:
            d (list): [decorator*, identifier, type]
        """
        result = [d[-2], d[-1]]

        # Define the list of decorator types
        decorators = [ConsistencyDecorator, CombinerDecorator, PersistenceDecorator]

        # Iterate over decorators and update result accordingly
        for decorator in decorators:
            decorator_idx = find_type_index(d, decorator)
            if decorator_idx != -1:
                result.append(decorator(d[decorator_idx].name))
            else:
                result.append(decorator("None"))

        # Reinitilize the Type to add decorator information
        result[1] = Type(result[1].name, result[2].name, result[3].name, result[4].name)
        return tuple(result)

    def decorator(self, d):
        return d[0]

    def consistency_decorator(self, d) -> ConsistencyDecorator:
        return ConsistencyDecorator(d[0])

    def combiner_decorator(self, d) -> CombinerDecorator:
        return CombinerDecorator(d[0])

    def persistence_decorator(self, d) -> PersistenceDecorator:
        return PersistenceDecorator(d[0])

    def identifier(self, i) -> Identifier:
        return Identifier(i[0])

    def type_(self, t):
        return Type(t[0].name, None, None, False)

    def vec_type(self, t) -> Type:
        return Type(f"Vec<{t[0].name}>", None, None, False)

    def map_type(self, t) -> Type:
        return Type(f"Map<{t[0].name}, {t[1].name}>", None, None, False)

    def single_type(self, d) -> Type:
        return Type(d[0], None, None, False)

    def init(self, i):
        """
        Args:
            i (list): [parameters, body]
        """
        return Procedure("init", i[0], i[1])

    def req(self, r):
        """
        Args:
            r (list): [parameters, body]
        """
        return Procedure("req", r[0], r[1])

    def resp(self, r):
        """
        Args:
            r (list): [parameters, body]
        """
        return Procedure("resp", r[0], r[1])

    def parameters(self, p) -> List[Identifier]:
        ret = []
        for i in p:
            if i != None:
                ret.append(i)
        return ret

    def parameter(self, p) -> str:
        if len(p) == 1:
            return p[0]
        else:
            return None

    def body(self, b) -> List[Statement]:
        return b

    def simple_stmt(self, s):
        if len(s) == 0:
            # pass statement
            return Statement(None)
        else:
            return Statement(s[0])

    def match_stmt(self, m) -> Match:
        """
        Args:
            m (list): [expr, action_stmt*]
        """
        return Match(m[0], m[1])

    def matchbody(self, m) -> List[Tuple[Pattern, List[Statement]]]:
        """
        Args:
            m (list): [action_stmt*]
        """
        return m

    def action_stmt(self, a) -> Tuple[Pattern, List[Statement]]:
        """
        Args:
            a (list): [pattern, body]
        """
        return (a[0], a[1])

    def pattern(self, p) -> Pattern:
        return Pattern(p[0], False)

    def some_pattern(self, p) -> Pattern:
        return Pattern(p[0], True)

    def none_pattern(self, p) -> Pattern:
        return Pattern(Literal("None"), False)

    def expr(self, e) -> Expr:
        if len(e) == 1:
            return e[0]
        elif len(e) == 3:
            return Expr(e[0], e[1], e[2])
        else:
            raise Exception("Invalid expression: " + str(e))

    def assign(self, a) -> Assign:
        return Assign(a[0], a[1])

    def primitive(self, p):
        """
        Args:
            p (list): [expr|err, "Up"|"Down"]
        """
        return Send(p[1], p[0])

    def dir_up(self, _):
        return "Up"

    def dir_down(self, _):
        return "Down"

    def builtin_func(self, f):
        """
        Args:
            f (list): [method_type, [identifier, ...]]
        """
        f = f[0]
        return MethodCall(f[0], f[1][0], f[1][1:])

    def func(self, f) -> FuncCall:
        # TODO: check function name is valid
        # TODO: change send to Send primitive
        # TODO: maybe we should have a global function list first
        assert isinstance(f[0], Identifier)
        assert f[0].name != "send" and f[0].name != "err"
        if f[0].name == "send":
            assert len(f[1]) == 2
            assert f[1][1].name == "Up" or f[1][1].name == "Down"
            # assert f[1][1].name == "APP" or f[1][1].name == "NET"
            # f[1][1] should be str, but it will be parsed as Identifier
            return Send(f[1][1].name, f[1][0])
        elif f[0].name == "err":
            assert len(f[1]) == 1
            return Error(f[1][0])
        else:
            return FuncCall(f[0], f[1])

    def arguments(self, a):
        return a

    def const(self, c) -> Literal:
        return Literal(c[0])

    # TODO: remove this function as err(xxx) will be recognized as a function
    # and handled in def func().
    def err(self, e) -> Error:
        return Error(Literal(e[0]))

    def get_func(self, g):
        return MethodType.GET, g

    def set_func(self, s):
        return MethodType.SET, s

    def delete_func(self, d):
        return MethodType.DELETE, d

    def byte_size_func(self, b):
        return MethodType.BYTE_SIZE, b

    def size_func(self, s):
        return MethodType.SIZE, s

    def op(self, o) -> Operator:
        return o[0]

    def op_add(self, o):
        return Operator.ADD

    def op_sub(self, o):
        return Operator.SUB

    def op_mul(self, o):
        return Operator.MUL

    def op_div(self, o):
        return Operator.DIV

    def op_lor(self, o):
        return Operator.LOR

    def op_land(self, o):
        return Operator.LAND

    def op_eq(self, o):
        return Operator.EQ

    def op_neq(self, o):
        return Operator.NEQ

    def op_lt(self, o):
        return Operator.LT

    def op_gt(self, o):
        return Operator.GT

    def op_le(self, o):
        return Operator.LE

    def op_ge(self, o):
        return Operator.GE

    def quoted_string(self, s):
        return str(s[0])

    def NAME(self, n):
        return n.value

    def true(self, _):
        return "true"

    def false(self, _):
        return "false"
