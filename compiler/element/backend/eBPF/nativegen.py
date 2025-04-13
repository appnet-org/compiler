from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.element.backend.eBPF.appnettype import DEFAULT_DECORATOR
from compiler.element.backend.eBPF.types import *
from compiler.element.backend.eBPF.types import NativeVariable
from compiler.element.frontend.printer import Printer
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.node import Identifier, Pattern
from compiler.element.visitor import Visitor

import traceback
class eBPFContext:
    def __init__(
        self,
        proto=None,
        method_name=None,
        request_message_name=None,
        response_message_name=None,
        message_field_types: Optional[dict[str, dict[str, str]]] = None,
        mode: str = "eBPF",
        element_name: str = "",
        tag: str = "0",
        # envoy_verbose: bool = False,
    ) -> None:
        self.appnet_var: list[dict[str, AppNetVariable]] = [
            {}
        ]  # The first scope is the states.
        self.native_var: list[dict[str, NativeVariable]] = [
            {}
        ]  # The first scope is the global scope
        self.global_var_def: list[str] = []
        self.init_code: list[str] = []
        self.on_tick_code: list[str] = []
        self.req_hdr_code: list[str] = []
        self.req_body_code: list[str] = []
        self.resp_hdr_code: list[str] = []
        self.resp_body_code: list[str] = []

        self.current_procedure: str = ""
        self.current_procedure_code: list[str] = []

        self.tmp_cnt: int = 0

        assert message_field_types is not None
        self.message_field_types: dict[str, dict[str, str]] = message_field_types

        # Dirty hack for get_rpc_header type inference
        self.most_recent_assign_left_type: Optional[AppNetType] = None

        # self.envoy_verbose = envoy_verbose
        self.global_state_lock_held = False

    def print_content(self):
        print(f"self.appnet_var = {self.appnet_var}")
        print(f"self.native_var = {self.native_var}")

        print(f"self.global_var_def = {self.global_var_def}")
        print(f"self.init_code = {self.init_code}")

        print(f"self.on_tick_code = {self.on_tick_code}")
        print(f"self.req_hdr_code = {self.req_hdr_code}")

        print(f"self.req_body_code = {self.req_body_code}")
        print(f"self.resp_hdr_code = {self.resp_hdr_code}")
        print(f"self.resp_body_code = {self.resp_body_code}")
        

        # self.current_procedure: str = ""
        # self.current_procedure_code: list[str] = []

        # self.tmp_cnt: int = 0

        # assert message_field_types is not None
        # self.message_field_types: dict[str, dict[str, str]] = message_field_types

        # # Dirty hack for get_rpc_header type inference
        # self.most_recent_assign_left_type: Optional[AppNetType] = None

        # # self.envoy_verbose = envoy_verbose
        # self.global_state_lock_held = False)


    def insert_envoy_log(self) -> None:
        # Insert ENVOY_LOG(info, stmt) after each statement in req and resp
        # This is for debugging.
        # Then we will have 2 times more lines of code.

        def process(codes: List[str]) -> List[str]:
            new_code = []
            for stmt in codes:
                if (
                    "for" in stmt
                    or "if" in stmt
                    or "else" in stmt
                    or "while" in stmt
                    or "{" in stmt
                    or "}" in stmt
                ) == False:
                    trans_stmt = stmt.replace('"', '\\"')
                    new_code.append(f'ENVOY_LOG(warn, "{trans_stmt}");')

                new_code.append(stmt)

            return new_code

        self.req_hdr_code = process(self.req_hdr_code)
        self.req_body_code = process(self.req_body_code)
        self.resp_hdr_code = process(self.resp_hdr_code)
        self.resp_body_code = process(self.resp_body_code)

    def push_appnet_scope(self) -> None:
        self.appnet_var.append({})

    def pop_appnet_scope(self) -> None:
        popped = self.appnet_var.pop()
        LOG.debug(f"appnet scope popped {popped}")

    def push_native_scope(self) -> None:
        self.native_var.append({})

    def pop_native_scope(self) -> None:
        self.native_var.pop()

    def push_code(self, code: str) -> None:
        code = code.strip()
        if "temp_1" in code:
            print(f"code = {code}")
        self.current_procedure_code.append(code)
        if code.endswith("{"):
            self.push_native_scope()

        if code.startswith("}"):
            self.pop_native_scope()

    def push_global_var_def(self, code: str) -> None:
        self.global_var_def.append(code)

    def new_temporary_name(self) -> str:
        self.tmp_cnt += 1
        return f"temp_{self.tmp_cnt}"

    def declareAppNetLocalVariable(
        self,
        name: str,
        rtype: AppNetType,
    ) -> AppNetVariable:
        if name in self.appnet_var[-1]:
            raise Exception(f"variable {name} already declared as a local variable")
        self.appnet_var[-1][name] = AppNetVariable(name, rtype)
        return self.appnet_var[-1][name]

    def declareAppNetState(
        self,
        name: str,
        rtype: AppNetType,
        decorator: dict[str, str] = DEFAULT_DECORATOR,
    ) -> AppNetVariable:
        if name in self.appnet_var[0]:
            raise Exception(f"variable {name} already declared")

        rtype.decorator = decorator
        self.appnet_var[0][name] = AppNetVariable(name, rtype)
        return self.appnet_var[0][name]

    def declareeBPFVar(
        self, name: str, rtype: NativeType, local: bool = True
    ) -> Tuple[NativeVariable, str]:
        # Declare a native var in the current scope.
        # It will return the declared variable and the declaration statement.
        # The declaration statement should be pushed to the current procedure code by the caller manually.
        if name in self.native_var[-1]:
            raise Exception(f"variable {name} already declared")
        self.native_var[-1][name] = NativeVariable(name, rtype, local)
        if local:
            return (self.native_var[-1][name], rtype.gen_decl_local(name))
        return (self.native_var[-1][name], rtype.gen_decl(name))

    def find_native_var(self, name: str) -> NativeVariable:
        for scope in reversed(self.native_var):
            if name in scope:
                return scope[name]
        raise Exception(f"variable {name} not found")

    def get_appnet_var(self, name: str) -> Tuple[AppNetVariable, bool]:
        for scope in reversed(self.appnet_var):
            if name in scope:
                return (scope[name], False)
        if name in self.appnet_var[0]:
            return (self.appnet_var[0][name], True)
        raise Exception(f"variable {name} not found")

    def find_appnet_var(self, name: str) -> Optional[Tuple[AppNetVariable, bool]]:
        try:
            return self.get_appnet_var(name)
        except:
            return None

    def getHeaderPath(self):
        return (
            "decoder_callbacks_->requestHeaders()"
            if self.current_procedure == "req"
            else "encoder_callbacks_->responseHeaders()"
        )

    def genBlockingHttpRequest(self, cluster_name: str, url: NativeVariable) -> None:

        assert url.type.is_string()
        assert self.current_procedure in ["req", "resp", "init"]

        self.push_code("{")
        self.push_code(f'   ENVOY_LOG(info, "[AppNet Filter] Blocking HTTP Request");')
        self.push_code(f"   Awaiter http_awaiter = Awaiter();")
        self.push_code(f"   this->http_awaiter_ = &http_awaiter;")
        self.push_code(f"   this->external_response_ = nullptr;")
        self.push_code(
            f'   this->sendHttpRequest("{cluster_name}", {url.name}, *this);'
        )
        self.push_code(f"   assert(this->appnet_coroutine_.has_value());")
        self.push_code(
            f'   ENVOY_LOG(info, "[AppNet Filter] Blocking HTTP Request Sent");'
        )

        if self.global_state_lock_held:
            # we need to release the lock. Otherwise, we will have a deadlock.
            self.push_code(f"   lock.unlock();")
        self.push_code(f"   co_await http_awaiter;")
        if self.global_state_lock_held:
            # we need to re-acquire the lock.
            self.push_code(f"   lock.lock();")

        self.push_code(
            f'   ENVOY_LOG(info, "[AppNet Filter] Blocking HTTP Request Done");'
        )
        self.push_code("}")

    def genBlockingWebdisRequest(self, url: NativeVariable) -> None:
        self.genBlockingHttpRequest("webdis_cluster", url)

    def genNonBlockingWebdisRequest(self, url: NativeVariable) -> None:
        assert url.type.is_string()
        assert self.current_procedure in ["req", "resp", "init"]

        self.push_code("{")
        self.push_code(
            f'  ENVOY_LOG(info, "[AppNet Filter] Non-Blocking Webdis Request");'
        )
        # make sure url start with SET
        self.push_code(f"  this->sendWebdisRequest({url.name}, *empty_callback_);")
        self.push_code("}")

    def get_current_msg_fields(self) -> dict[str, str]:
        assert self.current_procedure in ["req", "resp"]
        if self.current_procedure == "req":
            return self.message_field_types["request"]
        else:
            return self.message_field_types["response"]

    def get_callback_name(self):
        return (
            "this->decoder_callbacks_"
            if self.current_procedure == "req"
            else "this->encoder_callbacks_"
        )


