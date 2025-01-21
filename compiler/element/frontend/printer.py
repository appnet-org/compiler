from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor


class Printer(Visitor):
    def __init__(self):
        self.indent = 0

    def visitNode(self, node: Node, ctx) -> str:
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx) -> str:
        return f"""{node.definition.accept(self, ctx)}
{node.init.accept(self, ctx)}
{node.req.accept(self, ctx)}
{node.resp.accept(self, ctx)}"""

    def visitState(self, node: State, ctx):
        ret = "State:\n"
        for (i, t, cons, comb, per) in node.state:
            i_val = i.accept(self, ctx)
            t_val = t.accept(self, ctx)
            cons_val = cons.accept(self, ctx)
            comb_val = comb.accept(self, ctx)
            per_val = per.accept(self, ctx)

            ret += f"{i_val}: {t_val} {cons_val} {comb_val} {per_val}\n"
        return ret + "\n"

    def visitProcedure(self, node: Procedure, ctx):
        ret = f"Procedure {node.name}: "
        for p in node.params:
            ret += f"{p.accept(self, ctx)}"
        ret += "\n"
        for s in node.body:
            ret += f"{s.accept(self, ctx)}\n"
        return ret

    def visitForeach(self, node: Foreach, ctx):
        ret = f"foreach {node.func.arg.name} in {node.var.name}\n"
        for stmt in node.func.body:
            ret += f"   {stmt.accept(self, ctx)}\n"
        return ret

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return "NULL_STMT;\n"
        else:
            if isinstance(node.stmt, Expr):
                return node.stmt.accept(self, ctx) + ";\n"
            else:
                return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx):
        ret = f"Match {node.expr.accept(self, ctx)}:\n"
        for (p, s) in node.actions:
            leg = f"    {p.accept(self, ctx)} =>\n"
            for st in s:
                leg += f"       {st.accept(self, ctx)}\n"
            ret += leg
        return ret

    def visitAssign(self, node: Assign, ctx):
        return f"{node.left.accept(self, ctx)} := {node.right.accept(self, ctx)}"

    def visitPattern(self, node: Pattern, ctx):
        return node.value.accept(self, ctx)

    def visitPair(self, node: Pair, ctx):
        return f"( {node.first.accept(self, ctx)}, {node.second.accept(self, ctx)} )"

    def visitExpr(self, node: Expr, ctx):
        return (
            f"{node.lhs.accept(self, ctx)} {node.op.name} {node.rhs.accept(self, ctx)}"
        )

    def visitIdentifier(self, node: Identifier, ctx):
        return node.name

    def visitConsistencyDecorator(self, node: ConsistencyDecorator, ctx):
        return node.name

    def visitCombinerDecorator(self, node: CombinerDecorator, ctx):
        return node.name

    def visitPersistenceDecorator(self, node: PersistenceDecorator, ctx):
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
