from copy import deepcopy
from typing import Dict, List, Optional, Set

from compiler.element.backend.envoy_native.types import *

from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.node import Identifier, Pattern
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

    self.tmp_cnt: int = 0

  def push_code(self, code: str) -> None:
    self.current_procedure_code.append(code)

    if code.endswith("{"):
      self.native_var.append({})

    if code.startswith("}"):
      self.native_var.pop()


  def push_global_var_def(self, code: str) -> None:
    self.global_var_def.append(code)

  def new_temporary_name(self) -> str:
    self.tmp_cnt += 1
    return f"temp_{self.tmp_cnt}"

  def declareAppNetVariable(
    self,
    name: str,
    rtype: AppNetType,
  ) -> AppNetVariable:
    if name in self.appnet_local_var:
      raise Exception(f"variable {name} already declared")
    if name in self.appnet_state:
      raise Exception(f"variable {name} already declared in global scope")
    self.appnet_local_var[name] = AppNetVariable(name, rtype)
    return self.appnet_local_var[name]

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
    # Declare a native var in the current scope.
    # It will return the declared variable and the declaration statement.
    # The declaration statement should be pushed to the current procedure code by the caller manually.
    if name in self.native_var[-1]:
      raise Exception(f"variable {name} already declared")
    self.native_var[-1][name] = NativeVariable(name, rtype)
    return (self.native_var[-1][name], rtype.gen_decl(name))


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
      assert(per.name == "None" or  per.name == "true" or per.name == "false")
      appType: AppNetType = type.accept(self, ctx)
      decorator = {
        "consistency": cons.name,
        "combiner": comb.name,
        "persistence": per.name,
      }
      state = ctx.declareAppNetState(identifier.name, appType, decorator)
      native_var, decl = ctx.declareNativeVar(identifier.name, state.type.to_native())
      state.native_var = native_var
      ctx.push_global_var_def(decl)


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
      ctx.req_body_code = ctx.current_procedure_code
    elif node.name == "resp":
      ctx.resp_body_code = ctx.current_procedure_code
    else:
      raise Exception("unknown procedure")
    
    ctx.appnet_local_var = {}
    assert(len(ctx.native_var) == 1)

  def visitStatement(self, node: Statement, ctx: NativeContext):
    # A statement may be translated into multiple C++ statements.
    # These statements will be attached to ctx.current_procedure_code directly.
    
    if node.stmt is None:
      ctx.push_code("; // empty statement")
    elif isinstance(node.stmt, Send) \
      or isinstance(node.stmt, Assign) \
      or isinstance(node.stmt, Match) \
      or isinstance(node.stmt, Expr):

      ctx.push_code(f"// stmt {node.stmt}")

      retval = node.stmt.accept(self, ctx)
      if not isinstance(retval, list):
        retval = [retval]
      return retval
    
    else:
      raise Exception("unknown statement")

  def visitIdentifier(self, node: Identifier, ctx) -> str:
    return node.name

  def generateOptionMatch(self, node: Match, ctx: NativeContext, appnet_type: AppNetOption, native_expr: NativeVariable) -> None:
    some_pattern = None
    some_pattern_stmts = None

    none_pattern = None
    none_pattern_stmts = None

    assert(len(node.actions) == 2) # Option type must have two patterns

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

    assert(some_pattern is not None)
    assert(none_pattern is not None)
    assert(some_pattern_stmts is not None)
    assert(none_pattern_stmts is not None)

    assert(isinstance(some_pattern.value, Literal))
    none_appnet_type, none_embed_str = none_pattern.value.accept(self, ctx)
    assert(none_embed_str == "None")

    ctx.push_code(f"if ({native_expr.name}.is_some())")
    ctx.push_code("{")

    assert(isinstance(some_pattern.value, Identifier))
    bind_name: str = some_pattern.value.accept(self, ctx)
    ctx.declareAppNetVariable(bind_name, appnet_type.inner)
    ctx.declareNativeVar(bind_name, appnet_type.inner.to_native())
    ctx.push_code(f"{bind_name} = {native_expr.name}.value();")
    for stmt in some_pattern_stmts:
      stmt.accept(self, ctx)

    ctx.push_code("}")
    ctx.push_code("else")
    ctx.push_code("{")

    for stmt in none_pattern_stmts:
      stmt.accept(self, ctx)

    ctx.push_code("}")

  def visitMatch(self, node: Match, ctx: NativeContext) -> None:
    appnet_type, native_expr = self.visitGeneralExpr(node.expr, ctx)
    
    if isinstance(native_expr.type, NativeOption):
      assert(isinstance(appnet_type, AppNetOption))
      self.generateOptionMatch(node, ctx, appnet_type, native_expr)
      return

    # ====== Generate basic types match (no binding) ====

    first = True

    empty_pattern = None
    empty_pattern_stmts = None

    for pattern, stmts in node.actions:
      assert(pattern.some == False)
      if isinstance(pattern.value, Identifier):
        raise Exception("Only Some(x) binding is supported")
      else:
        assert(isinstance(pattern.value, Literal))
        pattern_appnet_type, pattern_embed_str = pattern.value.accept(self, ctx)

        if pattern_embed_str == "_":
          if empty_pattern is not None:
            raise Exception("Only one empty pattern is allowed in a match statement")
          empty_pattern = pattern
          empty_pattern_stmts = stmts
          continue

        if first == False:
          ctx.push_code("else")

        ctx.push_code(f"if ({native_expr.name} == {pattern_embed_str})")
        ctx.push_code("{")
        for stmt in stmts:
          stmt.accept(self, ctx)
        ctx.push_code("}")
        first = False
    if empty_pattern is not None:
      assert(empty_pattern_stmts is not None)
      if first == True:
        raise Exception("Remove redundant empty pattern please")
      ctx.push_code("else")
      ctx.push_code("{")
      for stmt in empty_pattern_stmts:
        stmt.accept(self, ctx)
      ctx.push_code("}")

  def visitGeneralExpr(self, node, ctx: NativeContext) -> Tuple[AppNetType, NativeVariable]:

    if isinstance(node, Literal):
      rhs_appnet_type, embed_str = node.accept(self, ctx)

      # Create a temporary variable to store the value of the literal
      rhs_native_var, decl = ctx.declareNativeVar(
        ctx.new_temporary_name(), rhs_appnet_type.to_native())
      ctx.push_code(decl)
      ctx.push_code(f"{rhs_native_var.name} = {embed_str};")
      
    elif isinstance(node, Expr):
      rhs_appnet_type, rhs_native_var = node.accept(self, ctx)

    elif isinstance(node, Identifier):
      rhs = None
      if node.name in ctx.appnet_local_var:
        rhs = ctx.appnet_local_var[node.name]
      elif node.name in ctx.appnet_state:
        rhs = ctx.appnet_state[node.name]
      else:
        raise Exception(f"unknown variable {node.name}")
      
      assert(rhs is not None)
      assert(rhs.native_var is not None)
      rhs_native_var = rhs.native_var
      rhs_appnet_type = rhs.type
    else:
      raise Exception(f"unknown right hand side type={node.__class__.__name__}")
    
    assert(isinstance(rhs_appnet_type, AppNetType))
    assert(isinstance(rhs_native_var, NativeVariable))
    return (rhs_appnet_type, rhs_native_var)

  def visitAssign(self, node: Assign, ctx: NativeContext) -> None:
    lhs_name = node.left.name

    rhs_appnet_type, rhs_native_var = self.visitGeneralExpr(node.right, ctx)

    assert(isinstance(rhs_appnet_type, AppNetType))
    assert(isinstance(rhs_native_var, NativeVariable))
    


    lock_acquire_stmt = None
    lock_release_stmt = None

    if lhs_name not in ctx.appnet_local_var and lhs_name not in ctx.appnet_state:
      # This is a new local variable
      lhs = ctx.declareAppNetVariable(lhs_name, rhs_appnet_type)
      lhs.native_var = rhs_native_var

    else:
      if lhs_name in ctx.appnet_local_var:
        # Existing AppNet variable
        lhs = ctx.appnet_local_var[lhs_name]
      elif lhs_name in ctx.appnet_state:
        # Existing AppNet state
        lhs = ctx.appnet_state[lhs_name]

        # std::mutex global_state_lock;
        lock_acquire_stmt = f"global_state_lock.lock(); // {lhs_name}_lock will be acquired here"
        lock_release_stmt = f"global_state_lock.unlock(); // {lhs_name}_lock will be released here"

      else:
        raise Exception("unknown variable")
      
      assert(isinstance(rhs_native_var, NativeVariable))
      assert(lhs.native_var is not None)
      assert(lhs.native_var.type.is_same(rhs_native_var.type))

      if lock_acquire_stmt is not None:
        ctx.push_code(lock_acquire_stmt)
      ctx.push_code(f"{lhs.name} = {rhs_native_var.name};")

      if lock_release_stmt is not None:
        ctx.push_code(lock_release_stmt)

  # A temporary native variable will be generated to store the result of the expression.
  def visitExpr(self, node: Expr, ctx: NativeContext) -> Tuple[AppNetType, NativeVariable]:
    assert(isinstance(node, Expr))
    
    lhs_appnet_type, lhs_nativevar = self.visitGeneralExpr(node.lhs, ctx)
    rhs_appnet_type, rhs_nativevar = self.visitGeneralExpr(node.rhs, ctx)
    
    assert(isinstance(lhs_appnet_type, AppNetType))
    assert(isinstance(rhs_appnet_type, AppNetType))
    assert(isinstance(lhs_nativevar, NativeVariable))
    assert(isinstance(rhs_nativevar, NativeVariable))

    # Make sure they are the same type. We don't support type conversion for now.
    assert(lhs_appnet_type.is_same(rhs_appnet_type))
    assert(lhs_nativevar.type.is_same(rhs_nativevar.type))

    def get_expr_type(op: Operator, lhs_type: AppNetType, rhs_type: AppNetType) -> AppNetType:
      if lhs_type.is_basic() and rhs_type.is_basic():
        if op in [Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV]:
          assert(lhs_type.is_same(rhs_type))
          assert(lhs_type.is_arithmetic())
          return lhs_type
        
        if op in [Operator.EQ, Operator.NEQ, Operator.LT, Operator.GT, Operator.LE, Operator.GE]:
          assert(lhs_type.is_same(rhs_type))
          if lhs_type.is_bool():
            assert(op in [Operator.EQ, Operator.NEQ])
          return AppNetBool()
      else:
        # String == and != are supported
        if op in [Operator.EQ, Operator.NEQ]:
          assert(lhs_type.is_string() and rhs_type.is_string())
          return AppNetBool()
        else:
          raise Exception("unsupported operator")
      raise Exception("unknown operator")
      
    expr_appnet_type = get_expr_type(node.op, lhs_appnet_type, rhs_appnet_type)

    new_var, decl = ctx.declareNativeVar(
      ctx.new_temporary_name(), expr_appnet_type.to_native())
    
    ctx.push_code(decl)
    assign_code = f"{new_var.name} = {lhs_nativevar.name} {node.op.accept(self, ctx)} {rhs_nativevar.name};"
    ctx.push_code(assign_code)

    return (expr_appnet_type, new_var)

  def visitOperator(self, node: Operator, ctx: NativeContext) -> str:
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
      return "<"
    elif node == Operator.GT:
      return ">"
    elif node == Operator.LE:
      return "<="
    elif node == Operator.GE:
      return ">="
    else:
      raise Exception("unknown operator")

  def visitType(self, node: Type, ctx: NativeContext) -> AppNetType:
    if node.name == "int":
      return AppNetInt()
    elif node.name == "float":
      return AppNetFloat()
    elif node.name == "string":
      return AppNetString()
    elif node.name == "bool":
      return AppNetBool()
    elif node.name == "Instant":
      return AppNetInstant()
    else:
      raise Exception("unknown type")

  def visitFuncCall(self, node: FuncCall, ctx: NativeContext) -> Tuple[AppNetType, Optional[NativeVariable]]:
    args = [self.visitGeneralExpr(arg, ctx) for arg in node.args]
    fname = node.name.name
    for func in APPNET_BUILTIN_FUNCS:
      func_instance: AppNetBuiltinFuncProto = func()
      if func_instance.appnet_name != fname:
        continue

      # Check if the arguments match
      if not func_instance.instantiate([arg[0] for arg in args]):
        continue
      
      # Generate the code
      ret_native_var = func_instance.gen_code(ctx, *[arg[1] for arg in args])
      return (func_instance.ret_type(), ret_native_var)
    
    raise Exception(f"no function prototype match with name={fname} args={args}")
    
  def visitMethodCall(self, node: MethodCall, ctx: NativeContext) -> Tuple[AppNetType, Optional[NativeVariable]]:
    raise NotImplementedError

  def visitSend(self, node: Send, ctx: NativeContext):
    # Down: cluster side
    # Up: client side
    # Request: Up --> Down
    # Response: Down --> Up

    match ctx.current_procedure:
      case "req":
        if node.direction == "Up":
          # Make sure it's something like send(err('msg'), Up)
          if isinstance(node.msg, Error):
            assert(node.msg.msg.type == DataType.STR)
            assert(node.msg.msg.value != "")
            # Forbidden 403
            ctx.push_code(f"this->decoder_callbacks_->sendLocalReply(Http::Code::Forbidden, \"{node.msg.msg.value[1:-1]}\", nullptr, absl::nullopt, \"\");")
            ctx.push_code(f"this->req_appnet_blocked_ = true;")
            ctx.push_code("co_return;")
          else:
            raise Exception("req procedure should only send error message tp Up direction")
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
          raise NotImplementedError("down direction is not supported in resp procedure yet")
        else:
          raise Exception("unknown direction")
      case _:
        raise Exception("unknown procedure")

  def visitLiteral(self, node: Literal, ctx: NativeContext) -> Tuple[AppNetType, str]:
    # Return a string that can be embedded in the C++ code directly.
    # A literal is a string, int, float, or bool
    if node.type == DataType.STR:
      # replace ' into "
      new_str = node.value.replace("'", "\"")
      return (AppNetString(), new_str)
    elif node.type == DataType.INT:
      return (AppNetInt(), str(node.value))
    elif node.type == DataType.FLOAT:
      return (AppNetFloat(), str(node.value))
    elif node.type == DataType.BOOL:
      return (AppNetBool(), str(node.value).lower())
    else:
      LOG.warning(f"unknown literal type {node.type}, value={node.value}")
      types = [(int, AppNetInt()), (float, AppNetFloat()), (str, AppNetString()), (bool, AppNetBool())]
      for t, appnet_type in types:
        # try cast 
        try:
          t(node.value)
          return (appnet_type, str(node.value))
        except:
          pass

      raise Exception("unknown literal type, and cast failed")

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
    assert(self.prepared)
    assert(len(native_args) == len(self.appargs))
    for i in range(len(native_args)):
      assert(native_args[i].type.is_same(self.appargs[i].to_native()))

  def gen_code(self, ctx: NativeContext, *args) -> NativeVariable:
    raise NotImplementedError

  def __init__(self, appnet_name: str, comments: str = ""):
    self.appnet_name = appnet_name
    self.comments = comments
    self.prepared = False
    self.appargs = []