class eBPFGenerator(Visitor):
    def __init__(self, placement: str) -> None:
        self.placement = placement
        if placement not in ["client", "server", "ambient"]:
            raise ValueError(f"invalid placement {placement}")

    def visitNode(self, node: Node, ctx: eBPFContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: eBPFContext) -> None:
        print("Enter visitProgram")
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)
        print("Exit visitProgram")

    def visitState(self, node: State, ctx: eBPFContext) -> None:
        print("Enter visitState")
        print(f"node = {node}")
        # Iterate through all state variables and declare them
        for (identifier, type, cons, comb, per) in node.state:
            assert per.name == "None" or per.name == "true" or per.name == "false"
            appType: AppNetType = type.accept(self, ctx)
            decorator = {
                "consistency": cons.name,
                "combiner": comb.name,
                "persistence": per.name,
            }
            state = ctx.declareAppNetState(identifier.name, appType, decorator)
            native_var, decl = ctx.declareeBPFVar(
                identifier.name, state.type.to_native(), False
            )
            print(f"decl = {decl}")
            state.native_var = native_var
            ctx.push_global_var_def(decl)

            # ===== Consistency Part =====
            assert decorator["consistency"] in ["strong", "weak", "None"]
            if decorator["consistency"] == "None":
                continue

            if appType.is_map() == False:
                raise Exception(
                    "Only map<string, string> type can have consistency for now"
                )

            assert isinstance(appType, AppNetMap)
            if appType.key.is_string() == False or (
                appType.value.is_string() == False and appType.value.is_int() == False
            ):
                raise Exception(
                    "Only map<string, string/int> can have consistency for now"
                )

            if decorator["consistency"] in ["weak"]:
                if (
                    appType.key.is_string() == False
                    or appType.value.is_string() == False
                ):
                    raise Exception(
                        "Only map<string, string> can have weak consistency for now"
                    )
                # for (auto& [key, value] : cache) {
                #   ENVOY_LOG(info, "[AppNet Filter] cache key={}, value={}", key, value);
                # }
                # this->sendWebdisRequest(const std::string path, int &callback)
                # path="/MGET/a/b/c/d"       to get a,b,c,d
                # path="/MSET/a/b/c/d"       to set a to b, c to d

                ctx.on_tick_code.append("{")
                # We simulate the overhead. Just set the value to the key, and then get them back from webdis.
                ctx.on_tick_code.append(f'  std::string geturl = "/MGET";')
                ctx.on_tick_code.append(f'  std::string seturl = "/MSET";')
                ctx.on_tick_code.append(f"  for (auto& [key, value] : {state.name}) {{")
                ctx.on_tick_code.append(f'    geturl += "/" + key;')
                ctx.on_tick_code.append(
                    f'    seturl += "/" + key + "/" + base64_encode(value, true);'
                )
                ctx.on_tick_code.append(f"  }}")
                ctx.on_tick_code.append(f"this->sendWebdisRequest(seturl);")
                # TODO: We should wait for the response of the set request, and then we can send the get request.
                ctx.on_tick_code.append(f"  this->sendWebdisRequest(geturl);")
                ctx.on_tick_code.append("}")
        print("Exit visitState")

    def visitProcedure(self, node: Procedure, ctx: eBPFContext):
        print("Enter visitProcedure")
        ctx.current_procedure = node.name
        ctx.current_procedure_code = []
        # self.appnet_var = [{'prob': <compiler.element.backend.eBPF.appnettype.AppNetVariable object at 0x7f1b6a189060>}, {}]
        ctx.push_appnet_scope()
        # self.native_var = [{'prob': <compiler.element.backend.eBPF.nativetype.NativeVariable object at 0x7f1b6a19dae0>}, {}]
        ctx.push_native_scope()

        ctx.global_state_lock_held = False
        # if len(ctx.appnet_var[0]) > 0:
        #     # TODO: We do very coarse-grained locking here.
        #     # If we have global states, we serialize all the request handling.
        #     if ctx.current_procedure != "init":
        #         # init() already has the lock in tempalte, for init global variable.
        #         ctx.push_code("std::unique_lock<std::mutex> lock(global_state_lock);")
        #         ctx.global_state_lock_held = True

        if node.name == "init":
            assert len(node.params) == 0
        else:
            assert node.name == "req" or node.name == "resp"
            # assert(len(node.params) == 1)
            assert node.params[0].name == "rpc"
            app_rpc = ctx.declareAppNetLocalVariable("rpc", AppNetRPC())
            native_rpc, decl = ctx.declareeBPFVar("rpc", app_rpc.type.to_native())
            app_rpc.native_var = native_rpc
            buffer_name = (
                "this->request_buffer_"
                if node.name == "req"
                else "this->response_buffer_"
            )
            # tmp_data_buf_name = ctx.new_temporary_name()
            # ctx.push_code(decl)
            # ctx.push_code(
            #     f"std::vector<uint8_t> {tmp_data_buf_name}({buffer_name}->length());"
            # )
            # ctx.push_code(
            #     f"{buffer_name}->copyOut(0, {buffer_name}->length(), {tmp_data_buf_name}.data());"
            # )
            # ctx.push_code(
            #     f"{native_rpc.name}.ParseFromArray({tmp_data_buf_name}.data() + 5, {tmp_data_buf_name}.size() - 5);"
            # )

        for stmt in node.body:
            stmt.accept(self, ctx)

        if node.name == "init":
            ctx.init_code = ctx.current_procedure_code
        elif node.name == "req":
            ctx.req_body_code = ctx.current_procedure_code
        elif node.name == "resp":
            ctx.resp_body_code = ctx.current_procedure_code
        else:
            raise Exception("unknown procedure")

        ctx.pop_appnet_scope()
        ctx.pop_native_scope()

        assert len(ctx.native_var) == 1
        print("Exit visitProcedure")

    def visitForeach(self, node: Foreach, ctx: eBPFContext):
        vec_name = node.var.name
        lambda_arg_name = node.func.arg.name

        ctx.push_appnet_scope()

        vec, is_state = ctx.get_appnet_var(vec_name)
        vec_type = vec.type
        assert isinstance(vec_type, AppNetVec)
        inner_type = vec_type.type

        ctx.push_code(
            f"for ({inner_type.to_native().type_name()} {lambda_arg_name} : {vec_name}) {{"
        )
        iter_var_appnet = ctx.declareAppNetLocalVariable(lambda_arg_name, inner_type)
        iter_var_native, _decl = ctx.declareeBPFVar(
            lambda_arg_name, inner_type.to_native()
        )
        iter_var_appnet.native_var = iter_var_native

        for stmt in node.func.body:
            stmt.accept(self, ctx)

        ctx.pop_appnet_scope()

        ctx.push_code("}")

    def visitStatement(self, node: Statement, ctx: eBPFContext):
        # if ctx.envoy_verbose:
        #     try:
        #         LOG.info(f"statement {node.accept(Printer(), ctx=None)}")
        #     except Exception as e:
        #         LOG.info(f"statement {node}, fail to parse")

        # A statement may be translated into multiple C++ statements.
        # These statements will be attached to ctx.current_procedure_code directly.
        print("Enter visitStatement")
        if isinstance(node.stmt, Foreach):
            return self.visitForeach(node.stmt, ctx)
            pass
        elif node.stmt is None:
            ctx.push_code("; // empty statement")
        elif isinstance(node.stmt, Send):
            # TODO: deal with Up and Down
            # TODO: support hooks in addition to the XDP hook
            if isinstance(node.stmt.msg, Error):
                ctx.push_code(f"return XDP_DROP;")
            else:
                assert isinstance(node.stmt.msg, Identifier), "currently do not support types beyond Error and Identifier"
                ctx.push_code(f"return XDP_PASS;")
        elif isinstance(node.stmt, Assign):
            if ctx.current_procedure != "init":
                ctx.push_code(f"// stmt {node.stmt}")
            ctx.print_content()
            retval = node.stmt.accept(self, ctx)
            ctx.print_content()
            if not isinstance(retval, list):
                retval = [retval]
            print("Exit visitStatement")
            return retval
        elif (isinstance(node.stmt, Match)
            or isinstance(node.stmt, Expr)
        ):
            ctx.push_code(f"// stmt {node.stmt}")
            ctx.print_content()
            retval = node.stmt.accept(self, ctx)
            print("After")
            ctx.print_content()
            # exit(0)
            if not isinstance(retval, list):
                retval = [retval]
            print("Exit visitStatement")
            return retval

        else:
            raise Exception("unknown statement")

    def visitIdentifier(self, node: Identifier, ctx) -> str:
        return node.name

    def generateOptionMatch(
        self,
        node: Match,
        ctx: eBPFContext,
        appnet_type: AppNetOption,
        native_expr: NativeVariable,
    ) -> None:

        some_pattern = None
        some_pattern_stmts = None

        none_pattern = None
        none_pattern_stmts = None

        assert len(node.actions) == 2  # Option type must have two patterns

        for pattern, stmts in node.actions:
            if pattern.some == True:
                some_pattern = pattern
                some_pattern_stmts = stmts
            else:
                none_pattern = pattern
                none_pattern_stmts = stmts

        if some_pattern is None or none_pattern is None:
            raise Exception("Some and None patterns must be both present")

        # Generate arms.

        assert some_pattern is not None
        assert none_pattern is not None
        assert some_pattern_stmts is not None
        assert none_pattern_stmts is not None

        assert isinstance(none_pattern.value, Literal)
        none_appnet_type, none_embed_str = none_pattern.value.accept(self, ctx)
        assert none_embed_str == "None"

        ctx.push_code(f"if ({native_expr.name}.has_value())")
        ctx.push_appnet_scope()
        ctx.push_code("{")

        assert isinstance(some_pattern.value, Identifier)
        bind_name: str = some_pattern.value.accept(self, ctx)
        bind_app_var = ctx.declareAppNetLocalVariable(bind_name, appnet_type.inner)
        bind_native_var, decl = ctx.declareeBPFVar(
            bind_name, appnet_type.inner.to_native()
        )
        bind_app_var.native_var = bind_native_var
        ctx.push_code(decl)

        ctx.push_code(f"{bind_name} = {native_expr.name}.value();")
        for stmt in some_pattern_stmts:
            stmt.accept(self, ctx)

        ctx.push_code("}")
        ctx.pop_appnet_scope()

        ctx.push_code("else")
        ctx.push_appnet_scope()
        ctx.push_code("{")

        for stmt in none_pattern_stmts:
            stmt.accept(self, ctx)

        ctx.pop_appnet_scope()
        ctx.push_code("}")

    def visitMatch(self, node: Match, ctx: eBPFContext) -> None:
        print("Enter visitMatch")
        print(f"type(node.expr) = {type(node.expr)}, node.actions = {node.actions}")
        print(f"node.expr.lhs = {node.expr.lhs}, node.expr.op = {node.expr.op}, node.expr.rhs = {node.expr.rhs}")
        appnet_type, native_expr = self.visitGeneralExpr(node.expr, ctx)
        print(f"appnet_type = {appnet_type}, native_expr = {native_expr}")
        if isinstance(native_expr.type, NativeOption):
            assert isinstance(appnet_type, AppNetOption)
            self.generateOptionMatch(node, ctx, appnet_type, native_expr)
            return
        # print("Before")
        # ctx.print_content()
        ctx.push_appnet_scope()
        # ====== Generate basic types match (no binding) ====
        # print("After")
        # ctx.print_content()
        # exit(0)
        first = True

        empty_pattern = None
        empty_pattern_stmts = None

        for pattern, stmts in node.actions:
            assert pattern.some == False
            if isinstance(pattern.value, Identifier):
                raise Exception("Only Some(x) binding is supported")
            else:
                assert isinstance(pattern.value, Literal)
                pattern_appnet_type, pattern_embed_str = pattern.value.accept(self, ctx)
                print(f"pattern_appnet_type={pattern_appnet_type}, pattern_embed_str={pattern_embed_str}")
                if pattern_embed_str == "_":
                    if empty_pattern is not None:
                        raise Exception(
                            "Only one empty pattern is allowed in a match statement"
                        )
                    empty_pattern = pattern
                    empty_pattern_stmts = stmts
                    continue
                if first == False:
                    ctx.push_code("else")
                ctx.push_code(f"if ({native_expr.name} == {pattern_embed_str})")
                ctx.push_appnet_scope()
                ctx.push_code("{")
                for stmt in stmts:
                    stmt.accept(self, ctx)
                ctx.push_code("}")
                ctx.pop_appnet_scope()
                first = False
        if empty_pattern is not None:
            assert empty_pattern_stmts is not None
            if first == True:
                raise Exception("Remove redundant empty pattern please")
            ctx.push_code("else")
            ctx.push_appnet_scope()
            ctx.push_code("{")
            for stmt in empty_pattern_stmts:
                stmt.accept(self, ctx)
            ctx.push_code("}")
            ctx.pop_appnet_scope() 

        ctx.pop_appnet_scope()

    def visitGeneralExpr(
        self, node, ctx: eBPFContext
    ) -> Tuple[AppNetType, NativeVariable]:
        print("Enter visitGeneralExpr")
        if isinstance(node, Literal):
            rhs_appnet_type, embed_str = node.accept(self, ctx)
            print(f"type(rhs_appnet_type) = {type(rhs_appnet_type)}, rhs_appnet_type = {rhs_appnet_type}, type(embed_str) = {type(embed_str)}, embed_str = {embed_str}")
            rhs_native_var, decl = ctx.declareeBPFVar(
                ctx.new_temporary_name(), rhs_appnet_type.to_native()
            )
            # Create a temporary variable to store the value of the literal
            ctx.push_code(decl)
            ctx.push_code(f"{rhs_native_var.name} = {embed_str};")

        elif isinstance(node, Identifier):
            rhs = None
            res = ctx.find_appnet_var(node.name)

            if res is not None:
                rhs, _is_state = res
            elif node.name in ctx.appnet_var[0]:
                rhs = ctx.appnet_var[0][node.name]
            elif node.name == "inf":
                # Special case.
                rhs = ctx.declareAppNetLocalVariable(node.name, AppNetInt())
                rhs_native_var, decl = ctx.declareeBPFVar(
                    ctx.new_temporary_name(), NativeInt()
                )
                ctx.push_code(decl)
                # set it to the maximum value of int
                ctx.push_code(
                    f"{rhs_native_var.name} = std::numeric_limits<int>::max();"
                )
                rhs.native_var = rhs_native_var
            elif node.name == "inf_f":
                rhs = ctx.declareAppNetLocalVariable(node.name, AppNetFloat())
                rhs_native_var, decl = ctx.declareeBPFVar(
                    ctx.new_temporary_name(), NativeFloat()
                )
                ctx.push_code(decl)
                # set it to the maximum value of float
                ctx.push_code(
                    f"{rhs_native_var.name} = std::numeric_limits<float>::max();"
                )
                rhs.native_var = rhs_native_var
            else:
                raise Exception(f"unknown variable {node.name}")

            assert rhs is not None
            assert rhs.native_var is not None
            rhs_native_var = rhs.native_var
            rhs_appnet_type = rhs.type

        elif isinstance(node, Expr):  # Maybe subclass of Expr
            # print(f"node.lhs = {node.lhs}, node.op = {node.op}, node.rhs = {node.rhs}")
            print("isinstance(node, Expr)")
            if isinstance(node, FuncCall):
                print(f"node.name = {node.name}, node.args = {node.args}")
                print(node.__str__())
            rhs_appnet_type, rhs_native_var = node.accept(self, ctx)

        else:
            raise Exception(f"unknown right hand side type={node.__class__.__name__}")

        assert isinstance(rhs_appnet_type, AppNetType)
        assert isinstance(rhs_native_var, NativeVariable)
        print("Exit visitGeneralExpr")
        return (rhs_appnet_type, rhs_native_var)

    def visitAssign(self, node: Assign, ctx: eBPFContext) -> None:
        print("Enter visitAssign")
        assert isinstance(node.left, Identifier) or isinstance(node.left, Pair)
        if ctx.current_procedure == "init":
            # b = BPF(text=bpf_code)
            # prob = b["prob"]
            # prob[ctypes.c_uint(0)] = ctypes.c_uint(50)
            # if ctx.current_procedure == "init":
            #     if ctx.find_appnet_var(lhs_name):
            #         ctx.push_code(f"{lhs_name}[ctypes.c_uint(0)] = {rhs_native_var.name};")
            #     print(f"{lhs_name} = {rhs_native_var.name};")
            #     exit(0)
            if isinstance(node.left, Identifier) and isinstance(node.right, Literal):
                lhs_name = node.left.name
                rhs_appnet_type, rhs_native_var = node.right.accept(self, ctx)
                if ctx.find_appnet_var(lhs_name):
                    ctx.push_code(f"{lhs_name} = b[\"{lhs_name}\"]")
                    ctx.push_code(f"{lhs_name}[ctypes.c_uint(0)] = ctypes.c_uint({rhs_native_var})")
            else:
                assert False, "New init case"
        else:
            if isinstance(node.left, Identifier):
                print("isinstance(node.left, Identifier)")
                lhs_name = node.left.name
                rhs_appnet_type, rhs_native_var = self.visitGeneralExpr(node.right, ctx)
                assert isinstance(rhs_appnet_type, AppNetType)
                assert isinstance(rhs_native_var, NativeVariable)
                if ctx.find_appnet_var(lhs_name):
                    ctx.push_code(f"{lhs_name}[0] = {rhs_native_var.name};")
                else:
                    ctx.push_code(f"{lhs_name} = {rhs_native_var.name};")
                # if ctx.find_appnet_var(lhs_name) is None:
                #     # This is a new local variable.
                #     LOG.debug(f"new local variable {lhs_name}")

                #     # Eval the right side.
                #     rhs_appnet_type, rhs_native_var = self.visitGeneralExpr(node.right, ctx)
                #     assert isinstance(rhs_appnet_type, AppNetType)
                #     assert isinstance(rhs_native_var, NativeVariable)

                #     lhs = ctx.declareAppNetLocalVariable(lhs_name, rhs_appnet_type)
                #     lhs_native, decl = ctx.declareeBPFVar(
                #         lhs_name, rhs_appnet_type.to_native()
                #     )
                #     lhs.native_var = lhs_native
                #     ctx.push_code(
                #         f"{lhs.native_var.type.type_name()} {lhs.name} = {rhs_native_var.name};"
                #     )

                # else:
                #     # Assigning the existing variable.

                #     lhs = ctx.get_appnet_var(lhs_name)[0]

                #     ctx.most_recent_assign_left_type = lhs.type
                #     rhs_appnet_type, rhs_native_var = self.visitGeneralExpr(node.right, ctx)
                #     ctx.most_recent_assign_left_type = None

                #     assert isinstance(rhs_appnet_type, AppNetType)
                #     assert isinstance(rhs_native_var, NativeVariable)
                #     assert lhs.native_var is not None
                #     assert lhs.native_var.type.is_same(rhs_native_var.type)

                #     ctx.push_code(f"{lhs.name} = {rhs_native_var.name};")

            elif isinstance(node.left, Pair):

                rhs_appnet_type, rhs_native_var = self.visitGeneralExpr(node.right, ctx)

                assert isinstance(rhs_appnet_type, AppNetType)
                assert isinstance(rhs_native_var, NativeVariable)

                assert isinstance(node.left.first, Identifier) and isinstance(
                    node.left.second, Identifier
                )
                assert isinstance(rhs_appnet_type, AppNetPair)
                first_name = node.left.first.name
                second_name = node.left.second.name

                # In pair assignment, we only support declaring new local variables.
                assert ctx.find_appnet_var(first_name) is None
                assert ctx.find_appnet_var(second_name) is None

                first_var_appnet = ctx.declareAppNetLocalVariable(
                    first_name, rhs_appnet_type.first
                )
                second_var_appnet = ctx.declareAppNetLocalVariable(
                    second_name, rhs_appnet_type.second
                )

                first_var_native, first_decl = ctx.declareeBPFVar(
                    first_name, rhs_appnet_type.first.to_native()
                )
                second_var_native, second_decl = ctx.declareeBPFVar(
                    second_name, rhs_appnet_type.second.to_native()
                )

                first_var_appnet.native_var = first_var_native
                second_var_appnet.native_var = second_var_native

                ctx.push_code(first_decl)
                ctx.push_code(second_decl)

                ctx.push_code(f"{first_var_native.name} = {rhs_native_var.name}.first;")
                ctx.push_code(f"{second_var_native.name} = {rhs_native_var.name}.second;")

                pass
            else:
                raise Exception("should not reach here")

    def acceptable_oper_type(
        self, lhs: AppNetType, op: Operator, rhs: AppNetType
    ) -> bool:
        if op in [
            Operator.ADD,
            Operator.SUB,
            Operator.MUL,
            Operator.DIV,
            Operator.GT,
            Operator.LT,
            Operator.GE,
            Operator.LE,
        ]:
            if lhs.is_arithmetic() and rhs.is_arithmetic():
                return True
        return False

    def visitPair(
        self, node: Pair, ctx: eBPFContext
    ) -> Tuple[AppNetType, NativeVariable]:
        assert isinstance(node, Pair)

        first_appnet_type, first_native_var = self.visitGeneralExpr(node.first, ctx)
        second_appnet_type, second_native_var = self.visitGeneralExpr(node.second, ctx)

        assert isinstance(first_appnet_type, AppNetType)
        assert isinstance(second_appnet_type, AppNetType)

        new_pair_type = AppNetPair(first_appnet_type, second_appnet_type)
        appnet_pair = ctx.declareAppNetLocalVariable(
            ctx.new_temporary_name(), new_pair_type
        )
        native_pair, decl = ctx.declareeBPFVar(
            appnet_pair.name, new_pair_type.to_native()
        )
        ctx.push_code(decl)
        ctx.push_code(f"{native_pair.name}.first = {first_native_var.name};")
        ctx.push_code(f"{native_pair.name}.second = {second_native_var.name};")

        return (new_pair_type, native_pair)

    # A temporary native variable will be generated to store the result of the expression.
    def visitExpr(
        self, node: Expr, ctx: eBPFContext
    ) -> Tuple[AppNetType, NativeVariable]:
        if isinstance(node, Pair):
            return self.visitPair(node, ctx)

        assert isinstance(node, Expr)

        lhs_appnet_type, lhs_nativevar = self.visitGeneralExpr(node.lhs, ctx)
        rhs_appnet_type, rhs_nativevar = self.visitGeneralExpr(node.rhs, ctx)

        assert isinstance(lhs_appnet_type, AppNetType)
        assert isinstance(rhs_appnet_type, AppNetType)
        assert isinstance(lhs_nativevar, NativeVariable)
        assert isinstance(rhs_nativevar, NativeVariable)

        # Make sure they are the same type. We don't support type conversion for now.

        assert lhs_appnet_type.is_same(rhs_appnet_type) or self.acceptable_oper_type(
            lhs_appnet_type, node.op, rhs_appnet_type
        )
        # assert(lhs_nativevar.type.is_same(rhs_nativevar.type))

        def get_expr_type(
            op: Operator, lhs_type: AppNetType, rhs_type: AppNetType
        ) -> AppNetType:
            if lhs_type.is_basic() and rhs_type.is_basic():
                if op in [Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV]:
                    assert lhs_type.is_arithmetic() and rhs_type.is_arithmetic()
                    return (
                        AppNetFloat()
                        if lhs_type.is_float() or rhs_type.is_float()
                        else AppNetInt()
                    )

                if op in [
                    Operator.EQ,
                    Operator.NEQ,
                    Operator.LT,
                    Operator.GT,
                    Operator.LE,
                    Operator.GE,
                ]:
                    assert (
                        lhs_type.is_same(rhs_type)
                        or lhs_type.is_arithmetic()
                        and rhs_type.is_arithmetic()
                    )
                    if lhs_type.is_bool():
                        assert op in [Operator.EQ, Operator.NEQ]
                    return AppNetBool()
            else:
                # String == and != are supported
                if op in [Operator.EQ, Operator.NEQ]:
                    assert lhs_type.is_string() and rhs_type.is_string()
                    return AppNetBool()
                else:
                    raise Exception("unsupported operator")
            raise Exception("unknown operator")

        expr_appnet_type = get_expr_type(node.op, lhs_appnet_type, rhs_appnet_type)

        new_var, decl = ctx.declareeBPFVar(
            ctx.new_temporary_name(), expr_appnet_type.to_native()
        )

        ctx.push_code(decl)
        if ctx.find_appnet_var(lhs_nativevar.name) and ctx.find_appnet_var(rhs_nativevar.name):
            assign_code = f'''
u32 {lhs_nativevar.name}_key = 0;
u32 *{lhs_nativevar.name}_val = {lhs_nativevar.name}.lookup(&{lhs_nativevar.name}_key);
u32 {rhs_nativevar.name}_key = 0;
u32 *{rhs_nativevar.name}_val = {rhs_nativevar.name}.lookup(&{rhs_nativevar.name}_key);
if ({lhs_nativevar.name}_val && {rhs_nativevar.name}_val) {{
    {new_var.name} = (*{lhs_nativevar.name}_val) {node.op.accept(self, ctx)} (*{rhs_nativevar.name}_val);    
}}'''
        elif ctx.find_appnet_var(lhs_nativevar.name):
            assign_code = f'''
u32 {lhs_nativevar.name}_key = 0;
u32 *{lhs_nativevar.name}_val = {lhs_nativevar.name}.lookup(&{lhs_nativevar.name}_key);
if ({lhs_nativevar.name}_val) {{
    {new_var.name} = (*{lhs_nativevar.name}_val) {node.op.accept(self, ctx)} {rhs_nativevar.name};    
}}'''
        elif ctx.find_appnet_var(rhs_nativevar.name):
            assign_code = f'''
u32 {rhs_nativevar.name}_key = 0;
u32 *{rhs_nativevar.name}_val = {rhs_nativevar.name}.lookup(&{rhs_nativevar.name}_key);
if ({rhs_nativevar.name}_val) {{
    {new_var.name} = {lhs_nativevar.name} {node.op.accept(self, ctx)} (*{rhs_nativevar.name}_val);    
}}'''
        else:
            assign_code = f"{new_var.name} = {lhs_nativevar.name} {node.op.accept(self, ctx)} {rhs_nativevar.name};"     
        # LEFT_NAME = ""
        # if ctx.find_appnet_var(lhs_nativevar.name):
        #     # TODO: consider various members in the array. Currently, we let index to be always 0
        #     # u32 prob_val_key = 0;
        #     # u32 *prob_val = prob.lookup(&prob_val_key);
            
        #     LEFT_NAME = lhs_nativevar.name + "[0]"
        # else:
        #     LEFT_NAME = lhs_nativevar.name
        # RIGHT_NAME = ""
        # if ctx.find_appnet_var(rhs_nativevar.name):
        #     RIGHT_NAME = rhs_nativevar.name + "[0]"
        # else:
        #     RIGHT_NAME = rhs_nativevar.name
        # print(f"LEFT_NAME = {LEFT_NAME}, RIGHT_NAME = {RIGHT_NAME}")
        # assign_code = f"{new_var.name} = {LEFT_NAME} {node.op.accept(self, ctx)} {RIGHT_NAME};"
        ctx.push_code(assign_code)

        return (expr_appnet_type, new_var)

    def visitOperator(self, node: Operator, ctx: eBPFContext) -> str:
        print("Enter visitOperator")
        if node == Operator.ADD:
            return "+"
        elif node == Operator.SUB:
            return "-"
        elif node == Operator.MUL:
            return "*"
        elif node == Operator.DIV:
            return "/"
        elif node == Operator.EQ:
            return "=="
        elif node == Operator.NEQ:
            return "!="
        elif node == Operator.LT:
            print("Exit visitOperator")
            return "<"
        elif node == Operator.GT:
            return ">"
        elif node == Operator.LE:
            return "<="
        elif node == Operator.GE:
            return ">="
        else:
            raise Exception("unknown operator")

    def visitType(self, node: Type, ctx: eBPFContext) -> AppNetType:
        if node.name == "int":
            return AppNetInt()
        elif node.name == "uint":
            return AppNetUInt()
        elif node.name == "float":
            return AppNetFloat()
        elif node.name == "string":
            return AppNetString()
        elif node.name == "bool":
            return AppNetBool()
        elif node.name == "Instant":
            return AppNetInstant()
        elif node.name.startswith("Map"):
            # For now, we only support 3 types of map:
            # Map<keytype, valuetype>
            # Map<keytype, <typea, typeb>>
            # Map<keytype, Vec<valuetype>>
            print(node.name)
            if node.name.count(",") == 1:
                # Map<keytype, valuetype> / Map<keytype, Vec<valuetype>>
                keytype_str = node.name[4:-1].split(",")[0].strip()
                valuetype_str = node.name[4:-1].split(",")[1].strip()
                key_type = appnet_type_from_str(keytype_str)
                value_type = appnet_type_from_str(valuetype_str)
                return AppNetMap(key_type, value_type)
            else:
                # Map<keytype, <typea, typeb>>
                # keytype
                keytype_str = node.name[4:-1].strip()[
                    node.name[4:-1].find("<") + 1 : node.name[4:-1].rfind(",")
                ]
                # <typea, typeb>
                valuepair_str = node.name[4:-1][
                    node.name[4:-1].find("<") : node.name[4:-1].rfind(">") + 1
                ]

                key_type = appnet_type_from_str(keytype_str)
                value_type = appnet_type_from_str(valuepair_str)
                return AppNetMap(key_type, value_type)
        elif node.name.startswith("Vec"):
            # Vec<string>
            valuetype_str = node.name[4:-1].strip()
            value_type = appnet_type_from_str(valuetype_str)
            return AppNetVec(value_type)
        else:
            print(node.name)
            raise Exception("unknown type")

    def genGeneralFuncCall(
        self,
        fname: str,
        node: MethodCall,
        args: List[Tuple[AppNetType, NativeVariable]],
        ctx: eBPFContext,
    ) -> Tuple[AppNetType, NativeVariable]:
        for func in APPNET_BUILTIN_FUNCS:
            func_instance: AppNetBuiltinFuncProto = func()
            if func_instance.appnet_name != fname:
                continue

            if fname == "metaget":
                for arg in node.args:
                    if isinstance(arg, Literal) and "meta" in arg.value:
                        func_instance.set_field_name(arg.value)

            # Check if the arguments match
            if not func_instance.instantiate([arg[0] for arg in args]):
                continue

            # Generate the code
            ret_native_var = func_instance.gen_code(ctx, *[arg[1] for arg in args])
            return (func_instance.ret_type(), ret_native_var)

        raise Exception(
            f"unknown function {fname}. Parameters matching failed: {[arg[0] for arg in args]}"
        )

    def visitFuncCall(
        self, node: FuncCall, ctx: eBPFContext
    ) -> Tuple[AppNetType, Optional[NativeVariable]]:
        args = [self.visitGeneralExpr(arg, ctx) for arg in node.args]
        fname = node.name.name
        return self.genGeneralFuncCall(fname, node, args, ctx)

    def visitMethodCall(
        self, node: MethodCall, ctx: eBPFContext
    ) -> Tuple[AppNetType, Optional[NativeVariable]]:

        fname = node.method.name.lower()
        args = [self.visitGeneralExpr(arg, ctx) for arg in node.args]

        obj_name = node.obj.name
        obj_appnet_var, is_global_state = ctx.get_appnet_var(obj_name)

        assert obj_appnet_var.native_var is not None
        return self.genGeneralFuncCall(
            fname, node, [(obj_appnet_var.type, obj_appnet_var.native_var)] + args, ctx
        )

    def visitSend(self, node: Send, ctx: eBPFContext):
        # Down: cluster side
        # Up: client side
        # Request: Up --> Down
        # Response: Down --> Up
        return
        match ctx.current_procedure:
            case "req":
                if node.direction == "Up":
                    # Make sure it's something like send(err('msg'), Up)
                    if isinstance(node.msg, Error):
                        assert node.msg.msg.type == DataType.STR
                        assert node.msg.msg.value != ""
                        # Forbidden 403

                        ctx.push_code(
                            "std::function<void(ResponseHeaderMap& headers)> modify_headers = [](ResponseHeaderMap& headers) {"
                        )
                        ctx.push_code(
                            '  headers.addCopy(LowerCaseString("grpc-status"), "1");'
                        )
                        ctx.push_code("};")

                        ctx.push_code(f"this->req_appnet_blocked_ = true;")
                        ctx.push_code(
                            f'this->decoder_callbacks_->sendLocalReply(Http::Code::Forbidden, "{node.msg.msg.value[1:-1]}", modify_headers, absl::nullopt, "");'
                        )
                        ctx.push_code("co_return;")
                    else:
                        raise Exception(
                            "req procedure should only send error message tp Up direction"
                        )
                elif node.direction == "Down":
                    ctx.push_code("if (this->in_decoding_or_encoding_ == false) {")
                    ctx.push_code(f"  this->decoder_callbacks_->continueDecoding();")
                    ctx.push_code("}")
                    ctx.push_code("co_return;")
                else:
                    raise Exception("unknown direction")

            case "resp":
                if node.direction == "Up":
                    ctx.push_code("if (this->in_decoding_or_encoding_ == false) {")
                    ctx.push_code(f"  this->encoder_callbacks_->continueEncoding();")
                    ctx.push_code("}")
                    ctx.push_code("co_return;")
                elif node.direction == "Down":
                    raise NotImplementedError(
                        "down direction is not supported in resp procedure yet"
                    )
                else:
                    raise Exception("unknown direction")
            case _:
                raise Exception("unknown procedure")

    def visitLiteral(self, node: Literal, ctx: eBPFContext) -> Tuple[AppNetType, str]:
        # Return a string that can be embedded in the C++ code directly.
        # A literal is a string, int, float, or bool
        try:
            print("Enter visitLiteral")
            print("node.type =", node.type, "node.value =", node.value, "type(node.value) =", type(node.value))
            if node.type == DataType.STR:
                # replace ' into "
                new_str = node.value.replace("'", '"')
                return (AppNetString(node.value[1:-1]), new_str)
            elif node.type == DataType.INT:
                return (AppNetInt(), str(node.value))
            elif node.type == DataType.FLOAT:
                print(f"Come here, str(node.value * 100) = {str(int(float(node.value) * 100))}")
                return (AppNetInt(), str(int(float(node.value) * 100)))
                # return (AppNetFloat(), str(node.value))
            elif node.type == DataType.BOOL:
                return (AppNetBool(), str(node.value).lower())
            else:
                types = [
                    (int, AppNetInt()),
                    (float, AppNetFloat()),
                    (str, AppNetString()),
                    (bool, AppNetBool()),
                ]
                for t, appnet_type in types:
                    # try cast
                    try:
                        t(node.value)
                        LOG.warning(f"cast {node.value} into a {t}")
                        if appnet_type == AppNetFloat():
                            print("return (AppNetInt(), str(node.value * 100))")
                            return (AppNetInt(), str(node.value * 100))
                        return (appnet_type, str(node.value))
                    except:
                        pass

                raise Exception("unknown literal type, and cast failed")
        finally:
            print("Exit visitLiteral")

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError


