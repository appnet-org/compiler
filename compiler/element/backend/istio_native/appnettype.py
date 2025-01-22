# Created and used by Envoy native backend.


from typing import Optional

from compiler.element.backend.istio_native.nativetype import RPC as NativeRPC
from compiler.element.backend.istio_native.nativetype import Bool as NativeBool
from compiler.element.backend.istio_native.nativetype import Bytes as NativeBytes
from compiler.element.backend.istio_native.nativetype import Float as NativeFloat
from compiler.element.backend.istio_native.nativetype import Int as NativeInt
from compiler.element.backend.istio_native.nativetype import Map as NativeMap
from compiler.element.backend.istio_native.nativetype import NativeType, NativeVariable
from compiler.element.backend.istio_native.nativetype import Option as NativeOption
from compiler.element.backend.istio_native.nativetype import Pair as NativePair
from compiler.element.backend.istio_native.nativetype import String as NativeString
from compiler.element.backend.istio_native.nativetype import (
    Timepoint as NativeTimepoint,
)
from compiler.element.backend.istio_native.nativetype import UInt as NativeUInt
from compiler.element.backend.istio_native.nativetype import Vec as NativeVec
from compiler.element.logger import ELEMENT_LOG as LOG

DEFAULT_DECORATOR = {
    "consistency": "None",
    "combiner": "None",
    "persistence": "None",
}

# Every expression, state and temporary variables in AppNet belong to a AppNetType.
# This is the base class for all types in AppNet.


class AppNetType:
    def __init__(self, decorator: dict[str, str] = DEFAULT_DECORATOR):
        self.decorator = decorator

    def to_native(self) -> NativeType:  # type: ignore
        LOG.error(f"to_native not implemented for {self}")
        assert 0

    def is_basic(self) -> bool:
        return self.is_arithmetic() or self.is_bool()

    def is_arithmetic(self) -> bool:
        return (
            isinstance(self, Int) or isinstance(self, UInt) or isinstance(self, Float)
        )

    def is_float(self) -> bool:
        return isinstance(self, Float)

    def is_string(self) -> bool:
        return isinstance(self, String)

    def is_string_literal(self) -> bool:
        return isinstance(self, String) and self.literal is not None

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

    def is_int(self) -> bool:
        return isinstance(self, Int)

    def is_uint(self) -> bool:
        return isinstance(self, UInt)

    def is_pair(self) -> bool:
        return isinstance(self, Pair)

    def is_vec(self) -> bool:
        return isinstance(self, Vec)


def appnet_type_from_str(name: str) -> AppNetType:
    match name.lower():
        case "int":
            return Int()
        case "uint":
            return UInt()
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
            if name.startswith("<") and name.endswith(">"):
                # maybe a pair type: <typea, typeb>
                inner = name[1:-1].split(",")
                if len(inner) == 2:
                    return Pair(
                        appnet_type_from_str(inner[0].strip()),
                        appnet_type_from_str(inner[1].strip()),
                    )
                else:
                    raise Exception(f"Unknown type {name} when converting from string")

            raise Exception(f"Unknown type {name} when converting from string")


class RPC(AppNetType):
    def to_native(self) -> NativeType:
        return NativeRPC()


class Int(AppNetType):
    def to_native(self) -> NativeType:
        return NativeInt()


class UInt(AppNetType):
    def to_native(self) -> NativeType:
        return NativeUInt()


class Float(AppNetType):
    def to_native(self) -> NativeType:
        return NativeFloat()


class String(AppNetType):
    literal: Optional[
        str
    ]  # Sometimes we have get(rpc, 'load') where 'load' is a string literal.

    def to_native(self) -> NativeType:
        return NativeString()

    def __init__(self, literal: Optional[str] = None):
        super().__init__()
        self.literal = literal


class Bool(AppNetType):
    def to_native(self) -> NativeType:
        return NativeBool()


class Bytes(AppNetType):
    def to_native(self) -> NativeType:
        return NativeBytes()


class Instant(AppNetType):
    def to_native(self) -> NativeType:
        return NativeTimepoint()


class Option(AppNetType):  # return type of get(Map, ...)
    inner: AppNetType

    def __init__(self, inner: AppNetType):
        super().__init__()
        self.inner = inner

    def to_native(self) -> NativeType:
        return NativeOption(self.inner.to_native())


class Map(AppNetType):
    key: AppNetType
    value: AppNetType

    def __init__(
        self,
        key: AppNetType,
        value: AppNetType,
        decorator: dict[str, str] = DEFAULT_DECORATOR,
    ):
        super().__init__(decorator)
        self.key = key
        self.value = value

    def to_native(self) -> NativeType:
        return NativeMap(self.key.to_native(), self.value.to_native())


class Vec(AppNetType):
    type: AppNetType

    def __init__(self, type: AppNetType):
        super().__init__()
        self.type = type

    def to_native(self) -> NativeType:
        return NativeVec(self.type.to_native())


class Void(AppNetType):
    def to_native(self) -> NativeType:  # type: ignore
        LOG.error(f"AppNet Void type cannot be converted to native type")
        assert 0


class Pair(AppNetType):
    first: AppNetType
    second: AppNetType

    def __init__(self, first: AppNetType, second: AppNetType):
        super().__init__()
        self.first = first
        self.second = second

    def to_native(self) -> NativeType:
        return NativePair(self.first.to_native(), self.second.to_native())


class AppNetVariable:
    name: str
    type: AppNetType

    native_var: Optional[NativeVariable]

    def __init__(self, name: str, type: AppNetType):
        self.name = name
        self.type = type


def proto_type_to_appnet_type(proto_type: str) -> AppNetType:
    match proto_type:
        case "int32", "int64", "uint32", "uint64", "sint32", "sint64", "fixed32", "fixed64", "sfixed32", "sfixed64":
            return Int()
        case "float", "double":
            return Float()
        case "string":
            return String()
        case "bool":
            return Bool()
        case "bytes":
            return Bytes()
        case "google.protobuf.Timestamp":
            return Instant()
        case _:
            raise Exception(f"Unknown proto type {proto_type}")
