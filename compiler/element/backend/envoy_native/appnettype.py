# Created and used by Envoy natvie backend.


from typing import Optional
from compiler.element.backend.envoy_native.nativetype import NativeVariable


# Every expression and state in AppNet has a type. This is the base class for all types in AppNet.
class AppNetType:
  pass

class Int(AppNetType):
  pass

class Float(AppNetType):
  pass

class String(AppNetType):
  pass

class Bool(AppNetType):
  pass

class Bytes(AppNetType):
  pass

class Option(AppNetType): # return type of get(Map, ...)
  inner: AppNetType
  def __init__(self, is_some: bool, inner: AppNetType):
    self.is_some = is_some
    self.inner

class Map(AppNetType):
  key: AppNetType
  value: AppNetType

  def __init__(self, key: AppNetType, value: AppNetType):
    self.key = key
    self.value = value

class Vec(AppNetType):
  type: AppNetType

  def __init__(self, type: AppNetType):
    self.type = type

class Void(AppNetType):
  pass

class AppNetVariable:
  name: str
  type: AppNetType

  # We have two types of variables in AppNet:
  # 1. Temporary variables: These are variables that are implicitly declared in procedures.
  # 2. State variables: These are variables that are declared in the state block of the program.
  # If global_decorator is None, it means it's a temporary local variable.
  global_decorator: Optional[dict[str, str]]

  native_var: Optional[NativeVariable]

  def __init__(self, name: str, type: AppNetType, global_decorator: Optional[dict[str, str]] = None):
    self.name = name
    self.type = type
    self.global_decorator = global_decorator