# ======================== BUILD-IN FUNCTIONS ========================


class AppNetBuiltinFuncProto:
    def instantiate(self, args: List[AppNetType]) -> bool:
        # This function accepts a list of AppNetType and returns a boolean indicating whether the given list of AppNetType is valid for this function
        raise NotImplementedError

    def ret_type(self) -> AppNetType:
        raise NotImplementedError

    def native_arg_sanity_check(self, native_args: List[NativeVariable]):
        # Check the given native arguments is consistent with the app args given by instantiate()
        assert self.prepared
        assert len(native_args) == len(self.appargs)
        for i in range(len(native_args)):
            assert native_args[i].type.is_same(self.appargs[i].to_native())

    def gen_code(self, ctx: eBPFContext, *args) -> NativeVariable:
        raise NotImplementedError

    def __init__(self, appnet_name: str, comments: str = ""):
        self.appnet_name = appnet_name
        self.comments = comments
        self.prepared = False
        self.appargs = []


class GetMapStrongConsistency(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetMap)
            and args[0].key.is_same(args[1])
        )
        ret = ret and args[0].decorator["consistency"] == "strong"
        if ret:
            assert isinstance(args[0], AppNetMap)
            assert isinstance(args[1], AppNetType)
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.prepared
        assert isinstance(self.appargs[0], AppNetMap)
        return AppNetOption(self.appargs[0].value)

    def gen_code(
        self, ctx: eBPFContext, map: NativeVariable, key: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([map, key])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)

        ctx.push_code("{")
        ctx.push_code(f"// save variable to {res_native_var.name}")

        # Construct the URL
        url_native_var, url_decl_str = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(url_decl_str)
        ctx.push_code(f'{url_native_var.name} = "/GET/" + {key.name};')
        ctx.genBlockingWebdisRequest(url_native_var)

        # Parse the response
        # which is put in ResponseMessagePtr external_response_;
        ctx.push_code("if (this->external_response_ == nullptr) {")
        ctx.push_code('   ENVOY_LOG(error, "[AppNet Filter] Webdis Request Failed");')
        ctx.push_code("   std::terminate();")
        ctx.push_code("}")

        ret_type = self.ret_type()
        assert isinstance(ret_type, AppNetOption)
        assert isinstance(ret_type.inner, AppNetString) or isinstance(
            ret_type.inner, AppNetInt
        )

        # return {"GET":null} or {"GET":"value"}
        # parse the response using json
        ctx.push_code(
            f"std::string response_str = this->external_response_->bodyAsString();"
        )
        ctx.push_code(
            f'ENVOY_LOG(info, "[AppNet Filter] Webdis Response: {{}}", response_str);'
        )

        # nlohmann::json j = nlohmann::json::parse(body);
        ctx.push_code(f"nlohmann::json j = nlohmann::json::parse(response_str);")
        ctx.push_code(f'if (j.contains("GET") && j["GET"].is_null() == false)')
        ctx.push_code("{")
        if isinstance(ret_type.inner, AppNetInt):
            # get it as string, and then cast to int
            ctx.push_code(f'std::string str_int = static_cast<std::string>(j["GET"]);')
            ctx.push_code(f"{res_native_var.name}.emplace(std::stoi(str_int));")
        else:
            ctx.push_code(
                f'  {res_native_var.name}.emplace(base64_decode(j["GET"], false));'
            )
        ctx.push_code("}")

        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("get", "map_strong")


