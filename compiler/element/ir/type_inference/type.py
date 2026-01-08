from __future__ import annotations

class AbstractType:
    def is_same(self, other: AbstractType) -> bool:
        return type(self) == type(other)
    
    def to_proto(self) -> str:
        raise ValueError("to_proto not implemented for abstract type")


class VecType(AbstractType):
    def __init__(self, element_type: AbstractType):
        self.element_type = element_type


class MapType(AbstractType):
    def __init__(self, key_type: AbstractType, value_type: AbstractType):
        self.key_type = key_type
        self.value_type = value_type
    
    def is_same(self, other: AbstractType) -> bool:
        if not isinstance(other, MapType):
            return False
        return self.key_type.is_same(other.key_type) and self.value_type.is_same(other.value_type)

class PairType(AbstractType):
    def __init__(self, first_type: AbstractType, second_type: AbstractType):
        self.first_type = first_type
        self.second_type = second_type
    
    def is_same(self, other: AbstractType) -> bool:
        if not isinstance(other, PairType):
            return False
        return self.first_type.is_same(other.first_type) and self.second_type.is_same(other.second_type)


class OptionalType(AbstractType):
    def __init__(self, inner_type: AbstractType):
        self.inner_type = inner_type
    
    def is_same(self, other: AbstractType) -> bool:
        if not isinstance(other, OptionalType):
            return False
        return self.inner_type.is_same(other.inner_type)


class ArithmeticType(AbstractType):
    pass


class FloatType(ArithmeticType):
    def to_proto(self) -> str:
        return "float"


class IntType(ArithmeticType):
    def to_proto(self) -> str:
        return "int32"


class UIntType(ArithmeticType):
    def to_proto(self) -> str:
        return "uint32"


class StringType(AbstractType):
    def to_proto(self) -> str:
        return "string"


class BoolType(AbstractType):
    def to_proto(self) -> str:
        return "bool"