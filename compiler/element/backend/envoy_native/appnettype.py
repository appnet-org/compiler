# Created and used by Envoy natvie backend.

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