class GetMap(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetMap)
            and args[0].key.is_same(args[1])
        )
        ret = ret and args[0].decorator["consistency"] in ["None", "weak"]
        if ret:
            assert isinstance(args[0], AppNetMap)
            assert isinstance(args[1], AppNetType)
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.prepared
        assert isinstance(self.appargs[0], AppNetMap)
        return AppNetOption(self.appargs[0].value)

    def gen_code(
        self, ctx: eBPFContext, map: NativeVariable, key: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([map, key])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)

        ctx.push_code(f"{res_native_var.name} = map_get_opt({map.name}, {key.name});")
        return res_native_var

    def __init__(self):
        super().__init__("get", "map")


class CurrentTime(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 0
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetInstant()

    def native_arg_sanity_check(self, args: List[NativeVariable]):
        assert self.prepared
        assert len(args) == 0

    def gen_code(self, ctx: eBPFContext, args=[]) -> NativeVariable:
        self.native_arg_sanity_check(args)

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        ctx.push_code(f"{res_native_var.name} = std::chrono::system_clock::now();")
        return res_native_var

    def __init__(self):
        super().__init__("current_time")


class TimeDiff(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetInstant)
            and isinstance(args[1], AppNetInstant)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetFloat()

    def gen_code(
        self, ctx: eBPFContext, end: NativeVariable, start: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([end, start])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        # cast into float in second
        ctx.push_code(
            f"{res_native_var.name} = std::chrono::duration_cast<std::chrono::duration<float>>({end.name} - {start.name}).count();"
        )
        return res_native_var

    def __init__(self):
        super().__init__("time_diff", "in_sec")


class Min(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and args[0].is_arithmetic() and args[1].is_arithmetic()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.prepared
        return (
            AppNetFloat()
            if self.appargs[0].is_float() or self.appargs[1].is_float()
            else AppNetInt()
        )

    def gen_code(
        self, ctx: eBPFContext, a: NativeVariable, b: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([a, b])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        ctx.push_code(f"{res_native_var.name} = my_min({a.name}, {b.name});")
        return res_native_var

    def __init__(self):
        super().__init__("min")


class GetRPCMeta(AppNetBuiltinFuncProto):
    def __init__(self):
        super().__init__("metaget")
        self.field_name: str = ""

    def set_field_name(self, field_name: str):
        self.field_name = field_name

    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetRPC)
            and isinstance(args[1], AppNetString)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert isinstance(self.msg_type_dict, dict)
        assert isinstance(self.appargs[1], AppNetString)
        field = self.appargs[1]
        assert isinstance(field.literal, str)
        return proto_type_to_appnet_type(self.msg_type_dict[field.literal])

    def gen_code(
        self, ctx: eBPFContext, rpc: NativeVariable, field: NativeVariable
    ) -> NativeVariable:
        self.msg_type_dict = ctx.get_current_msg_fields()
        self.native_arg_sanity_check([rpc, field])

        header_path = ctx.getHeaderPath()
        if "meta_status" in self.field_name:
            ctx.resp_hdr_code.append(
                f"""
                auto __status_tmp = this->{header_path}->get(LowerCaseString(":status"))[0]->value().getStringView();
                std::string status_value = std::string(__status_tmp.data(), __status_tmp.size());
                if (status_value == "200") {{
                    this->{header_path}->setCopy(LowerCaseString("meta_status"), "success");
                }} else {{
                    this->{header_path}->setCopy(LowerCaseString("meta_status"), "failure");
                }}
                """
            )

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(
            f"auto __tmp = this->{header_path}->get(LowerCaseString({field.name}))[0]->value().getStringView();"
        )
        ctx.push_code(native_decl_stmt)
        ctx.push_code(
            f"{res_native_var.name} = std::string(__tmp.data(), __tmp.size());"
        )

        return res_native_var


class GetRPCField(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetRPC)
            and isinstance(args[1], AppNetString)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert isinstance(self.msg_type_dict, dict)
        assert isinstance(self.appargs[1], AppNetString)
        field = self.appargs[1]
        assert isinstance(field.literal, str)
        return proto_type_to_appnet_type(self.msg_type_dict[field.literal])

    def gen_code(
        self, ctx: eBPFContext, rpc: NativeVariable, field: NativeVariable
    ) -> NativeVariable:
        self.msg_type_dict = ctx.get_current_msg_fields()
        self.native_arg_sanity_check([rpc, field])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)
        ctx.push_code(
            f"{res_native_var.name} = get_rpc_field({rpc.name}, {field.name});"
        )

        return res_native_var

    def __init__(self):
        super().__init__("get", "rpc_field")
        self.msg_type_dict = None


class SetMap(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 3
            and isinstance(args[0], AppNetMap)
            and args[0].key.is_same(args[1])
            and args[0].value.is_same(args[2])
        )
        ret = ret and args[0].decorator["consistency"] in ["None", "weak"]
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self,
        ctx: eBPFContext,
        map: NativeVariable,
        key: NativeVariable,
        value: NativeVariable,
    ) -> None:
        self.native_arg_sanity_check([map, key, value])

        ctx.push_code(f"{map.name}[{key.name}] = {value.name};")
        return None

    def __init__(self):
        super().__init__("set", "map")


class ByteSize(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        # TODO: wasm needs field name for now, discarded
        ret = len(args) == 2 and isinstance(args[0], AppNetRPC)
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetInt()

    def gen_code(
        self, ctx: eBPFContext, rpc: NativeVariable, field_name: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([rpc, field_name])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)
        ctx.push_code(f"{res_native_var.name} = {rpc.name}.ByteSizeLong();")

        return res_native_var

    def __init__(self):
        super().__init__("byte_size")


class RandomF(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and args[0].is_arithmetic() and args[1].is_arithmetic()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetFloat()

    def native_arg_sanity_check(self, native_args: List[NativeVariable]):
        # allow int and float to be mixed
        assert self.prepared
        assert len(native_args) == 2
        assert native_args[0].type.is_arithmetic()
        assert native_args[1].type.is_arithmetic()

    def gen_code(
        self, ctx: eBPFContext, a: NativeVariable, b: NativeVariable
    ) -> NativeVariable:
        print(f"a.type = {a.type}, a = {a.name}, b.type = {b.type}, b = {b.name}")
        self.native_arg_sanity_check([a, b])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        # get a random float number between a and b
        # ctx.push_code(
        #     f"{res_native_var.name} = {a.name} + static_cast <float> (rand()) / (static_cast <float> (RAND_MAX/({b.name} - {a.name})));"
        # )
        ctx.push_code(
            f"{res_native_var.name} = {a.name} * 100 + bpf_get_prandom_u32() % ({b.name} * 100 - {a.name} * 100);"
        )
        return res_native_var

    def __init__(self):
        super().__init__("randomf")


# set(record_req, size(record_req), get(rpc, 'body'))
class SetVector(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 3
            and isinstance(args[0], AppNetVec)
            and args[0].type.is_same(args[2])
            and isinstance(args[1], AppNetInt)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self,
        ctx: eBPFContext,
        vec: NativeVariable,
        index: NativeVariable,
        value: NativeVariable,
    ) -> None:
        self.native_arg_sanity_check([vec, index, value])
        ctx.push_code(f"if ({index.name} >= static_cast<int>({vec.name}.size())) {{")
        ctx.push_code(f"  {vec.name}.resize({index.name} + 1);")
        ctx.push_code("}")
        ctx.push_code(f"{vec.name}[{index.name}] = {value.name};")
        return None

    def __init__(self):
        super().__init__("set", "vector")


class SizeVector(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 1 and isinstance(args[0], AppNetVec)
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetInt()

    def gen_code(self, ctx: eBPFContext, vec: NativeVariable) -> NativeVariable:
        self.native_arg_sanity_check([vec])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)
        ctx.push_code(f"{res_native_var.name} = {vec.name}.size();")

        return res_native_var

    def __init__(self):
        super().__init__("size", "vector")


class SetRPCField(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        # TODO: For now, we assume the rpc field is a string
        ret = (
            len(args) == 3
            and isinstance(args[0], AppNetRPC)
            and isinstance(args[1], AppNetString)
            and args[2].is_string()
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self,
        ctx: eBPFContext,
        rpc: NativeVariable,
        field: NativeVariable,
        value: NativeVariable,
    ) -> None:
        self.native_arg_sanity_check([rpc, field, value])

        ctx.push_code(f"set_rpc_field({rpc.name}, {field.name}, {value.name});")
        buffer_name = (
            "request_buffer_" if ctx.current_procedure == "req" else "response_buffer_"
        )
        ctx.push_code(f"replace_payload(this->{buffer_name}, {rpc.name});")
        return None

    def __init__(self):
        super().__init__("set", "rpc_field")


class RPCID(AppNetBuiltinFuncProto):
    # func() -> uint
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 0
        if ret:
            self.prepared = True
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetUInt()

    def gen_code(self, ctx: eBPFContext) -> NativeVariable:
        rpc_id_str, decl = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(decl)
        ctx.push_code(f'{rpc_id_str.name} = "appnet-rpc-id";')

        rpcHeaderFunc: GetRPCHeader = GetRPCHeader()
        # Mock instantiate
        ret = rpcHeaderFunc.instantiate([AppNetRPC(), AppNetString()])
        assert ret == True

        ret = rpcHeaderFunc.gen_code(ctx, None, rpc_id_str, forced_ret_type=AppNetUInt())  # type: ignore
        return ret

    def __init__(self):
        super().__init__("rpc_id")


class SetMapStrongConsistency(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 3
            and isinstance(args[0], AppNetMap)
            and args[0].key.is_same(args[1])
            and args[0].value.is_same(args[2])
        )
        ret = ret and args[0].decorator["consistency"] == "strong"
        if ret:
            assert isinstance(args[0], AppNetMap)
            assert isinstance(args[1], AppNetType)
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self,
        ctx: eBPFContext,
        map: NativeVariable,
        key: NativeVariable,
        value: NativeVariable,
    ) -> None:
        self.native_arg_sanity_check([map, key, value])

        url_native_var, url_decl_str = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(url_decl_str)
        # if map.value is int, we need to convert it to string
        assert isinstance(self.appargs[0], AppNetMap)
        if isinstance(self.appargs[0].value, AppNetInt):
            ctx.push_code(
                f'{url_native_var.name} = "/SET/" + {key.name} + "/" + std::to_string({value.name});'
            )
        else:
            ctx.push_code(
                f'{url_native_var.name} = "/SET/" + {key.name} + "/" + base64_encode({value.name}, true);'
            )

        if ctx.current_procedure == "req":
            # If in resp or request, we send blocking call SET to webdis
            # Construct the URL
            ctx.genBlockingWebdisRequest(url_native_var)
        elif ctx.current_procedure in ["init", "resp"]:
            if ctx.current_procedure == "resp":
                LOG.warn(
                    "strong consistency operation is automatically converted to weak consistency in response procedure."
                )
            # we just send non blocking here.
            ctx.genNonBlockingWebdisRequest(url_native_var)

    def __init__(self):
        super().__init__("set", "map_strong")


class Max(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and args[0].is_arithmetic() and args[1].is_arithmetic()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.prepared
        return (
            AppNetFloat()
            if self.appargs[0].is_float() or self.appargs[1].is_float()
            else AppNetInt()
        )

    def gen_code(
        self, ctx: eBPFContext, a: NativeVariable, b: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([a, b])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        ctx.push_code(f"{res_native_var.name} = my_max({a.name}, {b.name});")
        return res_native_var

    def __init__(self):
        super().__init__("max")


class GetBackEnds(AppNetBuiltinFuncProto):
    # func(int) -> vec<int>
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 1 and args[0].is_int()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVec(AppNetInt())

    def gen_code(
        self, ctx: eBPFContext, backend_name: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([backend_name])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        # curl "http://10.96.88.99:8080/getReplica?key=23&service=ServiceB"
        # {"replica_id":[0,2]}

        # we need to send a request to the shard-manager cluster, and parse the response
        ctx.push_code("{")

        url_native, decl = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(decl)
        ctx.push_code(
            f'{url_native.name} = "/getReplica?key=" + std::to_string({backend_name.name}) + "&service=ServiceB";'
        )
        ctx.genBlockingHttpRequest("shard-manager", url_native)

        # parse the response
        ctx.push_code("if (this->external_response_ == nullptr) {")
        ctx.push_code(
            '   ENVOY_LOG(error, "[AppNet Filter] shard manager HTTP Request Failed");'
        )
        ctx.push_code("   std::terminate();")
        ctx.push_code("}")

        ctx.push_code(
            f"std::string response_str = this->external_response_->bodyAsString();"
        )
        ctx.push_code(
            f'ENVOY_LOG(info, "[AppNet Filter] Shard Manager Response: {{}}", response_str);'
        )
        ctx.push_code(f"nlohmann::json j = nlohmann::json::parse(response_str);")
        ctx.push_code(f'if (j.contains("replica_id"))')
        ctx.push_code("{")
        ctx.push_code(f'  for (auto& id : j["replica_id"])')
        ctx.push_code("{")
        ctx.push_code(f"    {res_native_var.name}.push_back(id);")
        ctx.push_code("}")
        ctx.push_code("}")
        ctx.push_code("else")
        ctx.push_code("{")
        ctx.push_code(
            f'  ENVOY_LOG(error, "[AppNet Filter] Shard Manager Response is in wrong format");'
        )
        ctx.push_code("  std::terminate();")
        ctx.push_code("}")

        ctx.push_code("}")
        return res_native_var

    def __init__(self):
        super().__init__("get_backends")


class RandomChoices(AppNetBuiltinFuncProto):
    # func(vec<T>, int) -> vec<T>

    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and isinstance(args[0], AppNetVec) and args[1].is_int()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.prepared
        return self.appargs[0]

    def gen_code(
        self, ctx: eBPFContext, vec: NativeVariable, num: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([vec, num])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        # declare a random number generator

        ctx.push_code("{")
        ctx.push_code(f"std::random_device rd;")
        ctx.push_code(f"std::mt19937 gen(rd());")
        ctx.push_code(f"std::uniform_int_distribution<> dis(0, {vec.name}.size() - 1);")
        ctx.push_code(f"std::vector<int> indices;")
        # We need to pick different random numbers out of the vector
        ctx.push_code(f"for (int i = 0; i < {num.name}; i++)")
        ctx.push_code("{")
        ctx.push_code(f"  int index = dis(gen);")
        ctx.push_code(f"  indices.push_back(index);")
        ctx.push_code("}")
        # random shuffle
        ctx.push_code(f"std::shuffle(indices.begin(), indices.end(), gen);")
        # copy the selected elements
        ctx.push_code(f"for (int i = 0; i < {num.name}; i++)")
        ctx.push_code("{")
        ctx.push_code(f"  {res_native_var.name}.push_back({vec.name}[indices[i]]);")
        ctx.push_code("}")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("random_choices")


class GetLoad(AppNetBuiltinFuncProto):
    # func(int) ->  pair<int, Instant>
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 1 and args[0].is_int()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetPair(AppNetInt(), AppNetInstant())

    def gen_code(
        self, ctx: eBPFContext, backend_id: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([backend_id])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)

        # curl "http://load-manager/getLoadInfo?service-name=my-service&replica-ids=0,1,2"
        # {"0":{"load":7,"timestamp":1724368802.8939054},"1":{"load":5,"timestamp":1724368802.8939054},"2":{"load":5,"timestamp":1724368802.8939054}}

        # we need to send a request to the load-manager cluster, and parse the response
        ctx.push_code("{")
        url_native_var, url_decl_str = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(url_decl_str)
        ctx.push_code(
            f'{url_native_var.name} = "/getLoadInfo?service-name=my-service&replica-ids=" + std::to_string({backend_id.name});'
        )
        ctx.genBlockingHttpRequest("load-manager", url_native_var)

        # parse the response
        ctx.push_code("if (this->external_response_ == nullptr) {")
        ctx.push_code(
            '   ENVOY_LOG(error, "[AppNet Filter] load manager HTTP Request Failed");'
        )
        ctx.push_code("   std::terminate();")
        ctx.push_code("}")

        ctx.push_code(
            f"std::string response_str = this->external_response_->bodyAsString();"
        )
        ctx.push_code(
            f'ENVOY_LOG(info, "[AppNet Filter] Load Manager Response: {{}}", response_str);'
        )
        ctx.push_code(f"nlohmann::json j = nlohmann::json::parse(response_str);")
        # we need to cast backend_id into string
        ctx.push_code(
            f"std::string __backend_id_str = std::to_string({backend_id.name});"
        )
        ctx.push_code(f"if (j.contains(__backend_id_str))")
        ctx.push_code("{")
        ctx.push_code(f'  {res_native_var.name}.first = j[__backend_id_str]["load"];')
        # translate the timestamp into std::chrono::system_clock::time_point
        ctx.push_code(
            f'  {res_native_var.name}.second = std::chrono::system_clock::from_time_t(j[__backend_id_str]["timestamp"]);'
        )
        ctx.push_code("}")
        ctx.push_code("else")
        ctx.push_code("{")
        ctx.push_code(
            f'  ENVOY_LOG(error, "[AppNet Filter] Load Manager Response is in wrong format");'
        )
        ctx.push_code("  std::terminate();")
        ctx.push_code("}")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("get_load")


class EstimateRIFDistribution(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 1 and args[0].is_vec()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVec(AppNetFloat())
    
    def gen_code(self, ctx: eBPFContext, backends: NativeVariable) -> NativeVariable:
        self.native_arg_sanity_check([backends])
        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)
        ctx.push_code("{")

        # generate query url
        ctx.push_code(f"nlohmann::json jsonlist = {backends.name};")
        url_native_var, url_decl_str = ctx.declareeBPFVar(
            ctx.new_temporary_name(), NativeString()
        )
        ctx.push_code(url_decl_str) 
        ctx.push_code(
            f'{url_native_var.name} = "/getEstimatedRIFDistribution?backends=" + jsonlist.dump();'
        )
        ctx.genBlockingHttpRequest("prequal-manager", url_native_var)

        # get response
        ctx.push_code("if (this->external_response_ == nullptr) {")
        ctx.push_code(
            '   ENVOY_LOG(error, "[AppNet Filter] prequal manager HTTP Request Failed");'
        )
        ctx.push_code("   std::terminate();")
        ctx.push_code("}")
        ctx.push_code(
            f"std::string response_str = this->external_response_->bodyAsString();"
        )
        ctx.push_code(
            f'ENVOY_LOG(info, "[AppNet Filter] Load Manager Response: {{}}", response_str);'
        )

        # parse response as vec<int>
        ctx.push_code(f"nlohmann::json j = nlohmann::json::parse(response_str);")
        ctx.push_code(f"{res_native_var.name} = j.get<std::vector<float>>();")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("estimate_RIF_distribution")


class Quantile(AppNetBuiltinFuncProto):
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2 and
            args[0].is_vec() and
            args[1].is_float()
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return self.appargs[0].type 
    
    def gen_code(self, ctx: eBPFContext, vec: NativeVariable, q: NativeVariable) -> NativeVariable:
        self.native_arg_sanity_check([vec, q])
        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)
        ctx.push_code("{")
        # get sorted vector
        ctx.push_code(f"std::vector<float> sorted_vec = {vec.name};")
        ctx.push_code("std::sort(sorted_vec.begin(), sorted_vec.end());")
        # find quantile position
        ctx.push_code(f"int idx = static_cast<int>({q.name} * sorted_vec.size()) - 1;")
        ctx.push_code(f"{res_native_var.name} = sorted_vec[idx];")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("quantile")


class GetRPCHeader(AppNetBuiltinFuncProto):
    # TODO: GetRPCHeader needs to infer the return type from the assign stmt.
    # TODO: For now we use the most recent assign stmt to infer the return type, which is quite dirty.

    # func(rpc, str) -> ? according to the assign stmt inference result.
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetRPC)
            and isinstance(args[1], AppNetString)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        assert self.ret_type_inferred is not None
        return self.ret_type_inferred

    def native_arg_sanity_check(self, native_args: List[NativeVariable]):

        assert self.prepared
        assert len(native_args) == 2
        assert native_args[1].type.is_string()

    def gen_code(
        self,
        ctx: eBPFContext,
        _rpc: NativeVariable,
        field: NativeVariable,
        *,
        forced_ret_type: Optional[AppNetType] = None,
    ) -> NativeVariable:
        # Note that we specialize the native arg check for this function because
        # 1. We don't really use RPC in the function body.
        # 2. RPCID will pass a None to here.
        self.native_arg_sanity_check([_rpc, field])

        if forced_ret_type is not None:
            self.ret_type_inferred = forced_ret_type
        else:
            assert ctx.most_recent_assign_left_type is not None
            self.ret_type_inferred = ctx.most_recent_assign_left_type

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())

        ctx.push_code(native_decl_stmt)
        ctx.push_code("{")

        # auto a = map->get(LowerCaseString("1"));
        # auto b = a[0]->value().getStringView();
        # auto str = std::string(b.data(), b.size());

        header_path = ctx.getHeaderPath()

        ctx.push_code(
            f"auto __tmp = this->{header_path}->get(LowerCaseString({field.name}))[0]->value().getStringView();"
        )
        ctx.push_code(
            f"std::string __tmp_str = std::string(__tmp.data(), __tmp.size());"
        )

        if self.ret_type_inferred.is_int() or self.ret_type_inferred.is_uint():
            # use stoul
            ctx.push_code(f"try {{")
            ctx.push_code(f"  {res_native_var.name} = std::stoul(__tmp_str);")
            ctx.push_code(f"}} catch (...) {{")
            ctx.push_code(
                f'  ENVOY_LOG(error, "[AppNet Filter] Failed to convert string to unsigned long");'
            )
            ctx.push_code("}")
        elif self.ret_type_inferred.is_string():
            ctx.push_code(f"{res_native_var.name} = __tmp_str;")
        else:
            raise NotImplementedError("only int/uint/string type is supported for now")

        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("get_rpc_header")
        self.ret_type_inferred: Optional[AppNetType] = None


class SetRPCHeader(AppNetBuiltinFuncProto):
    # func(rpc, str, ?) -> void
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 3
            and isinstance(args[0], AppNetRPC)
            and isinstance(args[1], AppNetString)
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self,
        ctx: eBPFContext,
        rpc: NativeVariable,
        field: NativeVariable,
        value: NativeVariable,
    ) -> None:
        self.native_arg_sanity_check([rpc, field, value])

        if self.appargs[2].is_int():
            header_path = ctx.getHeaderPath()
            ctx.push_code(
                f"this->{header_path}->setCopy(LowerCaseString({field.name}), std::to_string({value.name}));"
            )
        else:
            raise NotImplementedError("only int type is supported for now")

        return None

    def __init__(self):
        super().__init__("set_rpc_header")


class DeleteMap(AppNetBuiltinFuncProto):
    # func(map, key) -> void
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2
            and isinstance(args[0], AppNetMap)
            and args[0].key.is_same(args[1])
        )
        ret = ret and args[0].decorator["consistency"] in ["None", "weak"]
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self, ctx: eBPFContext, map: NativeVariable, key: NativeVariable
    ) -> None:
        self.native_arg_sanity_check([map, key])

        ctx.push_code(f"{map.name}.erase({key.name});")
        return None

    def __init__(self):
        super().__init__("delete", "map")


class SetMetadata(AppNetBuiltinFuncProto):
    # Example:
    # auto a = ProtobufWkt::Struct();
    # // add rpc-id to dynamic metadata
    # a.mutable_fields()->insert({"rpc-id", ValueUtil::stringValue("123")});
    # this->decoder_callbacks_->streamInfo().setDynamicMetadata("rpc-id", a);

    # func(str, T) -> void
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = (
            len(args) == 2 and isinstance(args[0], AppNetString) and args[1].is_basic()
        )
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetVoid()

    def gen_code(
        self, ctx: eBPFContext, key: NativeVariable, value: NativeVariable
    ) -> None:
        self.native_arg_sanity_check([key, value])

        if (
            isinstance(self.appargs[1], AppNetInt) == False
            and isinstance(self.appargs[1], AppNetUInt) == False
        ):
            raise NotImplementedError("only int/uint type is supported for now")

        ctx.push_code("{")
        # cast it into string first
        ctx.push_code(f"std::string __tmp_str = std::to_string({value.name});")
        ctx.push_code(f"ProtobufWkt::Struct __tmp;")
        ctx.push_code(
            f"__tmp.mutable_fields()->insert({{{{{key.name}, ValueUtil::stringValue(__tmp_str)}}}});"
        )
        ctx.push_code(
            f'{ctx.get_callback_name()}->streamInfo().setDynamicMetadata("appnet", __tmp);'
        )
        ctx.push_code("}")
        return None

    def __init__(self):
        super().__init__("set_metadata")


class GetMetadata(AppNetBuiltinFuncProto):
    # Example:
    # auto a = ProtobufWkt::Struct();
    # // fetch rpc-id from dynamic metadata
    # const envoy::config::core::v3::Metadata& metadata = this->encoder_callbacks_->streamInfo().dynamicMetadata();
    # const auto& rpc_id = metadata.filter_metadata().at("rpc-id").fields().at("rpc-id").string_value();
    # ENVOY_LOG(info, "[Ratelimit Filter] rpc-id={}", rpc_id);

    # func(str) -> ?
    # use ctx.most_recent_assign_left_type to infer the return type
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 1 and isinstance(args[0], AppNetString)
        if ret:
            self.prepared = True
            self.appargs = args
            self.ret_type_inferred = None
        return ret

    def ret_type(self) -> AppNetType:
        assert self.ret_type_inferred is not None
        return self.ret_type_inferred

    def gen_code(self, ctx: eBPFContext, key: NativeVariable) -> NativeVariable:
        self.native_arg_sanity_check([key])

        assert ctx.most_recent_assign_left_type is not None
        self.ret_type_inferred = ctx.most_recent_assign_left_type
        if (
            self.ret_type_inferred.is_int() == False
            and self.ret_type_inferred.is_uint() == False
        ):
            raise NotImplementedError("only int type is supported for now")

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)

        ctx.push_code("{")
        ctx.push_code(
            f"const envoy::config::core::v3::Metadata& metadata = {ctx.get_callback_name()}->streamInfo().dynamicMetadata();"
        )
        ctx.push_code(
            f'const auto& __tmp = metadata.filter_metadata().at("appnet").fields().at({key.name});'
        )
        ctx.push_code(f"std::string __tmp_str = __tmp.string_value();")
        ctx.push_code(f"try {{")
        # to int
        ctx.push_code(f"  {res_native_var.name} = std::stoi(__tmp_str);")
        ctx.push_code(f"}} catch (...) {{")
        ctx.push_code(
            f'  ENVOY_LOG(error, "[AppNet Filter] Failed to convert string to int (or uint)");'
        )
        ctx.push_code("}")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("get_metadata")


