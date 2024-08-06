from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.element.backend.envoy_native import *
from compiler.element.backend.envoy_native.nativetype import *
from compiler.element.backend.envoy_native.appnettype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor


class NativeContext:
    def __init__(
        self,
        proto=None,
        method_name=None,
        request_message_name = None,
        response_message_name = None,
        message_field_types = None,
        mode: str = "sidecar",
        element_name: str = "",
        tag: str = "0",
    ) -> None:
        self.appnet_state: dict[str, AppNetVariable] = {}
        self.appnet_local_var: dict[str, AppNetVariable] = {}
        self.native_var: list[dict[str, NativeVariable]] = [{}] # The first scope is the global scope
        self.global_var_def: list[str] = []
        self.init_code: list[str] = []
        self.on_tick_code: list[str] = []
        self.req_hdr_code: list[str] = []
        self.req_body_code: list[str] = []
        self.resp_hdr_code: list[str] = []
        self.resp_body_code: list[str] = []

        self.current_procedure: str = ""
        self.current_procedure_code: list[str] = []

    def declareAppNetState(
        self,
        name: str,
        rtype: AppNetType,
        decorator: Optional[dict[str, str]] = None,
    ) -> AppNetVariable:
        if name in self.appnet_state:
            raise Exception(f"variable {name} already declared")
        self.appnet_state[name] = AppNetVariable(name, rtype, decorator)
        return self.appnet_state[name]

    def declareNativeVar(self, name: str, rtype: NativeType) -> Tuple[NativeVariable, str]:
        # Return the declaration,
        if name in self.native_var[-1]:
            raise Exception(f"variable {name} already declared")
        self.native_var[-1][name] = NativeVariable(name, rtype)
        return (self.native_var[-1][name], rtype.gen_decl(name))

    def push_code(self, code: str) -> None:
        self.current_procedure_code.append(code)
        if code.startswith("{"):
            self.native_var.append({})
        if code.startswith("}"):
            self.native_var.pop()


class NativeGenerator(Visitor):
    def __init__(self, placement: str) -> None:
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: NativeContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: NativeContext) -> None:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitState(self, node: State, ctx: NativeContext) -> None:
        # Iterate through all state variables and declare them
        for (identifier, type, cons, comb, per) in node.state:

            assert(per == None or per.name == "true" or per.name == "false")
            appType: AppNetType = type.accept(self, ctx)
            decorator = {
                "consistency": cons.name,
                "combiner": comb.name,
                "persistence": per.name,
            }
            ctx.declareAppNetState(identifier.name, appType, decorator)


    def visitProcedure(self, node: Procedure, ctx: NativeContext):
        ctx.current_procedure = node.name
        ctx.current_procedure_code = []
        ctx.appnet_local_var = {}

        if node.name == "init":
            assert(len(node.params) == 0)
        else:
            assert(node.name == "req" or node.name == "resp")
            assert(len(node.params) == 1)
            assert(node.params[0].name == "rpc")

        for stmt in node.body:
            stmt.accept(self, ctx)
 
        if node.name == "init":
            ctx.init_code = ctx.current_procedure_code
        elif node.name == "req":
            ctx.req_hdr_code = ctx.current_procedure_code
        elif node.name == "resp":
            ctx.resp_hdr_code = ctx.current_procedure_code
        else:
            raise Exception("unknown procedure")
        ctx.appnet_local_var = {}

    def visitStatement(self, node: Statement, ctx: NativeContext):
        # A statement may be translated into multiple C++ statements.
        # These statements will be attached to ctx.current_procedure_code directly.

        if node.stmt is None:
            ctx.push_code("; // empty statement")
        elif isinstance(node.stmt, Send) \
            or isinstance(node.stmt, Assign) \
            or isinstance(node.stmt, Match) \
            or isinstance(node.stmt, Expr):
            
            retval = node.stmt.accept(self, ctx)
            if not isinstance(retval, list):
                retval = [retval]
            return retval
        
        else:
            raise Exception("unknown statement")
        

    def visitMatch(self, node: Match, ctx: NativeContext) -> None:
        expr = node.expr.accept(self, ctx)


    def visitAssign(self, node: Assign, ctx: NativeContext) -> None:
        pass

    # def visitPattern(self, node: Pattern, ctx: NativeContext):
    #     pass

    # A temporary cpp variable will be generated to store the result of the expression.
    def visitExpr(self, node: Expr, ctx) -> AppNetVariable:
        pass

    # def visitOperator(self, node: Operator, ctx)
    #     pass

    # def visitIdentifier(self, node: Identifier, ctx: NativeContext)
    #     pass

    def visitType(self, node: Type, ctx: NativeContext) -> AppNetType:
        pass

    def visitFuncCall(self, node: FuncCall, ctx: NativeContext):
        # For now, we only support the built-in functions
        assert(0)

    def visitMethodCall(self, node: MethodCall, ctx: NativeContext) -> str:
        pass

    def visitSend(self, node: Send, ctx: NativeContext) -> str:
        pass

    def visitLiteral(self, node: Literal, ctx):
        pass

    def visitError(self, node: Error, ctx) -> str:
        pass


def proto_gen_get(rpc: str, args: List[str], ctx: NativeContext) -> str:
    pass


def proto_gen_set(rpc: str, args: List[str], ctx: NativeContext) -> str:
    pass


def proto_gen_size(rpc: str, args: List[str]) -> str:
    pass


def proto_gen_bytesize(rpc: str, args: List[str]) -> str:
    pass

def proto_get_arg_type(arg: str, ctx: NativeContext) -> str:
    pass


def proto_type_mapping(proto_type: str) -> str:
    """Maps the type in the protobuf to the type in wasm"""
    if proto_type == "string":
        return "String"
    elif proto_type == "int":
        return "i32"
    elif proto_type == "uint":
        return "u32"
    elif proto_type == "float":
        return "f32"
    elif proto_type == "bool":
        return "bool"
    else:
        raise Exception("unknown type")
