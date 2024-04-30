from compiler.element.backend.grpc.gogen import GoContext
from compiler.element.node import *
from compiler.element.backend.grpc import *
from compiler.element.visitor import Visitor


def set_method(name: str, ctx: GoContext, method: MethodType):
    # If var name is not in the state definition, it's probably a temporary variable.
    if name not in ctx.state_names:
        return

    if (
        name not in ctx.access_ops[ctx.current_procedure]
        or ctx.access_ops[ctx.current_procedure][name] != MethodType.SET
    ):
        ctx.access_ops[ctx.current_procedure][name] = method


class AccessAnalyzer(
    Visitor
):  # AccessAnalyzer is used to analyze the IR and record the access operations.
    # The operations are then used to avoid unnecessary locks and RPC decode when generating the corresponding WASM code.
    def __init__(self, placement: str):
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: GoContext) -> str:
        pass

    def visitProgram(self, node: Program, ctx: GoContext) -> str:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitState(self, node: State, ctx: GoContext):
        for (var, _, cons, _, _) in node.state:
            ctx.state_names.append(var.name)
            # if cons.name == "strong":
            #     ctx.strong_access_args[var.name] = ""

    def visitProcedure(self, node: Procedure, ctx: GoContext):
        match node.name:
            case "init":
                ctx.current_procedure = FUNC_INIT
            case "req":
                ctx.current_procedure = FUNC_REQ
            case "resp":
                ctx.current_procedure = FUNC_RESP
            case _:
                raise Exception("unknown function")
        for b in node.body:
            b.accept(self, ctx)

    def visitStatement(self, node: Statement, ctx: GoContext):
        if node.stmt != None:
            node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: GoContext):
        node.expr.accept(self, ctx)
        for p, s in node.actions:
            for st in s:
                st.accept(self, ctx)

    def visitAssign(self, node: Assign, ctx: GoContext):
        set_method(node.left.name, ctx, MethodType.SET)
        node.right.accept(self, ctx)

    def visitPattern(self, node: Pattern, ctx: GoContext):
        pass

    def visitExpr(self, node: Expr, ctx: GoContext):
        if isinstance(node.lhs, Identifier):
            set_method(node.lhs.name, ctx, MethodType.GET)
        if isinstance(node.rhs, Identifier):
            set_method(node.rhs.name, ctx, MethodType.GET)

        node.lhs.accept(self, ctx)
        node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx: GoContext):
        pass

    def visitConsistencyDecorator(self, node: ConsistencyDecorator, ctx: GoContext):
        pass

    def visitCombinerDecorator(self, node: CombinerDecorator, ctx: GoContext):
        pass

    def visitPersistenceDecorator(self, node: PersistenceDecorator, ctx: GoContext):
        pass

    def visitType(self, node: Type, ctx: GoContext):
        pass

    def visitFuncCall(self, node: FuncCall, ctx: GoContext):
        for arg in node.args:
            if isinstance(arg, Identifier):
                set_method(arg.name, ctx, MethodType.GET)
            arg.accept(self, ctx)

    def visitMethodCall(self, node: MethodCall, ctx: GoContext):
        # Add access operations to the corresponding function.
        # If there are multiple operations on the same object, the set takes priority.
        set_method(node.obj.name, ctx, node.method)

        # Handle nested method calls
        for arg in node.args:
            arg.accept(self, ctx)

    def visitSend(self, node: Send, ctx: GoContext) -> str:
        pass

    def visitLiteral(self, node: Literal, ctx: GoContext):
        pass

    def visitError(self, node: Error, ctx: GoContext) -> str:
        pass
