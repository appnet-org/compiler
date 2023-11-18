from compiler.ir.node import *
from compiler.ir.visitor import Visitor
from compiler.ir.backend.rusttype import *
from typing import List, Dict, Optional

FUNC_REQ = "req"
FUNC_RESP = "resp"
FUNC_INIT = "init"

class RustContext():
    def __init__(self) -> None:
        self.internal_states: List[RustVariable] = []
        self.name2var: Dict[str, RustVariable] = {}
        self.current_func: str = "unknown"
        self.params: List[RustVariable] = []
        self.init_code: List[str] = []
        self.req_code: List[str] = []
        self.resp_code: List[str] = []
        
    def declare(self, name: str, rtype: RustType) -> None:
        if name in self.name2var:
            raise Exception(f"variable {name} already defined")
        else:
            var = RustVariable(name, rtype)
            self.name2var[name] = var
            self.internal_states.append(var)
    
    def push_code(self, code: str) -> None:
        if self.current_func == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_func == FUNC_REQ:
            self.req_code.append(code)
        elif self.current_func == FUNC_RESP:
            self.resp_code.append(code)
        else:
            raise Exception("unknown function")
    
    def find_var(self, name: str) -> Optional[RustVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None
        
    def explain(self) -> str:
        return f"Context.Explain:\n\t{self.internal_states}\n\t{self.name2var}\n\t{self.current_func}\n\t{self.params}\n\t{self.init_code}\n\t{self.req_code}\n\t{self.resp_code}"

class RustGenerator(Visitor):
    def __init__(self) -> None:
        super().__init__()

    def visitNode(self, node: Node, ctx: RustContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: RustContext) -> None:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: RustContext) -> None:
        for (i, t) in node.internal:
            name = i.name
            rust_type = t.accept(self, ctx)
            ctx.declare(name, rust_type)
            

    def visitProcedure(self, node: Procedure, ctx: RustContext):
        match node.name:
            case "init":
                ctx.current_func = FUNC_INIT
            case "req":
                ctx.current_func = FUNC_REQ
            case "resp":
                ctx.current_func = FUNC_RESP
            case _:
                raise Exception("unknown function")
        if node.name != "init":
            ctx.declare(f"rpc_{node.name}", RustRpcType("req", []))
            
        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
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

    def visitAssign(self, node: Assign, ctx: RustContext):
        name = node.left.name
        if ctx.find_var(lhs) == None:
            ctx.declare(lhs, RustType("unknown")) # declar temp
            lhs = "let mut temp_" + name
        else:
            lhs = name
        
        return f"{lhs} = {node.right.accept(self, ctx)};\n"

    def visitPattern(self, node: Pattern, ctx):
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return (
            f"{node.lhs.accept(self, ctx)} {node.op.name} {node.rhs.accept(self, ctx)}"
        )

    def visitIdentifier(self, node: Identifier, ctx):
        return node.name

    def visitType(self, node: Type, ctx):
        name: str = node.name
        if name.startswith("Vec<"):
            last = name[4:].split(">")[0]
            return RustVecType("Vec", RustType(last))
        elif name.startswith("Map<"):
            middle = name[4:].split(">")[0]
            key = middle.split(",")[0]
            value = middle.split(",")[1]
            return RustMapType("Map", RustType(key), RustType(value))
        else:
            return RustType(name)


    def visitFuncCall(self, node: FuncCall, ctx) -> str:
        fn_name = node.name.name
        if ctx.find_var(fn_name) == None:
            raise Exception(f"function {fn_name} not found")
        
        ret += node.name.accept(self, ctx) + "( "
        for a in node.args:
            ret += f"{a.accept(self, ctx)} "
        return ret + ")"

    def visitMethodCall(self, node: MethodCall, ctx) -> str:
        ret = ""
        ret += node.obj.name + "."
        var = ctx.find_var(node.obj.name)
        if var == None:
            raise Exception(f"object {node.obj.name} not found")
        else:
            args = [i.accept(self, ctx) for i in node.args if i is not None]
            t = var.type
            match node.method:
                case MethodType.GET:
                    ret += t.gen_get(args)
                case MethodType.SET:
                    ret += t.get_set(args)
                case _:
                    raise Exception("unknown method")
                
        return ret + ")"

    def visitSend(self, node: Send, ctx) -> str:
        if ctx.current_func == "unknown" or ctx.current_func == "init":
            raise Exception("send not in function")
        
        inner = node.msg.accept(self, ctx)
        inner = "let inner_gen = " + inner + ";\n"
        if ctx.current_func == FUNC_REQ:
            if node.direction == "NET":
                return f"{inner}self.tx_outputs()[0].send(inner_gen)?";
            elif node.direction == "APP":
                return f"{inner}self.rx_outputs()[0].send(inner_gen)?";
        elif ctx.current_func == FUNC_RESP:
            if node.direction == "NET":
                return f"{inner}self.tx_outputs()[0].send(inner_gen)?";            
            elif node.direction == "APP":
                return f"{inner}self.rx_outputs()[0].send(inner_gen)?";
        else:
            raise Exception("unknown function")


    def visitLiteral(self, node: Literal, ctx):
        return node.value

    def visitError(self, node: Error, ctx) -> str:
        return """EngineRxMessage::Ack(
                                        rpc_id,
                                        TransportStatus::Error(unsafe {
                                            NonZeroU32::new_unchecked(403)
                                        }),
                                    );"""