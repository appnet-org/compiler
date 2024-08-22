from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional

from compiler.element.backend.envoy_native import *
from compiler.element.logger import ELEMENT_LOG as LOG

class NativeType:
  def gen_decl(self, name: str) -> str:
    raise NotImplementedError(f"gen_decl not implemented for {self}")
  
  def is_arithmetic(self) -> bool:
    return isinstance(self, Int) or isinstance(self, Float)

  def is_string(self) -> bool:
    return isinstance(self, String)
  
  def is_bool(self) -> bool:
    return isinstance(self, Bool)
  
  def is_basic(self) -> bool:
    return self.is_arithmetic() or self.is_bool()
  
  def is_rpc(self) -> bool:
    return isinstance(self, RPC)
  
  def is_timepoint(self) -> bool:
    return isinstance(self, Timepoint)

  def type_name(self) -> str:
    raise Exception(f"type_name not implemented for {self}")

  def is_same(self, other: NativeType) -> bool:
    # not apply for complex types
    assert(self.is_basic() or self.is_string() or self.is_timepoint() or self.is_rpc())
    return type(self) == type(other)

class RPC(NativeType):
  def type_name(self) -> str:
    return "::appnetsamplefilter::Msg"
  
  def gen_decl(self, name: str) -> str:
    return f"::appnetsamplefilter::Msg {name};"

class Timepoint(NativeType):
  def type_name (self)-> str:
    return "std::chrono::time_point<std::chrono::system_clock>"

  def gen_decl(self, name: str) -> str:
    return f"std::chrono::time_point<std::chrono::system_clock> {name};"

class Int(NativeType):
  def type_name(self) -> str:
    return "int"
  
  def gen_decl(self, name: str) -> str:
    return f"int {name} = 0;"

class Float(NativeType):
  def type_name(self) -> str:
    return "float"
  
  def gen_decl(self, name: str) -> str:
    return f"float {name} = 0;"
  
class String(NativeType):
  def type_name(self) -> str:
    return "std::string"
  
  def gen_decl(self, name: str) -> str:
    return f"std::string {name} = \"\";"
  
class Bool(NativeType):
  def type_name(self) -> str:
    return "bool"
  
  def gen_decl(self, name: str) -> str:
    return f"bool {name} = false;"
  
class Bytes(NativeType):
  def type_name(self) -> str:
    return "std::vector<uint8_t>"
  
  def gen_decl(self, name: str) -> str:
    return f"std::vector<uint8_t> {name}{{0}};"

class Option(NativeType):
  inner: NativeType
  def __init__(self, inner: NativeType):
    self.inner = inner

  def gen_decl(self, name: str) -> str:
    return f"std::optional<{self.inner.type_name()}> {name} = std::nullopt;"

  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Option):
      return False
    return self.inner.is_same(other.inner)
  
  def type_name(self) -> str:
    return f"std::optional<{self.inner.type_name()}>"

class Map(NativeType):
  key: NativeType
  value: NativeType

  def __init__(self, key: NativeType, value: NativeType):
    self.key = key
    self.value = value

  def gen_decl(self, name: str) -> str:
    return f"std::map<{self.key.type_name()}, {self.value.type_name()}> {name} = {{}};"
  
  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Map):
      return False
    return self.key.is_same(other.key) and self.value.is_same(other.value)

  def type_name(self) -> str:
    return f"std::map<{self.key.type_name()}, {self.value.type_name()}>"

class Vec(NativeType):
  type: NativeType

  def __init__(self, type: NativeType):
    self.type = type

  def gen_decl(self, name: str) -> str:
    return f"std::vector<{self.type.type_name()}> {name} = {{}};"

  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Vec):
      return False
    return self.type.is_same(other.type)

  def type_name(self) -> str:
    return f"std::vector<{self.type.type_name()}>"

class Pair(NativeType):
  first: NativeType
  second: NativeType

  def __init__(self, first: NativeType, second: NativeType):
    self.first = first
    self.second = second

  def gen_decl(self, name: str) -> str:
    return f"std::pair<{self.first.type_name()}, {self.second.type_name()}> {name};"

  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Pair):
      return False
    return self.first.is_same(other.first) and self.second.is_same(other.second)

  def type_name(self) -> str:
    return f"std::pair<{self.first.type_name()}, {self.second.type_name()}>"

class NativeVariable:
  name: str
  type: NativeType
  local: bool # is this variable local to a request or not

  def __init__(self, name: str, type: NativeType, local: bool):
    self.name = name
    self.type = type
    self.local = local