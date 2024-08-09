# Created and used by Envoy native backend.


from typing import Optional
from compiler.element.logger import ELEMENT_LOG as LOG

from compiler.element.backend.envoy_native.types import *



# Every expression, state and temporary variables in AppNet belong to a AppNetType. 
# This is the base class for all types in AppNet.

class AppNetType:
  def to_native(self) -> NativeType: # type: ignore
    LOG.error(f"to_native not implemented for {self}")
    assert(0)

  def is_basic(self) -> bool:
    return self.is_arithmetic() or self.is_bool()
  
  def is_arithmetic(self) -> bool:
    return isinstance(self, Int) or isinstance(self, Float)
  
  def is_string(self) -> bool:
    return isinstance(self, String)

  def is_bool(self) -> bool:
    return isinstance(self, Bool)
  
  def is_same(self, other) -> bool:
    return type(self) == type(other)
  
  def is_map(self) -> bool:
    return isinstance(self, Map)
  
  def is_vec(self) -> bool:
    return isinstance(self, Vec)
  
  def is_option(self) -> bool:
    return isinstance(self, Option)

def appnet_type_from_str(name: str) -> AppNetType:
  match name:
    case "int":
      return Int()
    case "float":
      return Float()
    case "string":
      return String()
    case "bool":
      return Bool()
    case "bytes":
      return Bytes()
    case "instant":
      return Instant()
    case _:
      raise Exception(f"Unknown type {name} when converting from string")


class RPC(AppNetType):
  def to_native(self) -> NativeType:
    return NativeRPC()

class Int(AppNetType):
  def to_native(self) -> NativeType:
    return NativeInt()

class Float(AppNetType):
  def to_native(self) -> NativeType:
    return NativeFloat()

class String(AppNetType):
  def to_native(self) -> NativeType:
    return NativeString()

class Bool(AppNetType):
  def to_native(self) -> NativeType:
    return NativeBool()

class Bytes(AppNetType):
  def to_native(self) -> NativeType:
    return NativeBytes()

class Instant(AppNetType):
  def to_native(self) -> NativeType:
    return NativeTimepoint()

class Option(AppNetType): # return type of get(Map, ...)
  inner: AppNetType
  def __init__(self, inner: AppNetType):
    self.inner = inner

  def to_native(self) -> NativeType:
    return NativeOption(self.inner.to_native())

class Map(AppNetType):
  key: AppNetType
  value: AppNetType

  def __init__(self, key: AppNetType, value: AppNetType):
    self.key = key
    self.value = value

  def to_native(self) -> NativeType:
    return NativeMap(self.key.to_native(), self.value.to_native())

class Vec(AppNetType):
  type: AppNetType

  def __init__(self, type: AppNetType):
    self.type = type

  def to_native(self) -> NativeType:
    return NativeVec(self.type.to_native())

class Void(AppNetType):
  def to_native(self) -> NativeType: # type: ignore
    LOG.error(f"AppNet Void type cannot be converted to native type")
    assert(0)

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