class Encrypt(AppNetBuiltinFuncProto):
    # func(msg: str, password: str) -> new_msg: str
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and args[0].is_string() and args[1].is_string()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetString()

    def gen_code(
        self, ctx: eBPFContext, msg: NativeVariable, password: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([msg, password])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)

        ctx.push_code("{")
        ctx.push_code(f"std::string __tmp_str;")
        ctx.push_code(f"std::string __password_str = {password.name};")
        ctx.push_code(f"std::string __msg_str = {msg.name};")
        ctx.push_code(f"for (size_t i = 0; i < __msg_str.size(); i++)")
        ctx.push_code("{")
        ctx.push_code(
            f"  __tmp_str.push_back(__msg_str[i] ^ __password_str[i % __password_str.size()]);"
        )
        ctx.push_code("}")
        ctx.push_code(f"{res_native_var.name} = __tmp_str;")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("encrypt")


class Decrypt(AppNetBuiltinFuncProto):
    # func(msg: str, password: str) -> new_msg: str
    def instantiate(self, args: List[AppNetType]) -> bool:
        ret = len(args) == 2 and args[0].is_string() and args[1].is_string()
        if ret:
            self.prepared = True
            self.appargs = args
        return ret

    def ret_type(self) -> AppNetType:
        return AppNetString()

    def gen_code(
        self, ctx: eBPFContext, msg: NativeVariable, password: NativeVariable
    ) -> NativeVariable:
        self.native_arg_sanity_check([msg, password])

        (
            res_native_var,
            native_decl_stmt,
        ) = ctx.declareeBPFVar(ctx.new_temporary_name(), self.ret_type().to_native())
        ctx.push_code(native_decl_stmt)

        ctx.push_code("{")
        ctx.push_code(f"std::string __tmp_str;")
        ctx.push_code(f"std::string __password_str = {password.name};")
        ctx.push_code(f"std::string __msg_str = {msg.name};")
        ctx.push_code(f"for (size_t i = 0; i < __msg_str.size(); i++)")
        ctx.push_code("{")
        ctx.push_code(
            f"  __tmp_str.push_back(__msg_str[i] ^ __password_str[i % __password_str.size()]);"
        )
        ctx.push_code("}")
        ctx.push_code(f"{res_native_var.name} = __tmp_str;")
        ctx.push_code("}")

        return res_native_var

    def __init__(self):
        super().__init__("decrypt")


APPNET_BUILTIN_FUNCS = [
    GetRPCMeta,
    GetRPCField,
    GetMap,
    CurrentTime,
    TimeDiff,
    Min,
    Max,
    SetMap,
    ByteSize,
    RandomF,
    SetVector,
    SizeVector,
    SetRPCField,
    RPCID,
    GetMapStrongConsistency,
    SetMapStrongConsistency,
    GetBackEnds,
    RandomChoices,
    GetLoad,
    GetRPCHeader,
    SetRPCHeader,
    DeleteMap,
    GetMetadata,
    SetMetadata,
    Encrypt,
    Decrypt,
    EstimateRIFDistribution,
    Quantile,
]
