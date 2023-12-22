from typing import Dict, List, Optional

from compiler.element.backend.envoy.wasmtype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor

FUNC_REQ = "req"
FUNC_RESP = "resp"
FUNC_INIT = "init"


class WasmContext:
    def __init__(self) -> None:
        self.internal_states: List[WasmVariable] = []
        self.name2var: Dict[str, WasmVariable] = {}
        self.current_func: str = "unknown"
        self.params: List[WasmVariable] = []
        self.init_code: List[str] = []
        self.req_code: List[str] = []
        self.resp_code: List[str] = []

    def declare(self, name: str, rtype: WasmType, temp: bool, atomic: bool) -> None:
        if name in self.name2var:
            raise Exception(f"variable {name} already defined")
        else:
            var = WasmVariable(
                name, rtype, temp, name == "rpc_req" or name == "rpc_resp", atomic
            )
            self.name2var[name] = var
            if not temp and not var.rpc:
                self.internal_states.append(var)

    def clear_temps(self) -> None:
        new_dic = {}
        for k, v in self.name2var.items():
            if not v.temp:
                new_dic[k] = v
        self.name2var = new_dic

    def push_code(self, code: str) -> None:
        if self.current_func == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_func == FUNC_REQ:
            self.req_code.append(code)
        elif self.current_func == FUNC_RESP:
            self.resp_code.append(code)
        else:
            raise Exception("unknown function")

    def find_var(self, name: str) -> Optional[WasmVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None

    def explain(self) -> str:
        return f"Context.Explain:\n\t{self.internal_states}\n\t{self.name2var}\n\t{self.current_func}\n\t{self.params}\n\t{self.init_code}\n\t{self.req_code}\n\t{self.resp_code}"

    def gen_struct_names(self) -> List[str]:
        ret = []
        # todo! check this
        # for i in self.internal_states:
        #     ret.append(i.name)
        return ret

    def gen_init_localvar(self) -> List[str]:
        ret = []
        for _, v in self.name2var.items():
            if not v.temp and not v.rpc:
                ret.append(v.gen_init_localvar())
        return ret

    def gen_internal_names(self) -> List[str]:
        ret = []
        for i in self.internal_states:
            ret.append(i.name)
        return ret

    def gen_init_tempvar(self) -> List[str]:
        ret = []
        for _, v in self.name2var.items():
            if v.temp and not v.rpc:
                ret.append(v.gen_init_localvar())
        return ret

    def gen_struct_declaration(self) -> List[str]:
        ret = []
        for v in self.internal_states:
            ret.append(v.gen_struct_declaration())
        return ret


class WasmGenerator(Visitor):
    def __init__(self, placement: str) -> None:
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: WasmContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: WasmContext) -> None:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        for v in ctx.internal_states:
            if v.init == "":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: WasmContext) -> None:
        for i, t in node.internal:
            name = i.name
            wasm_type = t.accept(self, ctx)
            ctx.declare(name, wasm_type, False)

    def visitProcedure(self, node: Procedure, ctx: WasmContext):
        raise NotImplementedError

    def visitStatement(self, node: Statement, ctx: WasmContext) -> str:
        if node.stmt == None:
            return ";//NULL_STMT\n"
        else:
            if isinstance(node.stmt, Expr) or isinstance(node.stmt, Send):
                ret = node.stmt.accept(self, ctx) + ";\n"
                return ret
            else:
                return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: WasmContext) -> str:
        template = "match ("
        if isinstance(node.expr, Identifier):
            var = ctx.find_var(node.expr.name)
            if var.type.name == "String":
                template += node.expr.accept(self, ctx) + ".as_str()"
        else:
            template += node.expr.accept(self, ctx)
        template += ") {"
        for p, s in node.actions:
            leg = f"    {p.accept(self, ctx)} => {{"
            for st in s:
                leg += f"{st.accept(self, ctx)}\n"
            leg += "}"
            template += leg
        template += "}"
        return template

    def visitAssign(self, node: Assign, ctx: WasmContext):
        raise NotImplementedError

    def visitPattern(self, node: Pattern, ctx):
        raise NotImplementedError

    def visitExpr(self, node: Expr, ctx):
        return f"({node.lhs.accept(self, ctx)} {node.op.accept(self, ctx)} {node.rhs.accept(self, ctx)})"

    def visitOperator(self, node: Operator, ctx):
        match node:
            case Operator.ADD:
                return "+"
            case Operator.SUB:
                return "-"
            case Operator.MUL:
                return "*"
            case Operator.DIV:
                return "/"
            case Operator.AND:
                return "&&"
            case Operator.OR:
                return "||"
            case Operator.EQ:
                return "=="
            case Operator.NEQ:
                return "!="
            case Operator.GT:
                return ">"
            case Operator.GE:
                return ">="
            case Operator.LT:
                return "<"
            case Operator.LE:
                return "<="
            case Operator.NOT:
                return "!"
            case _:
                raise Exception("unknown operator")

    def visitIdentifier(self, node: Identifier, ctx):
        var = ctx.find_var(node.name)
        if var == None:
            LOG.error(f"variable name {node.name} not found")
            raise Exception(f"variable {node.name} not found")
        else:
            if var.temp or var.rpc:
                return node.name
            else:
                return "self." + node.name

    def visitType(self, node: Type, ctx):
        def map_basic_type(name: str):
            match name:
                case "float":
                    return WasmBasicType("f32")
                case "int":
                    return WasmBasicType("i32")
                case "string":
                    return WasmBasicType("String")
                case "Instant":
                    return WasmBasicType("Instant")
                case _:
                    LOG.warning(f"unknown type: {name}")
                    return WasmType(name)

        name: str = node.name
        if name.startswith("Vec<"):
            last = name[4:].split(">")[0].strip()
            return WasmVecType("Vec", map_basic_type(last))
        elif name.startswith("Map<"):
            middle = name[4:].split(">")[0]
            key = middle.split(",")[0].strip()
            value = middle.split(",")[1].strip()
            return WasmMapType("HashMap", map_basic_type(key), map_basic_type(value))
        else:
            return map_basic_type(last)

    def visitFuncCall(self, node: FuncCall, ctx) -> str:
        raise NotADirectoryError

    def visitMethodCall(self, node: MethodCall, ctx) -> str:
        raise NotImplementedError

    def visitSend(self, node: Send, ctx) -> str:
        raise NotImplementedError

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError


class ExprResolver(Visitor):
    def __init__(self) -> None:
        pass

    def visitNode(self, node: Node, ctx) -> str:
        LOG.error(node.__class__.__name__, "being visited")
        raise Exception("Unreachable!")

    def visitLiteral(self, node: Literal, ctx) -> str:
        return node.value.replace("'", '"')

    def visitIdentifier(self, node: Identifier, ctx) -> str:
        return node.name

    def visitExpr(self, node: Expr, ctx) -> str:
        return node.lhs.accept(self, ctx) + str(node.op) + node.rhs.accept(self, ctx)

    def visitError(self, node: Error, ctx) -> str:
        return "ERROR"

    def visitMethodCall(self, node: MethodCall, ctx):
        return (
            node.obj.accept(self, ctx)
            + "."
            + node.method.name
            + "("
            + ",".join([a.accept(self, ctx) for a in node.args])
            + ")"
        )
