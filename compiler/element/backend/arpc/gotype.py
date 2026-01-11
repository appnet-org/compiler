from __future__ import annotations

from typing import Tuple

from compiler.element.ir.type_inference.type import *

class GoTypeNameGenerator(TypeVisitor):
    def visitFloatType(self, t: FloatType) -> str:
        return "float64"

    def visitIntType(self, t: IntType) -> str:
        return "int32"

    def visitUIntType(self, t: UIntType) -> str:
        return "uint32"

    def visitStringType(self, t: StringType) -> str:
        return "string"
    
    def visitBoolType(self, t: BoolType) -> str:
        return "bool"
    
    def visitVecType(self, t: VecType) -> str:
        return f"[]{t.element_type.accept(self)}"
    
    def visitMapType(self, t: MapType) -> str:
        key_type_str = t.key_type.accept(self)
        value_type_str = t.value_type.accept(self)
        return f"map[{key_type_str}]{value_type_str}"
    
    def visitOptionalType(self, t: OptionalType) -> Tuple[str, str]:
        inner_type_str = t.inner_type.accept(self)
        return inner_type_str, "bool"

# class GoTypeDeclarator(TypeVisitor):
#     def __init__(self):
#         self.type_name_generator = GoTypeNameGenerator()
    
#     @staticmethod
#     def process_in_struct(var_name: str, type_dec_str: str, in_struct: bool) -> str:
#         if in_struct:
#             # in struct global variables need to be protected by lock
#             return f"{var_name}: {type_dec_str},\n{var_name}_mu: &sync.RWMutex{{}},"
#         else:
#             return f"var {var_name} {type_dec_str}" 
    
#     def visitBasicType(self, t: BasicType, var_name: str, in_struct: bool = False) -> str:
#         type_str = t.accept(self.type_name_generator)
#         return GoTypeDeclarator.process_in_struct(var_name, type_str, in_struct)

#     def visitMapType(self, t: MapType, var_name: str, in_struct: bool = False) -> str:
#         map_name = t.accept(self.type_name_generator)
#         dec_str = f"make({map_name})"
#         return GoTypeDeclarator.process_in_struct(var_name, dec_str, in_struct)
    
#     def visitOptionalType(self, t: OptionalType, var_name: str, in_struct: bool = False) -> str:
#         inner_type_str = t.inner_type.accept(self, var_name, in_struct)
#         ok_str = BoolType().accept(self, f"{var_name}_ok", in_struct)
#         return inner_type_str + "\n" + ok_str


class GoTypeInitGenerator(TypeVisitor):
    def __init__(self):
        self.type_name_generator = GoTypeNameGenerator()
    
    def visitFloatType(self, t: FloatType) -> str:
        return "0.0"
    
    def visitIntType(self, t: IntType) -> str:
        return "0"
    
    def visitUIntType(self, t: UIntType) -> str:
        return "0"
    
    def visitStringType(self, t: StringType) -> str:
        return '""'

    def visitBoolType(self, t: BoolType) -> str:
        return "false"
    
    def visitVecType(self, t: VecType) -> str:
        return "make([])"
    
    def visitMapType(self, t: MapType) -> str:
        map_type_str = t.accept(self.type_name_generator)
        return f"make({map_type_str})"

    def visitOptionalType(self, t: OptionalType) -> Tuple[str, str]:
        inner_type_init = t.inner_type.accept(self)
        return inner_type_init, "false"
