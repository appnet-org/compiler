from __future__ import annotations
from abc import ABC
from typing import Any

class TypeVisitor(ABC):
    def visitVecType(self, t: VecType) -> Any:
        pass

    def visitMapType(self, t: MapType) -> Any:
        pass

    def visitPairType(self, t: PairType) -> Any:
        pass

    def visitOptionalType(self, t: OptionalType) -> Any:
        pass


class AbstractType:
    def is_same(self, other: AbstractType) -> bool:
        return type(self) == type(other)
    
    def to_proto(self) -> str:
        raise ValueError("to_proto not implemented for abstract type")
    
    def accept(self, visitor: TypeVisitor, *args, **kwargs) -> Any:
        class_list = type(self).__mro__
        for cls in class_list:
            func_name = "visit" + cls.__name__
            visit_func = getattr(visitor, func_name, None)
            if visit_func is not None:
                return visit_func(self, *args, **kwargs)
        raise Exception(f"visit function for {self.__class__.__name__} not implemented")


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


class BasicType(AbstractType):
    pass


class ArithmeticType(BasicType):
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


class StringType(BasicType):
    def to_proto(self) -> str:
        return "string"


class BoolType(BasicType):
    def to_proto(self) -> str:
        return "bool"