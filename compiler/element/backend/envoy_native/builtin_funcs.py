

from typing import List, Tuple, Callable
from compiler.element.backend.envoy_native.appnettype import AppNetType
from compiler.element.backend.envoy_native.types import *
from compiler.element.backend.envoy_native.nativegen import NativeContext, NativeVariable


class AppNetBuiltinFuncProto:
  def arg_filter(self, args: List[AppNetType]) -> bool:
    raise NotImplementedError

  def ret_type(self) -> AppNetType:
    raise NotImplementedError

  def native_arg_sanity_check(self, native_args: List[NativeVariable]):
    # Check the given native arguments is consistent with the app args given by arg_filter
    assert(self.prepared)
    assert(len(native_args) == len(self.appargs))
    for i in range(len(native_args)):
      assert(native_args[i].type.is_same(self.appargs[i].to_native()))

  def gen_code(self, ctx: NativeContext, args: List[NativeVariable]) -> NativeVariable:
    raise NotImplementedError

  def __init__(self, appnet_name: str, native_suffix: str = ""):
    self.appnet_name = appnet_name
    self.native_suffix = native_suffix
    self.prepared = False
    self.appargs = []

class GetMap(AppNetBuiltinFuncProto):
  def arg_filter(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 2 and isinstance(args[0], AppNetMap) and args[0].key.is_same(args[1])
    if ret:
      assert(isinstance(args[0], AppNetMap))
      assert(isinstance(args[1], AppNetType))
      self.prepared = True
      self.map = args[0]
      self.key = args[1]
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    assert(self.prepared)
    return AppNetOption(self.map.value)

  def native_arg_sanity_check(self, args: List[NativeVariable]):
    assert(self.prepared)
    assert(len(args) == 2)

  def gen_code(self, ctx: NativeContext, args: List[NativeVariable]) -> NativeVariable:
    self.native_arg_sanity_check(args)

    res_native_var, native_decl_stmt,  \
      = ctx.declareNativeVar(ctx.new_temporary_name(), self.ret_type().to_native())
    
    ctx.push_code(native_decl_stmt)
    ctx.push_code(f"{res_native_var.name} = map_get_opt({args[0].name}, {args[1].name});")
    return res_native_var
  
  def __init__(self):
    super().__init__("get", "map")
    self.map: AppNetMap = None # type: ignore
    self.key: AppNetType = None # type: ignore


class CurrentTime(AppNetBuiltinFuncProto):
  def arg_filter(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 0
    if ret:
      self.prepared = True
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    return AppNetInstant()

  def __init__(self):
    super().__init__("current_time")

class TimeDiff(AppNetBuiltinFuncProto):
  def arg_filter(self, args: List[AppNetType]) -> bool:
    ret = len(args) == 2 and isinstance(args[0], AppNetInstant) and isinstance(args[1], AppNetInstant)
    if ret:
      self.prepared = True
      self.appargs = args
    return ret

  def ret_type(self) -> AppNetType:
    return AppNetFloat()

  def __init__(self):
    super().__init__("time_diff", "in_sec")

APPNET_BUILTIN_FUNCS = [GetMap, CurrentTime, TimeDiff]
