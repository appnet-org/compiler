from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.utils import strip
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.visitor import Visitor
from compiler.element.node import *
from compiler.element.ir.type_inference.type import *
from compiler.proto import Proto

from compiler.element.backend.grpc import *
from compiler.element.backend.grpc.boilerplate import *
from compiler.element.backend.grpc.gotype import *
from compiler.element.backend.arpc.gotype import GoTypeNameGenerator, GoTypeInitGenerator


FUNC_INIT = "init"
FUNC_REQ = "req"
FUNC_RESP = "resp"

class ArpcContext:
    def __init__(
        self,
        element_name: str,
        proto: Proto,
        proto_module_name: str,
        tag: str = "0",
    ) -> None:
        self.element_name = element_name
        self.proto = proto
        self.proto_module_name = proto_module_name
        self.tag = tag
        # runtime
        self.current_procedure = ""
        self.global_var = set[str]()
        self.type_name_generator = GoTypeNameGenerator()
        self.type_init_generator = GoTypeInitGenerator()
        # used for generating unique temp variable names (e.g., in match statement)
        self.temp_var_idx = 0

        # code
        self.global_var_dec: List[str] = []
        self.global_var_init: List[str] = []
        # global var access needs helper functions because we need to deal with locks
        self.global_var_helper_code: Dict[str, List[str]] = {}
        self.global_func_code: List[str] = []
        self.procedure_code: Dict[str, List[str]] = {
            "init": [],
            "req": [],
            "resp": [],
        }
    
    def gen_temp_var(self) -> str:
        """
        Generate a unique temp variable name (e.g., in match statement)
        
        Returns:
            name of the temp variable
        """
        self.temp_var_idx += 1
        return f"temp_{self.temp_var_idx}"

    def push_code(self, code: str):
        self.procedure_code[self.current_procedure].append(code)


