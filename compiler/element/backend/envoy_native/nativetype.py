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


class Int(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"int {name};"

class Float(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"float {name};"
  
class String(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"std::string {name};"
  
class Bool(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"bool {name};"
  
class Bytes(NativeType):
  def gen_decl(self, name: str) -> str:
    return f"std::vector<uint8_t> {name};"

class Option(NativeType):
  inner: NativeType
  def __init__(self, inner: NativeType):
    self.inner = inner

  def gen_decl(self, name: str) -> str:
    return f"std::optional<{self.inner.gen_decl(name)}>"

class Map(NativeType):
  key: NativeType
  value: NativeType

  def __init__(self, key: NativeType, value: NativeType):
    self.key = key
    self.value = value

  def gen_decl(self, name: str) -> str:
    return f"std::map<{self.key.gen_decl(name)}, {self.value.gen_decl(name)}> {name};"
  
class Vec(NativeType):
  type: NativeType

  def __init__(self, type: NativeType):
    self.type = type

  def gen_decl(self, name: str) -> str:
    return f"std::vector<{self.type.gen_decl(name)}> {name};"

class NativeVariable:
  name: str
  type: NativeType

  def __init__(self, name: str, type: NativeType):
    self.name = name
    self.type = type