from compiler.ir.node import *
from compiler.ir.visitor import Visitor
from compiler.ir.backend.rusttype import *
from typing import List, Dict, Optional

class RustContext():
    def __init__(self) -> None:
        self.internal_states: List[RustVariable] = []
        self.name2var: Dict[str, RustVariable] = {}
        self.current_func: str = "unknown"
        self.params: List[RustVariable] = []
    def declare(self, name: str, rtype: RustType) -> None:
        pass
    
    def push_code(self, code: str) -> None:
        pass
    

class RustGenerator(Visitor):
    def __init__(self) -> None:
        super().__init__()

    def visitNode(self, node: Node, ctx: RustContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: RustContext) -> None:
        self.node.definition.accept(self, ctx)
        self.node.init.accept(self, ctx)
        self.node.req.accept(self, ctx)
        self.node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: RustContext) -> None:
        for (i, t) in node.internal:
            name = i.name
            rust_type = t.accept(self, ctx)
            ctx.declare(name, rust_type)
            

    def visitProcedure(self, node: Procedure, ctx: RustContext):
        ctx.current_func = node.name
        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None and name != f"rpc_{name}":
                raise Exception(f"param {name} not found")

        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)
        

    def visitStatement(self, node: Statement, ctx: RustContext) -> str:
        if node.stmt == None:
            return ";//NULL_STMT\n"
        else:
            if isinstance(node.stmt, Expr):
                return node.stmt.accept(self, ctx) + ";\n"
            else:
                return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: RustContext) -> str:
        template = "match ("
        template += node.expr.accept(self, ctx) + ") {"
        for (p, s) in node.actions:
            leg = f"    {p.accept(self, ctx)} =>"
            for st in s:
                leg += f"{st.accept(self, ctx)}\n"
            template += leg
        template += "}"
        return template

    def visitAssign(self, node: Assign, ctx):
        return f"{node.left.accept(self, ctx)} := {node.right.accept(self, ctx)}"

    def visitPattern(self, node: Pattern, ctx):
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return (
            f"{node.lhs.accept(self, ctx)} {node.op.name} {node.rhs.accept(self, ctx)}"
        )

    def visitIdentifier(self, node: Identifier, ctx):
        return node.name

    def visitType(self, node: Type, ctx):
        return node.name

    def visitFuncCall(self, node: FuncCall, ctx):
        ret = "FN_"
        ret += node.name.accept(self, ctx) + "( "
        for a in node.args:
            ret += f"{a.accept(self, ctx)} "
        return ret + ")"

    def visitMethodCall(self, node: MethodCall, ctx):
        ret = ""
        ret += node.obj.accept(self, ctx) + "."
        ret += node.method.name + "( "
        # print("args,", node.args)
        for a in node.args:
            if a != None:
                ret += f"{a.accept(self, ctx)} "
        return ret + ")"

    def visitSend(self, node: Send, ctx) -> str:
        return "Send: " + node.msg.accept(self, ctx) + "->" + node.direction

    def visitLiteral(self, node: Literal, ctx):
        return node.value

    def visitError(self, node: Error, ctx) -> str:
        # change this str to Literal
        if isinstance(node.msg, str):
            return "Err(" + node.msg + ")"
        else:
            return "Err(" + node.msg.accept(self, ctx) + ")"