class ArpcGenerator(Visitor):
    def visitProgram(self, node: Program, ctx: ArpcContext):
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)
    
    def visitState(self, node: State, ctx: ArpcContext):
        for (var, _, consistency, _, _) in node.state:
            ctx.global_var.add(var.name)
            if consistency.name in ["strong", "weak"]:
                raise NotImplementedError("strong and weak consistencies are not supported for aRPC yet")
            t = var.get_type()

            # struct declaration
            type_name_str = t.accept(ctx.type_name_generator)
            # TODO: define an optional type helper to simplify the code
            if isinstance(t, OptionalType):
                ctx.global_var_dec.append(f"{var.name} {type_name_str[0]}")
                ctx.global_var_dec.append(f"{var.name}_ok {type_name_str[1]}")
            else:
                ctx.global_var_dec.append(f"{var.name} {type_name_str}")

            # struct initialization
            init_code = t.accept(ctx.type_init_generator)
            if isinstance(t, OptionalType):
                ctx.global_var_init.append(f"{var.name}: {init_code[0]},")
                ctx.global_var_init.append(f"{var.name}_ok: {init_code[1]},")
            else:
                ctx.global_var_init.append(f"{var.name}: {init_code},")
            
            # if the global state is a map/vec, we need to create a mutex for it
            # IR has a method "need_lock" to check if a type needs a lock
            if t.need_lock():
                ctx.global_var_dec.append(f"{var.name}_mu *sync.RWMutex")
                ctx.global_var_init.append(f"{var.name}_mu: &sync.RWMutex{{}},")
    
    def visitProcedure(self, node: Procedure, ctx: ArpcContext):
        ctx.current_procedure = node.name
        package_name = ctx.proto.package_name
        if ctx.current_procedure != "init":
            ctx.push_code(f"packet_raw := {package_name}.GetRequestRaw(packet.Payload)")
            ctx.push_code("_ = packet_raw")
        for stmt in node.body:
            stmt.accept(self, ctx)
        # add a return statement to pass go return check
        if ctx.current_procedure != "init" and (len(node.body) == 0 or not isinstance(node.body[-1], Send)):
            ctx.push_code("return packet, util.PacketVerdictPass, ctx, nil")
    
    def visitStatement(self, node: Statement, ctx: ArpcContext):
        if node.stmt is None:
            # pass statement don't need to be compiled in go
            ctx.push_code("// pass")
            return
        code = node.stmt.accept(self, ctx)
        if isinstance(code, str):
            ctx.push_code(code)
    
    def visitAssign(self, node: Assign, ctx: ArpcContext):
        # declare the variable if needed
        if node.left.declare is True:
            t = node.left.get_type()
            var_name = node.left.name
            type_name_str = t.accept(ctx.type_name_generator)
            if isinstance(t, OptionalType):
                ctx.push_code(f"var {var_name} {type_name_str[0]}")
                ctx.push_code(f"var {var_name}_ok {type_name_str[1]}")
            else:
                ctx.push_code(f"var {var_name} {type_name_str}")
        # assign the value
        expr_code = node.right.accept(self, ctx)
        left_code = node.left.accept(self, ctx)
        ctx.push_code(f"{left_code} = {expr_code}")
    
    def visitMatch(self, node: Match, ctx: ArpcContext):
        expr_code = node.expr.accept(self, ctx)
        # TODO: unify the equalization check of optional type and non-optional types
        if isinstance(node.expr.get_type(), OptionalType):
            # go doesn't have built-in match-action, use if-else to implement
            if node.actions[0][0].some:
                some_block = node.actions[0]
                none_block = node.actions[1]
            else:
                some_block = node.actions[1]
                none_block = node.actions[0]
            vname = some_block[0].value.name
            ctx.push_code(f"if {vname}, {vname}_ok := {expr_code}; {vname}_ok {{")
            for stmt in some_block[1]:
                stmt.accept(self, ctx)
            ctx.push_code("} else {")
            for stmt in none_block[1]:
                stmt.accept(self, ctx)
            ctx.push_code("}")
        else:
            temp_var = ctx.gen_temp_var()
            for i, action in enumerate(node.actions):
                pattern, stmts = action[0], action[1]
                condition_code = f"{temp_var} == {pattern.value.accept(self, ctx)}"
                if i == 0:
                    init_code = f"{temp_var} := {expr_code}"
                    code = f"if {init_code}; {condition_code} {{"
                else:
                    code = f"}} else if {condition_code} {{"
                ctx.push_code(code)
                for stmt in stmts:
                    stmt.accept(self, ctx)
            ctx.push_code("}")
    
    def visitExpr(self, node: Expr, ctx: ArpcContext) -> str:
        lcode = node.lhs.accept(self, ctx)
        op_code = node.op.accept(self, ctx)
        rcode = node.rhs.accept(self, ctx)
        return f"({lcode} {op_code} {rcode})"
    
    def visitRpcGet(self, node: MethodCall, ctx: ArpcContext) -> str:
        assert isinstance(node.args[0], Literal), "rpc.get argument must be a literal"
        field_name = node.args[0].value
        if strip(field_name) == "rpcid":
            return "string(packet.GetRPCID())"
        else:
            return f"packet_raw.Get{strip(field_name).capitalize()}()"
    
    def visitRpcSet(self, node: MethodCall, ctx: ArpcContext) -> str:
        assert isinstance(node.args[0], Literal), "rpc.set argument must be a literal"
        return f"packet_raw.Set{strip(node.args[0].value).capitalize()}({node.args[1].accept(self, ctx)})"

    @staticmethod
    def gen_map_get_helper_func(map_name: str, map_type: MapType, ctx: ArpcContext) -> str:
        """
        Generate a helper function for getting a value from a lock-protected global map
        
        Args:
            map_name: name of the map
            map_type: IR type of the map
            ctx: context object
        """
        key_type_str = map_type.key_type.accept(ctx.type_name_generator)
        value_type_str = map_type.value_type.accept(ctx.type_name_generator)
        code = f"func (e *{ctx.element_name}) GetMap{map_name}(key {key_type_str}) ({value_type_str}, bool) {{\n"
        code += f"e.{map_name}_mu.RLock()\n"
        code += f"defer e.{map_name}_mu.RUnlock()\n"
        code += f"val, ok := e.{map_name}[key]\n"
        code += f"return val, ok\n"
        code += f"}}\n"
        return code
    
    @staticmethod
    def gen_map_set_helper_func(map_name: str, map_type: MapType, ctx: ArpcContext) -> str:
        """
        Generate a helper function for setting a value to a lock-protected global map
        
        Args:
            map_name: name of the map
            map_type: IR type of the map
            ctx: context object
        """
        key_type_str = map_type.key_type.accept(ctx.type_name_generator)
        value_type_str = map_type.value_type.accept(ctx.type_name_generator)
        code = f"func (e *{ctx.element_name}) SetMap{map_name}(key {key_type_str}, value {value_type_str}) {{\n"
        code += f"e.{map_name}_mu.Lock()\n"
        code += f"defer e.{map_name}_mu.Unlock()\n"
        code += f"e.{map_name}[key] = value\n"
        code += f"}}\n"
        return code
    
    def visitMethodCall(self, node: MethodCall, ctx: ArpcContext) -> str:
        if node.obj.name == "rpc":
            match node.method:
                case MethodType.GET:
                    return self.visitRpcGet(node, ctx)
                case MethodType.SET:
                    return self.visitRpcSet(node, ctx)
                case MethodType.BYTE_SIZE:
                    return "float64(len(packet_raw))"

        match node.method:
            # we currently only support get and set on global map
            case MethodType.GET:
                assert isinstance(node.obj.get_type(), MapType), "rpc.get can only be called on global map"
                map_name = node.obj.name
                helper_func_name = f"GetMap{map_name}"
                key_code = node.args[0].accept(self, ctx)
                if ctx.global_var_helper_code.get(helper_func_name) is None:
                    ctx.global_var_helper_code[helper_func_name] = ArpcGenerator.gen_map_get_helper_func(map_name, node.obj.get_type(), ctx)
                return f"e.GetMap{map_name}({key_code})"
            case MethodType.SET:
                map_name = node.obj.name
                key_code = node.args[0].accept(self, ctx)
                value_code = node.args[1].accept(self, ctx)
                helper_func_name = f"SetMap{map_name}"
                if ctx.global_var_helper_code.get(helper_func_name) is None:
                    ctx.global_var_helper_code[helper_func_name] = ArpcGenerator.gen_map_set_helper_func(map_name, node.obj.get_type(), ctx)
                return f"e.SetMap{map_name}({key_code}, {value_code})"
            case _:
                raise NotImplementedError(f"method {node.method} is not supported")
    
    def visitIdentifier(self, node: Identifier, ctx: ArpcContext) -> str:
        # go doesn't have built-in optional type, so if the var is of type Optional, we need extra handling
        t = node.get_type()
        prefix = "e." if node.name in ctx.global_var else ""
        # TODO: global var of basic type is not protected by lock for now
        if not isinstance(t, OptionalType):
            return f"{prefix}{node.name}"
        else:
            return f"{prefix}{node.name}, {prefix}{node.name}_ok"
    
    def visitLiteral(self, node: Literal, ctx: ArpcContext) -> str:
        value_str = strip(node.value)
        t = node.get_type()
        if isinstance(t, StringType):
            value_str = f'"{value_str}"'
        return value_str
    
    def visitRandomFunc(self, node: RandomFunc, ctx: ArpcContext) -> str:
        lower_code = node.lower.accept(self, ctx)
        upper_code = node.upper.accept(self, ctx)
        return f"randomf({lower_code}, {upper_code})"
    
    def visitCurrentTimeFunc(self, node: CurrentTimeFunc, ctx: ArpcContext) -> str:
        return "current_time()"
    
    def visitTimeDiffFunc(self, node: TimeDiffFunc, ctx: ArpcContext) -> str:
        a_code = node.a.accept(self, ctx)
        b_code = node.b.accept(self, ctx)
        return f"time_diff({a_code}, {b_code})"
    
    def visitMinFunc(self, node: MinFunc, ctx: ArpcContext) -> str:
        a_code = node.a.accept(self, ctx)
        b_code = node.b.accept(self, ctx)
        return f"min({a_code}, {b_code})"
    
    def visitMaxFunc(self, node: MaxFunc, ctx: ArpcContext) -> str:
        a_code = node.a.accept(self, ctx)
        b_code = node.b.accept(self, ctx)
        return f"max({a_code}, {b_code})"
    
    def visitOperator(self, node: Operator, ctx: ArpcContext) -> str:
        match node:
            case Operator.ADD:
                return "+"
            case Operator.SUB:
                return "-"
            case Operator.MUL:
                return "*"
            case Operator.DIV:
                return "/"
            case Operator.EQ:
                return "=="
            case Operator.NEQ:
                return "!="
            case Operator.LT:
                return "<"
            case Operator.GT:
                return ">"
            case Operator.LE:
                return "<="
            case Operator.GE:
                return ">="
            case Operator.AND:
                return "&&"
            case Operator.OR:
                return "||"
            case Operator.NOT:
                return "!"
    
    def visitError(self, node: Error, ctx: ArpcContext) -> str:
        # TODO: add type inference for error message, now we assume it's a string
        return f"errors.New(\"{node.msg.accept(self, ctx)}\")"
            
    def visitSend(self, node: Send, ctx: ArpcContext):
        error_mode = ctx.current_procedure == "req" and node.direction == "Up"
        if not error_mode:
            ctx.push_code("return packet, util.PacketVerdictPass, ctx, nil")
        else:
            msg_code = node.msg.accept(self, ctx)
            ctx.push_code(f"return nil, util.PacketVerdictDrop, ctx, {msg_code}")