class GetMap(AppNetBuiltinFuncProto):
  def instantiate(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 2 and isinstance(args[0], AppNetMap) and args[0].key.is_same(args[1])
    if ret:
      assert(isinstance(args[0], AppNetMap))
      assert(isinstance(args[1], AppNetType))
      self.prepared = True
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    assert(self.prepared)
    return AppNetOption(self.map.value)

  def gen_code(self, ctx: NativeContext, map: NativeVariable, key: NativeVariable) -> NativeVariable:
    self.native_arg_sanity_check([map, key])

    res_native_var, native_decl_stmt,  \
      = ctx.declareNativeVar(ctx.new_temporary_name(), self.ret_type().to_native())
    
    ctx.push_code(native_decl_stmt)
    ctx.push_code(f"{res_native_var.name} = map_get_opt({map.name}, {key.name});")
    return res_native_var
  
  def __init__(self):
    super().__init__("get", "map")
    self.map: AppNetMap = None # type: ignore
    self.key: AppNetType = None # type: ignore


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
    assert(self.prepared)
    assert(len(args) == 0)

  def gen_code(self, ctx: NativeContext, args = []) -> NativeVariable:
    self.native_arg_sanity_check(args)

    res_native_var, native_decl_stmt,  \
      = ctx.declareNativeVar(ctx.new_temporary_name(), self.ret_type().to_native())
    
    ctx.push_code(native_decl_stmt)
    ctx.push_code(f"{res_native_var.name} = std::chrono::system_clock::now();")
    return res_native_var

  def __init__(self):
    super().__init__("current_time")

class TimeDiff(AppNetBuiltinFuncProto):
  def instantiate(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 2 and isinstance(args[0], AppNetInstant) and isinstance(args[1], AppNetInstant)
    if ret:
      self.prepared = True
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    return AppNetFloat()

  def gen_code(self, ctx: NativeContext, end: NativeVariable, start: NativeVariable) -> NativeVariable:
    self.native_arg_sanity_check([end, start])

    res_native_var, native_decl_stmt,  \
      = ctx.declareNativeVar(ctx.new_temporary_name(), self.ret_type().to_native())
    
    ctx.push_code(native_decl_stmt)
    # cast into float in second
    ctx.push_code(f"{res_native_var.name} = std::chrono::duration_cast<std::chrono::duration<float>>({end.name} - {start.name}).count();")
    return res_native_var

  def __init__(self):
    super().__init__("time_diff", "in_sec")

class Min(AppNetBuiltinFuncProto):
  def instantiate(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 2 and args[0].is_same(args[1])
    if ret:
      self.prepared = True
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    assert(self.prepared)
    return self.appargs[0]

  def gen_code(self, ctx: NativeContext, a: NativeVariable, b: NativeVariable) -> NativeVariable:
    self.native_arg_sanity_check([a, b])

    res_native_var, native_decl_stmt,  \
      = ctx.declareNativeVar(ctx.new_temporary_name(), self.ret_type().to_native())
    
    ctx.push_code(native_decl_stmt)
    ctx.push_code(f"{res_native_var.name} = std::min({a.name}, {b.name});")
    return res_native_var

  def __init__(self):
    super().__init__("min")

APPNET_BUILTIN_FUNCS = [GetMap, CurrentTime, TimeDiff, Min]
