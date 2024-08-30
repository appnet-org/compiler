from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.element.backend.grpc import *
from compiler.element.backend.grpc.boilerplate import *
from compiler.element.backend.grpc.gotype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor


class GoContext:
    def __init__(
        self,
        proto=None,
        proto_module_name=None,
        proto_module_location=None,
        method_name=None,
        request_message_name=None,
        response_message_name=None,
        message_field_types=None,
        element_name: str = "",
        tag: str = "0",
    ) -> None:
        self.element_name: str = element_name  # Name of the generated element
        self.tag: str = tag  # version number, used for seamless migration
        self.method_name: str = method_name  # Name of the RPC method
        self.request_message_name: str = request_message_name
        self.response_message_name: str = response_message_name
        self.message_field_types: Dict[str, Dict[str, str]] = message_field_types
        self.scope: List[Optional[Node]] = [None]
        self.temp_var_scope: Dict[str, Optional[Node]] = {}
        self.current_procedure: str = "unknown"  # Name of the current procedure (i.e., init/req/resp) being processed
        self.on_tick_code: List[str] = []
        self.init_code: List[str] = []  # Code for initialization
        self.req_code: List[str] = []  # Code for request header processing
        self.resp_code: List[str] = []  # Code for response header processing
        self.req_code: List[str] = []  # Code for request body processing
        self.resp_code: List[str] = []  # Code for response body processing
        self.lock_prefix: str = ""  # Code for acquiring locks
        self.lock_suffix: str = ""  # Code for releasing locks
        self.proto: str = proto
        self.proto_module_name: str = proto_module_name
        self.proto_module_location: str = proto_module_location
        self.state_names: Set[str] = [
            "rpc",
        ]  # List of state names. Used by AccessAnalyzer
        self.strong_access_args: Dict[str, Expr] = {}
        self.states: List[GoVariable] = []  # List of state variables
        self.strong_consistency_states: List[
            GoVariable
        ] = []  # List of strong consistency variables
        self.weak_consistency_states: List[
            GoVariable
        ] = []  # List of weak consistency variables
        self.name2var: Dict[str, GoVariable] = {}  # Mapping from names to variables

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
            if consistency == "weak":
                self.weak_consistency_states.append(var)
            if consistency == "strong":
                self.strong_consistency_states.append(var)
                self.name2var[name] = var
            elif atomic:
                # Only internal states are atomic
                self.states.append(var)
                self.name2var[name] = var
            elif name == "rpc_request":
                self.name2var["rpc"] = var
            elif name == "rpc_response":
                self.name2var["rpc"] = var
            else:
                # temp variable, not rpc
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

    @property
    def strong_state_count(self) -> int:
        return len(self.strong_consistency_states)

    @property
    def weak_state_count(self) -> int:
        return len(self.weak_consistency_states)

    def gen_locks(self) -> tuple[str, str]:
        self.lock_prefix = ""
        self.lock_suffix = ""

        # Generate inners based on operations
        # Unlock in reverse order
        for v in self.states:
            if v.name in self.access_ops[self.current_procedure]:
                access_type = self.access_ops[self.current_procedure][v.name]
                if access_type == MethodType.GET:
                    self.lock_prefix = self.lock_prefix + f"{v.name}_mutex.RLock();"
                    self.lock_suffix = f"{v.name}_mutex.RUnlock();" + self.lock_suffix
                elif access_type == MethodType.SET:
                    self.lock_prefix = self.lock_prefix + f"{v.name}_mutex.Lock();"
                    self.lock_suffix = f"{v.name}_mutex.Unlock();" + self.lock_suffix
                else:
                    raise Exception("unknown method in gen_inners.")

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
        for v in self.states:
            ret += v.gen_init()
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
        for v in ctx.states:
            if v.init == "":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitState(self, node: State, ctx: GoContext):
        # Iterate through all state variables and declare them
        for (i, t, cons, comb, per) in node.state:
            state_name = i.name
            state_go_type = t.accept(self, ctx)
            ctx.declare(
                state_name, state_go_type, False, True, cons.name, comb.name, per.name
            )
        for var in ctx.weak_consistency_states:
            contents = {
                "state_name": var.name,
                "element_name": ctx.element_name,
            }
            ctx.on_tick_code.append(on_tick_template.format(**contents))

    def visitProcedure(self, node: Procedure, ctx: GoContext):
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

        # Consolidate strong reads into one request (TODO: frontend should check if it's safe to consolidate reads)
        prefix_strong_read, suffix_strong_read, res_defs_strong_read = "", "", ""
        if ctx.strong_state_count > 1 and ctx.current_procedure == FUNC_REQ:
            args, res_reads = "", ""
            for i, (sname, arg) in enumerate(ctx.strong_access_args.items()):
                var_type = ctx.name2var[sname].type
                assert (
                    type(var_type) is GoSyncMapType
                ), "only synchronized maps supported"
                res_defs_strong_read += f"var {sname}_read struct{{value {var_type.value.name}; ok bool}} \n"
                args += f' + "/" + {var_type.key.string_conversion(arg.accept(self, ctx))} + "_{sname}"'  # Append the sname to avoid key collision
                res_reads += f"""if remote_values[{i}] != nil {{
                                    {sname}_read = struct {{value {var_type.value.name}; ok bool}}{{*remote_values[{i}], true}}
                                }} else {{
                                    var zero {var_type.value.name}
                                    {sname}_read = struct {{value {var_type.value.name}; ok bool}}{{zero, false}}
                                }}\n"""  # assumes one key read per map

            # TODO(nikolabo): support consolidated sync read with different value types
            prefix_strong_read = f"""if remote_values, ok := func() ([]*{var_type.value.name}, bool) {{
                                            remote_read, err := http.Get("http://webdis-service-{ctx.element_name}:7379/MGET" {args})
                                            var res struct {{
                                                MGET []*{var_type.value.name}
                                            }}
                                            if err == nil {{
                                                body, _ := io.ReadAll(remote_read.Body)
                                                remote_read.Body.Close()
                                                if remote_read.StatusCode < 300 {{
                                                    _ = json.Unmarshal(body, &res)
                                                    return res.MGET, true
                                                }} else {{
                                                    log.Println(remote_read.StatusCode)
                                                }}
                                            }}
                                            return res.MGET, false
                                        }}(); ok {{
                                            if len(remote_values) == {len(ctx.strong_access_args.items())} {{
                                                {res_reads}"""
            suffix_strong_read = "}}"

        ctx.push_code(res_defs_strong_read)

        # Boilerplate code for decoding the RPC message
        # TODO: RPC should only be decoded at the time of first real access
        # (not including rpc status check)
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
                if "rpc" in ctx.access_ops[FUNC_REQ]:
                    ctx.push_code(prefix_decode_rpc)
            elif original_procedure == FUNC_RESP:
                if "rpc" in ctx.access_ops[FUNC_RESP]:
                    ctx.push_code(prefix_decode_rpc)

        ctx.push_code(prefix_strong_read)

        if ctx.current_procedure != FUNC_INIT:
            # No need for locks in init, nobody else has access to the closure
            ctx.gen_locks()

        ctx.push_code(ctx.lock_prefix)

        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
                LOG.error(f"param {name} not found in VisitProcedure")
                raise Exception(f"param {name} not found")
        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)

        ctx.push_code(ctx.lock_suffix)

        ctx.push_code(suffix_strong_read)

        if ctx.current_procedure != FUNC_INIT:
            if original_procedure == FUNC_REQ:
                if "rpc" in ctx.access_ops[FUNC_REQ]:
                    ctx.push_code(suffix_decode_rpc)
            elif original_procedure == FUNC_RESP:
                if "rpc" in ctx.access_ops[FUNC_RESP]:
                    ctx.push_code(suffix_decode_rpc)

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return "// NULL_STMT"
        else:
            if isinstance(node.stmt, Expr) or isinstance(node.stmt, Send):
                return node.stmt.accept(self, ctx) + ";"
            else:
                return node.stmt.accept(self, ctx) + ";"

    def visitMatch(self, node: Match, ctx: GoContext):
        first_pattern = node.actions[0][0]
        if first_pattern.some:
            assert isinstance(first_pattern.value, Identifier)
            assert len(node.actions) == 2
            name = first_pattern.value.name
            if ctx.find_var(name) == None:
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
            ret = f"""expr_eval := {node.expr.accept(self, ctx)}
                        if {name}, ok := expr_eval.value, expr_eval.ok; ok {{
                            _ = {name} // allow unused some() vars
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
        if (
            ctx.current_procedure != FUNC_INIT and var == None
        ):  # TODO(nikolabo): temp vars
            # raise NotImplementedError
            ctx.declare(node.left.name, GoType("unknown"), True, False)
            return f"{node.left.accept(self, ctx)} := {node.right.accept(self, ctx)}"
        else:
            return f"{node.left.accept(self, ctx)} = {node.right.accept(self, ctx)}"

    def visitPattern(self, node: Pattern, ctx):
        # Some/None patterns are never visited, handled in visitMatch
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return f"{node.lhs.accept(self, ctx)} {node.op.accept(self, ctx)} {node.rhs.accept(self, ctx)}"

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
                    return GoType(type_def)

        type_def: str = node.name
        if type_def.startswith("Vec<"):
            vec_type = type_def[4:].split(">")[0].strip()
            if node.consistency == "strong":
                assert False, "TODO: implement sync vec"
            return GoVecType(map_basic_type(vec_type))
        if type_def.startswith("Map<"):
            temp = type_def[4:].split(">")[0]
            key_type = temp.split(",")[0].strip()
            value_type = temp.split(",")[1].strip()
            if node.consistency == "strong":
                return GoSyncMapType(
                    map_basic_type(key_type), map_basic_type(value_type)
                )
            return GoMapType(map_basic_type(key_type), map_basic_type(value_type))
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
        if fn_name == "rpc_id":
            return "uint32(rpc_id)"
        fn: GoFunctionType = func_mapping(fn_name)
        types = fn.args
        args = [f"{i.accept(self, ctx)}" for i in node.args if i is not None]
        for idx, ty in enumerate(types):
            args[idx] = f"{ty.name}({args[idx]})"
        ret = fn.gen_call(args)
        return ret

    def visitMethodCall(self, node: MethodCall, ctx):
        var = ctx.find_var(node.obj.name)
        if (
            ctx.strong_state_count > 1
            and var.consistency == "strong"
            and node.method == MethodType.GET
        ):
            assert type(var.type) is GoSyncMapType
            return f"{var.name}_read"
        if var == None:
            LOG.error(f"{node.obj.name} is not declared")
            raise Exception(f"object {node.obj.name} not found")
        t = var.type
        args = [i.accept(self, ctx) for i in node.args]
        ret = var.name
        # For strongly consistent variables we read from external storage
        if var.consistency == "strong":
            ret = ""

        if var.rpc:
            match node.method:
                case MethodType.GET:
                    if args[0].strip('"').startswith("meta_status"):
                        ret = 'func() string {if err == nil{ return "success"} else {return "failure"}}()'
                    else:
                        ret += t.gen_get(args, var.name, ctx.element_name)
                case MethodType.SET:
                    ret += t.gen_set(
                        args, var.name, ctx.element_name, ctx.current_procedure
                    )
                case MethodType.DELETE:
                    raise NotImplementedError
                case MethodType.SIZE:
                    pass
                case MethodType.BYTE_SIZE:
                    ret = f"float64(proto.Size({var.name}))"
                case _:
                    raise Exception("unknown method", node.method)
        else:
            match node.method:
                case MethodType.GET:
                    if type(t) is GoMapType:
                        ret = ""
                    ret += t.gen_get(args, var.name, ctx.element_name)
                case MethodType.SET:
                    ret += t.gen_set(
                        args, var.name, ctx.element_name, ctx.current_procedure
                    )
                case MethodType.DELETE:
                    ret += t.gen_delete(args)
                case MethodType.SIZE:
                    ret = f"len({var.name})"
                case _:
                    raise Exception("unknown method", node.method)
        return ret

    def visitSend(self, node: Send, ctx: GoContext) -> str:
        if isinstance(node.msg, Error) and node.direction == "Up":
            if self.placement == "client":
                return (
                    ctx.lock_suffix
                    + f"""return status.Error(codes.Aborted, {node.msg.msg.accept(self, ctx)})"""
                )
            else:
                assert self.placement == "server"
                return (
                    ctx.lock_suffix
                    + f"""return nil, status.Error(codes.Aborted, {node.msg.msg.accept(self, ctx)})"""
                )
        else:
            return ""

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError
