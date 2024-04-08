from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.element.backend.grpc import *
from compiler.element.backend.grpc.gotype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor


class GoContext:
    def __init__(
        self,
        proto=None,
        method_name=None,
        request_message_name=None,
        response_message_name=None,
        message_field_types=None,
        element_name: str = "",
    ) -> None:
        self.element_name: str = element_name  # Name of the generated element
        self.method_name: str = method_name  # Name of the RPC method
        self.request_message_name: str = request_message_name
        self.response_message_name: str = response_message_name
        self.message_field_types: Dict[str, Dict[str, str]] = message_field_types
        self.scope: List[Optional[Node]] = [None]
        self.temp_var_scope: Dict[str, Optional[Node]] = {}
        self.current_procedure: str = "unknown"  # Name of the current procedure (i.e., init/req/resp) being processed
        self.init_code: List[str] = []  # Code for initialization
        self.req_code: List[str] = []  # Code for request header processing
        self.resp_code: List[str] = []  # Code for response header processing
        self.req_code: List[str] = []  # Code for request body processing
        self.resp_code: List[str] = []  # Code for response body processing
        self.proto: str = proto
        self.internal_state_names: Set[str] = [
            "rpc_req",
            "rpc_resp",
        ]  # List of internal state names. Used by AccessAnalyzer
        self.internal_states: List[
            GoVariable
        ] = []  # List of internal state variables
        self.name2var: Dict[
            str, GoVariable
        ] = {}  # Mapping from names to variables

        # Maps to store the state (incl. RPC) operations on request/response headers and bodies
        self.access_ops: Dict[str, Dict[str, MethodType]] = {
            FUNC_INIT: {},
            FUNC_REQ: {},
            FUNC_RESP: {},
        }

    def declare(
        self,
        name: str,
        rtype: GoType,
        temp_var: bool,
        atomic: bool,
        consistency: str = None,
        combiner: str = None,
        persistence: bool = False,
    ) -> None:
        # This method declares a new variable in the Go context and add it to the name2var mapping
        if name in self.name2var:
            # Check for duplicate variable names
            raise Exception(f"variable {name} already defined")
        else:
            assert consistency != "weak" and consistency != "strong"    # TODO(nikolabo): synchronized state
            # Create a new GoVariable instance and add it to the name2var mapping
            var = GoVariable(
                name,
                rtype,
                temp_var,
                name == "rpc_request" or name == "rpc_response",
                atomic,
                consistency=consistency,
                combiner=combiner,
                persistence=persistence,
            )
            if atomic:
                # Only internal states are atomic
                self.internal_states.append(var)
                self.name2var[name] = var
            elif name == "rpc_request":
                self.name2var["rpc_req"] = var
            elif name == "rpc_response":
                self.name2var["rpc_resp"] = var
            else:
                # temp variable, not rpc_req/resp
                self.name2var[name] = var
                self.temp_var_scope[name] = self.scope[-1]

    def push_scope(self, s):
        self.scope.append(s)

    def pop_scope(self):
        new_dict = {}
        for name, var in self.name2var.items():
            if (
                name in self.temp_var_scope
                and self.temp_var_scope[name] == self.scope[-1]
            ):
                self.temp_var_scope.pop(name)
            else:
                new_dict[name] = var
        self.name2var = new_dict
        self.scope.pop()

    def gen_locks(self) -> tuple[str, str]:
        prefix = ""
        suffix = ""

        # Generate inners based on operations
        for v in self.internal_states:
            if v.name in self.access_ops[self.current_procedure]:
                access_type = self.access_ops[self.current_procedure][v.name]
                if access_type == MethodType.GET:
                    prefix = prefix + f"{v.name}_mutex.RLock();"
                    suffix = suffix + f"{v.name}_mutex.RUnlock();"
                elif access_type == MethodType.SET:
                    prefix = prefix + f"{v.name}_mutex.Lock();"
                    suffix = suffix + f"{v.name}_mutex.Unlock();"
                else:
                    raise Exception("unknown method in gen_inners.")
        return prefix, suffix

    def clear_temps(self) -> None:
        new_dic = {}
        for k, v in self.name2var.items():
            if not v.temp:
                new_dic[k] = v
        self.name2var = new_dic

    def push_code(self, code: str) -> None:
        # This method appends the given code to the appropriate list based on the current function context
        if self.current_procedure == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_procedure == FUNC_REQ:
            self.req_code.append(code)
        elif self.current_procedure == FUNC_RESP:
            self.resp_code.append(code)
        else:
            raise Exception(
                "unknown function"
            )  # Raise an exception if the current function context is unknown

    def find_var(self, name: str) -> Optional[GoVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None

    def gen_global_var_def(self) -> str:
        ret = ""
        for v in self.internal_states:
            ret = v.gen_init()
        return ret


class GoGenerator(Visitor):
    def __init__(self, placement: str) -> None:
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: GoContext) -> str:
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: GoContext) -> str:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        for v in ctx.internal_states:
            if v.init == "":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: GoContext):
        # Iterate through all internal state variables and declare them
        for (i, t, cons, comb, per) in node.internal:
            state_name = i.name
            state_go_type = t.accept(self, ctx)
            ctx.declare(
                state_name, state_go_type, False, True, cons.name, comb.name, per.name
            )

    def visitProcedure(self, node: Procedure, ctx: GoContext):
        # TODO: Add request and response header processing.
        match node.name:
            case "init":
                ctx.current_procedure = FUNC_INIT
                procedure_type = "init"  # unused, make python happy
            case "req":
                ctx.current_procedure = FUNC_REQ
                procedure_type = "Request"
            case "resp":
                ctx.current_procedure = FUNC_RESP
                procedure_type = "Response"
            case _:
                raise Exception("unknown function")
        ctx.clear_temps()
        if node.name == "req":
            name = "request"
        elif node.name == "resp":
            name = "response"
        else:
            name = node.name
        if name != "init":
            ctx.declare(f"rpc_{name}", GoRpcType(f"rpc_{name}", []), True, False)
        original_procedure = ctx.current_procedure

        # Boilerplate code for decoding the RPC message
        message_name, message = ctx.response_message_name, "reply"
        if procedure_type == "Request":
            message_name, message = ctx.request_message_name, "req"
        prefix_decode_rpc = f"""
            if rpc_{name}, ok := {message}.(*{ctx.proto}.{message_name}); ok {{
        """
        suffix_decode_rpc = "}"

        # If the procedure does not access the RPC message, then we do not need to decode the RPC message
        if ctx.current_procedure != FUNC_INIT:
            if original_procedure == FUNC_REQ:
                if "rpc_req" in ctx.access_ops[FUNC_REQ]:
                    ctx.push_code(prefix_decode_rpc)
            elif original_procedure == FUNC_RESP:
                if "rpc_resp" in ctx.access_ops[FUNC_RESP]:
                    ctx.push_code(prefix_decode_rpc)

        prefix_locks, suffix_locks = ("", "")
        if (ctx.current_procedure != FUNC_INIT): 
            # No need for locks in init, nobody else has access to the closure
            prefix_locks, suffix_locks = ctx.gen_locks()

        ctx.push_code(prefix_locks)

        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
                LOG.error(f"param {name} not found in VisitProcedure")
                raise Exception(f"param {name} not found")
        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)

        ctx.push_code(suffix_locks)

        if ctx.current_procedure != FUNC_INIT:
            if original_procedure == FUNC_REQ:
                if "rpc_req" in ctx.access_ops[FUNC_REQ]:
                    ctx.push_code(suffix_decode_rpc)
            elif original_procedure == FUNC_RESP:
                if "rpc_resp" in ctx.access_ops[FUNC_RESP]:
                    ctx.push_code(suffix_decode_rpc)

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return "// NULL_STMT"
        else:
            if isinstance(node.stmt, Expr) or isinstance(node.stmt, Send):
                return node.stmt.accept(self, ctx) + ";"
            else:
                return node.stmt.accept(self, ctx) + ";"

    def visitMatch(self, node: Match, ctx):
        first_pattern = node.actions[0][0]
        if first_pattern.some: 
            assert isinstance(first_pattern.value, Identifier)
            assert len(node.actions) == 2
            name = first_pattern.value.name
            if ctx.find_var(name) != None:
                LOG.error("variable already defined should not appear in Some")
                raise Exception(f"variable {name} already defined")
            # TODO: infer the correct type for the temp variable
            ctx.declare(name, GoBasicType("String"), True, False)  # declare temp

            # Grab the statements for some and none branches
            some_statements = none_statements = ""
            for st in node.actions[0][1]:
                some_statements += f"{st.accept(self, ctx)}\n"
            for st in node.actions[1][1]:
                none_statements += f"{st.accept(self, ctx)}\n"

            # Idiomatic check if key present in go
            # TODO(nikolabo): avoid clashing with user vars named ok?
            ret =   f"""if {name}, ok := {node.expr.accept(self, ctx)}; ok {{
                            {some_statements}
                        }} else {{
                            {none_statements}
                        }}
                    """
        else:
            ret = f"switch {node.expr.accept(self, ctx)}{{\n"
            for (p, s) in node.actions:
                ctx.push_scope(p)
                if isinstance(p.value, Literal) and p.value.value == "_":
                    leg = "default:\n"
                else:
                    leg = f"case {p.accept(self, ctx)}:\n"
                for st in s:
                    leg += f"       {st.accept(self, ctx)}\n"
                ret += leg
                ctx.pop_scope()
            ret += "}\n"
        return ret

    def visitAssign(self, node: Assign, ctx: GoContext):
        value = node.right.accept(self, ctx)
        var = ctx.find_var(node.left.name)
        if ctx.current_procedure != FUNC_INIT and var == None: # TODO(nikolabo): temp vars
            raise NotImplementedError
            ctx.declare(
                node.left.name,
                GoType("unknown"),
                True,
                False
            )
            return f"{node.left.accept(self, ctx)} := {node.right.accept(self, ctx)}"
        else:
            return f"{node.left.accept(self, ctx)} = {node.right.accept(self, ctx)}"

    def visitPattern(self, node: Pattern, ctx):
        # Some/None patterns are never visited, handled in visitMatch
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return (
            f"{node.lhs.accept(self, ctx)} {node.op.accept(self, ctx)} {node.rhs.accept(self, ctx)}"
        )
    
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
            return var.name

    def visitType(self, node: Type, ctx: GoContext):
        # TODO(nikolabo): vectors
        def map_basic_type(type_def: str):
            match type_def:
                case "float":
                    return GoBasicType("float64")
                case "int":
                    return GoBasicType("int32")
                case "uint":
                    return GoBasicType("uint32")
                case "string":
                    return GoBasicType("string")
                case "Instant":
                    return GoBasicType("float64")
                case _:
                    LOG.warning(f"unknown type: {type_def}")
                #     return WasmType(type_def)
        type_def: str = node.name
        if type_def.startswith("Map<"):
            temp = type_def[4:].split(">")[0]
            key_type = temp.split(",")[0].strip()
            value_type = temp.split(",")[1].strip()
            return GoMaptype(map_basic_type(key_type), map_basic_type(value_type))
        else:
            return map_basic_type(type_def)

    def visitFuncCall(self, node: FuncCall, ctx: GoContext) -> str:
        def func_mapping(fname: str) -> GoFunctionType:
            match fname:
                case "randomf":
                    return GoGlobalFunctions["random_float64"]
                case "randomu":
                    return GoGlobalFunctions["random_uint32"]
                case "current_time":
                    return GoGlobalFunctions["current_time"]
                case "min":
                    return GoGlobalFunctions["min_float64"]
                case "max":
                    return GoGlobalFunctions["max_float64"]
                case "time_diff":
                    return GoGlobalFunctions["time_diff"]
                case "encrypt":
                    raise NotImplementedError
                case "decrypt":
                    raise NotImplementedError
                case "rpc_id":
                    raise NotImplementedError
                case _:
                    LOG.error(f"unknown global function: {fname} in func_mapping")
                    raise Exception("unknown global function:", fname)
        
        fn_name = node.name.name
        fn: GoFunctionType = func_mapping(fn_name)
        types = fn.args
        args = [f"{i.accept(self, ctx)}" for i in node.args if i is not None]
        for idx, ty in enumerate(types):
            args[idx] = f"{ty.name}({args[idx]})"
        ret = fn.gen_call(args)
        return ret

    def visitMethodCall(self, node: MethodCall, ctx):
        var = ctx.find_var(node.obj.name)
        if var == None:
            LOG.error(f"{node.obj.name} is not declared")
            raise Exception(f"object {node.obj.name} not found")
        t = var.type
        args = [i.accept(self, ctx) for i in node.args]
        ret = var.name

        if var.rpc:
            match node.method:
                case MethodType.GET:
                    assert len(args) == 1
                    # snake_case pb field to PascalCase go pb field
                    split_snake = args[0].strip('"').split('_')
                    pascal_case = ''.join(w.title() for w in split_snake)
                    ret += f".{pascal_case}"
                case MethodType.SET:
                    raise NotImplementedError
                case MethodType.DELETE:
                    raise NotImplementedError
                case MethodType.SIZE:
                    pass
                case MethodType.BYTE_SIZE:
                    raise NotImplementedError
                case _:
                    raise Exception("unknown method", node.method)
        else:
            match node.method:
                case MethodType.GET:
                    ret += t.gen_get(args, node.obj.name, ctx.element_name)
                case MethodType.SET:
                    ret += t.gen_set(
                        args, node.obj.name, ctx.element_name, ctx.current_procedure
                    )
                case MethodType.DELETE:
                    ret += t.gen_delete(args)
                case MethodType.SIZE:
                    ret += t.gen_size()
                case _:
                    raise Exception("unknown method", node.method)
        return ret

    def visitSend(self, node: Send, ctx) -> str:
        if isinstance(node.msg, Error):
            if self.placement == "client":
                return f"""return status.Error(codes.Aborted, {node.msg.msg.accept(self, ctx)})"""
            else:
                assert self.placement == "server"
                return f"""return nil, status.Error(codes.Aborted, {node.msg.msg.accept(self, ctx)})"""
        else:
            return ""

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError
