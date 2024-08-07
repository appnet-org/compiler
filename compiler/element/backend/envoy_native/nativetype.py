from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional

from compiler.element.backend.envoy_native import *
from compiler.element.logger import ELEMENT_LOG as LOG

class NativeType:
  def gen_decl(self, name: str) -> str:
    LOG.error(f"gen_decl not implemented for {self}")
    assert(0)
    return ""
  
  def is_arithmetic(self) -> bool:
    return isinstance(self, Int) or isinstance(self, Float)

  def is_string(self) -> bool:
    return isinstance(self, String)
  
  def is_bool(self) -> bool:
    return isinstance(self, Bool)
  
  def is_basic(self) -> bool:
    return self.is_arithmetic() or self.is_bool()
  
  def is_timepoint(self) -> bool:
    return isinstance(self, Timepoint)

  def is_same(self, other: NativeType) -> bool:
    # not apply for complex types
    assert(self.is_basic() or self.is_string() or self.is_timepoint())
    return type(self) == type(other)

class Timepoint(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"std::chrono::time_point<std::chrono::system_clock> {name};"

class Int(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"int {name} = 0;"

class Float(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"float {name} = 0;"
  
class String(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"std::string {name} = \"\";"
  
class Bool(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"bool {name} = false;"
  
class Bytes(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"std::vector<uint8_t> {name}{{0}};"

class Option(NativeType):
  inner: NativeType
  def __init__(self, inner: NativeType):
    self.inner = inner

  def gen_decl(self, name: str) -> str:
    return f"std::optional<{self.inner.gen_decl(name)}> = std::nullopt;"

  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Option):
      return False
    return self.inner.is_same(other.inner)

class Map(NativeType):
  key: NativeType
  value: NativeType

  def __init__(self, key: NativeType, value: NativeType):
    self.key = key
    self.value = value

  def gen_decl(self, name: str) -> str:
    return f"std::map<{self.key.gen_decl(name)}, {self.value.gen_decl(name)}> {name} = {{}};"
  
  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Map):
      return False
    return self.key.is_same(other.key) and self.value.is_same(other.value)

class Vec(NativeType):
  type: NativeType

  def __init__(self, type: NativeType):
    self.type = type

  def gen_decl(self, name: str) -> str:
    return f"std::vector<{self.type.gen_decl(name)}> {name} = {{}};"

  def is_same(self, other: NativeType) -> bool:
    if not isinstance(other, Vec):
      return False
    return self.type.is_same(other.type)

class NativeVariable:
  name: str
  type: NativeType

  def __init__(self, name: str, type: NativeType):
    self.name = name
    self.type = type