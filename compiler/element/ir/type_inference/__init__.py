from __future__ import annotations
from typing import List, Dict, Optional

from compiler.element.visitor import Visitor
from compiler.element.node import *
from compiler.element.ir.type_inference.type import *
from compiler.proto import Proto


class TypeInferenceError(Exception):
    pass


class TypeContext:
    """
    Type context for type inference.

    Attributes:
        name2type (List[Dict[str, AbstractType]]): A list of dictionaries mapping variable names to their types.
        match_type (AbstractType): The type of the current match block.
        current_procedure (str): The name of the current procedure.
        proto (Proto): The proto object.
        method (str): The method name.
    """
    def __init__(self, proto: Proto, method: str):
        self.name2type: List[Dict[str, AbstractType]] = [{}]
        self.match_type: AbstractType = AbstractType()
        self.current_procedure: str = ""
        self.proto = proto
        self.method = method
    
    def query_proto(self, field_name: str) -> Optional[AbstractType]:
        type_str = self.proto.query_type(self.method, self.current_procedure, field_name)
        if type_str == "":
            return None
        match type_str:
            case "int32":
                return IntType()
            case "uint32":
                return UIntType()
            case "string":
                return StringType()
            case "float":
                return FloatType()
            case _:
                raise TypeInferenceError(f"unsupported proto type: {type_str}")
    
    def proto_add_field(self, field_name: str, field_type: str):
        self.proto.add_field(self.method, self.current_procedure, field_name, field_type)

    def query_type(self, name: str) -> Optional[AbstractType]:
        """
        Args:
            name (str): The name of the variable to query the type of.
        Returns:
            Optional[AbstractType]: The type of the given name, or None if the name is not found.
        """
        for var_scope in self.name2type:
            if name in var_scope:
                return var_scope[name]
        return None
    
    def declare(self, var: Identifier):
        """
        Declare a variable in the type context.
        Args:
            var (Identifier): The variable to declare.
        Raises:
            TypeInferenceError: If the variable name is 'rpc'.
        """
        if var.name in ["rpc", "packet_raw"]:
            raise TypeInferenceError(f"variable name '{var.name}' is reserved.")
        var.declare = True
        scope = self.name2type[0]
        if var.name in scope:
            raise TypeInferenceError(f"variable {var.name} is redeclared.")
        scope[var.name] = var.get_type()
    
    def push_scope(self):
        self.name2type = [{}] + self.name2type
    
    def pop_scope(self):
        assert len(self.name2type) > 1, "no scope to pop"
        self.name2type = self.name2type[1:]


class TypeAnalyzer(Visitor):
    def visitProgram(self, node: Program, ctx: TypeContext):
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)
    
    @staticmethod
    def parse_type(type_def: str) -> AbstractType:   
        """
        Parse the type definition string into an AbstractType object.
        Args:
            type_def (str): The type definition string to parse.
        Returns:
            AbstractType: The parsed AbstractType object.
        Raises:
            TypeInferenceError
        """
        def build_basic_type(type_def: str) -> AbstractType:
            match type_def:
                case "float":
                    return FloatType()
                case "int":
                    return IntType()
                case "uint":
                    return UIntType()
                case "string":
                    return StringType()
                case "Instant":
                    return FloatType()
                case _:
                    raise TypeInferenceError(f"unknown basic type: {type_def}")

        def find_comma_idx(content: str) -> int:
            """
            Find the index of the seperating comma in the content.
            Used for parsing Map types, Pair types, etc.
            Args:
                content (str): The content to find the comma index of.
            Returns:
                int: The index of the seperating comma, or -1 if no comma is found.
            """
            bracket_count = 0
            for i, ch in enumerate(content):
                if ch in "(<{":
                    bracket_count += 1
                elif ch in ")>}":
                    bracket_count -= 1
                if bracket_count == 0 and ch == ",":
                    return i
            return -1

        if type_def.startswith("Vec<"):
            element_type_str = type_def[4:-1].strip()
            element_type = TypeAnalyzer.parse_type(element_type_str)
            return VecType(element_type)

        if type_def.startswith("Map<"):
            content = type_def[4:-1].strip()
            comma_idx = find_comma_idx(content)
            if comma_idx == -1:
                raise TypeInferenceError(f"invalid Map type: {type_def}")
            key_type = TypeAnalyzer.parse_type(content[:comma_idx].strip())
            value_type = TypeAnalyzer.parse_type(content[comma_idx+1:].strip())
            return MapType(key_type, value_type)

        if type_def.startswith("Pair<"):
            content = type_def[5:-1].strip()
            comma_idx = find_comma_idx(content)
            if comma_idx == -1:
                raise TypeInferenceError(f"invalid Pair type: {type_def}")
            first_type = TypeAnalyzer.parse_type(content[:comma_idx].strip())
            second_type = TypeAnalyzer.parse_type(content[comma_idx+1:].strip())
            return PairType(first_type, second_type)
        
        return build_basic_type(type_def)

    def visitState(self, node: State, ctx: TypeContext):
        """
        Visit the State node and declare the state variables in the type context.
        Args:
            node (State): The State node to visit.
            ctx (TypeContext): The type context to use.
        Raises:
            TypeInferenceError: If type definitions are invalid or states are redefined.
        """
        for (var, type, _, _, _) in node.state:
            try:
                var.set_type(self.parse_type(type.name))
            except TypeInferenceError as e:
                raise TypeInferenceError(f"Invalid type definition for state variable {var.name}: {e}") 
            ctx.declare(var)
    
    def visitProcedure(self, node: Procedure, ctx: TypeContext):
        ctx.push_scope()
        # TODO: now we only support "rpc" as a parameter, so the parameter list is not parsed here.
        ctx.current_procedure = node.name
        for stmt in node.body:
            stmt.accept(self, ctx)
        ctx.pop_scope()
    
    def visitStatement(self, node: Statement, ctx: TypeContext):
        if node.stmt is None:
            return
        node.stmt.accept(self, ctx)
    
    def visitAssign(self, node: Assign, ctx: TypeContext):
        node.right.accept(self, ctx)
        rtype = node.right.get_type()
        lvars: List[Identifier] = []
        if isinstance(node.left, Pair):
            if not isinstance(rtype, PairType):
                raise TypeInferenceError(f"expected Pair type, got {rtype}")
            node.left.first.set_type(rtype.first_type)
            node.left.second.set_type(rtype.second_type)
            lvars = [node.left.first, node.left.second]
        else:
            if isinstance(rtype, Pair):
                raise TypeInferenceError(f"expected non-Pair type, got {rtype}")
            node.left.set_type(rtype)
            lvars = [node.left]
        # check for declaration
        for var in lvars:
            t = ctx.query_type(var.name)
            if t is not None:
                # this is not a new declaration
                if not t.is_same(var.get_type()):
                    raise TypeInferenceError(f"variable {var.name} is declared with type {t}, but assigned with type {var.get_type()}")
            else:
                ctx.declare(var)
    
    def visitExpr(self, node: Expr, ctx: TypeContext):
        node.lhs.accept(self, ctx)
        node.rhs.accept(self, ctx)
        ltype, rtype = node.lhs.get_type(), node.rhs.get_type()
        if node.op in [Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV]:
            if not ltype.is_same(rtype):
                raise TypeInferenceError(f"expected same type for operands {node.op}, got {ltype} and {rtype}")
            if not isinstance(ltype, ArithmeticType):
                raise TypeInferenceError(f"expected arithmetic type for operands {node.op}, got {ltype}")
            node.set_type(ltype)
        elif node.op in [Operator.AND, Operator.OR]:
            if not isinstance(ltype, BoolType) or not isinstance(rtype, BoolType):
                raise TypeInferenceError(f"expected boolean type for operands {node.op}, got {ltype} and {rtype}")
            node.set_type(BoolType())
        elif node.op in [Operator.EQ, Operator.NEQ]:
            if not ltype.is_same(rtype):
                raise TypeInferenceError(f"expected same type for operands {node.op}, got {ltype} and {rtype}")
            node.set_type(BoolType())
        elif node.op in [Operator.LT, Operator.GT, Operator.LE, Operator.GE]:
            if not ltype.is_same(rtype):
                raise TypeInferenceError(f"expected same type for operands {node.op}, got {ltype} and {rtype}")
            if not isinstance(ltype, ArithmeticType):
                raise TypeInferenceError(f"expected arithmetic type for operands {node.op}, got {ltype}")
            node.set_type(BoolType())
        else:
            raise TypeInferenceError(f"unknown operator: {node.op}")
    
    def visitIdentifier(self, node: Identifier, ctx: TypeContext):
        if node.name == "rpc":
            # rpc doesn't need to be type checked
            return
        t = ctx.query_type(node.name)
        if t is None:
            raise TypeInferenceError(f"variable {node.name} used before declaration")
        node.set_type(t)
    
    def visitLiteral(self, node: Literal, ctx: TypeContext):
        if node.value.startswith("'") and node.value.endswith("'"):
            node.set_type(StringType())
        elif node.value in ["true", "false"]:
            node.set_type(BoolType())
        elif all(ch.isdigit() for ch in node.value):
            node.set_type(IntType())
        else:
            node.set_type(FloatType())
    
    def visitMatch(self, node: Match, ctx: TypeContext):
        node.expr.accept(self, ctx)
        expr_type = node.expr.get_type()
        for pattern, statements in node.actions:
            ctx.push_scope()
            # ctx.match_type might be changed in inner statements, so we need to reassign it for each pattern.
            ctx.match_type = expr_type
            pattern.accept(self, ctx)
            t = pattern.get_type()
            if not t.is_same(expr_type):
                raise TypeInferenceError(f"match: expected same type for pattern and expression, got {t} and {expr_type}")
            if isinstance(pattern.value, Identifier):
                ctx.declare(pattern.value)
            for statement in statements:
                statement.accept(self, ctx)
            ctx.pop_scope()
    
    def visitPattern(self, node: Pattern, ctx: TypeContext):
        if isinstance(node.value, Identifier):
            if node.some is True:
                if not isinstance(ctx.match_type, OptionalType):
                    raise TypeInferenceError(f"expected Optional type for pattern, got {ctx.match_type}")
                node.value.set_type(ctx.match_type.inner_type)
            else:
                node.value.set_type(ctx.match_type)
            node.set_type(ctx.match_type)
        elif isinstance(node.value, Literal):
            if node.value.value == "None":
                # TODO: "None" cannot be used as a string in Pattern for now.
                node.set_type(ctx.match_type)
            else:
                node.value.accept(self, ctx)
                node.set_type(node.value.get_type()) 
    
    def visitRpcGet(self, node: MethodCall, ctx: TypeContext):
        assert node.obj.name == "rpc", "rpc.get can only be called on rpc"
        node.args[0].accept(self, ctx)
        if not (isinstance(node.args[0], Literal) and isinstance(node.args[0].get_type(), StringType)):
            raise TypeInferenceError("rpc key can only be a string literal")
        field_name = node.args[0].value
        t = ctx.query_proto(field_name)
        if t is None:
            if not(len(node.args) == 2 and isinstance(node.args[1], Literal)):
                raise TypeInferenceError(f"type annotation is required for field {field_name} in rpc.get")
            node.args[1].accept(self, ctx)
            if not isinstance(node.args[1].get_type(), StringType):
                raise TypeInferenceError(f"type annotation for field {field_name} in rpc.get must be a string")
            field_type = node.args[1].value
            ctx.proto_add_field(field_name, field_type)
            t = ctx.query_proto(field_name)
        node.set_type(t)
    
    def visitRpcSet(self, node: MethodCall, ctx: TypeContext):
        assert node.obj.name == "rpc", "rpc.set can only be called on rpc"
        node.args[0].accept(self, ctx)
        node.args[1].accept(self, ctx)

        if not (isinstance(node.args[0], Literal) and isinstance(node.args[0].get_type(), StringType)):
            raise TypeInferenceError("rpc key can only be a string literal")
        field_name = node.args[0].value
        field_type= ctx.query_proto(field_name)
        vtype = node.args[1].get_type()

        if field_type is not None:
            if not field_type.is_same(vtype):
                raise TypeInferenceError(f"expected map value of type {field_type}, got {vtype}")
        else:
            ctx.proto_add_field(field_name, vtype.to_proto())
    
    def visitSend(self, node: Send, ctx: TypeContext):
        pass
    
    def visitMethodCall(self, node: MethodCall, ctx: TypeContext):
        if node.obj.name == "rpc":
            if node.method == MethodType.GET:
                self.visitRpcGet(node, ctx)
            elif node.method == MethodType.SET:
                self.visitRpcSet(node, ctx)
            elif node.method == MethodType.BYTE_SIZE:
                # TODO: byte_size should be an built-in function
                node.set_type(FloatType())
            else:
                raise TypeInferenceError(f"method {node.method} is not supported for rpc")
            return

        node.obj.accept(self, ctx)
        for arg in node.args:
            arg.accept(self, ctx)
        obj_type = node.obj.get_type()
        match node.method:
            case MethodType.GET:
                if not isinstance(obj_type, MapType):
                    raise TypeInferenceError(f"expected Map type for method GET, got {obj_type}")
                map_key_type = node.args[0].get_type()
                if not map_key_type.is_same(obj_type.key_type):
                    raise TypeInferenceError(f"expected Map key type {obj_type.key_type}, got {map_key_type}")
                node.set_type(OptionalType(obj_type.value_type))
            case MethodType.SET:
                if not isinstance(obj_type, MapType):
                    raise TypeInferenceError(f"expected Map type for method SET, got {obj_type}")
                map_key_type = node.args[0].get_type()
                if not map_key_type.is_same(obj_type.key_type):
                    raise TypeInferenceError(f"expected Map key type {obj_type.key_type}, got {map_key_type}")
                map_value_type = node.args[1].get_type()
                if not map_value_type.is_same(obj_type.value_type):
                    raise TypeInferenceError(f"expected Map value type {obj_type.value_type}, got {map_value_type}")
            case _:
                raise NotImplementedError(f"type inference for method {node.method} is not supported")

    def visitRandomFunc(self, node: RandomFunc, ctx: TypeContext):
        node.lower.accept(self, ctx)
        node.upper.accept(self, ctx)
        ltype, utype = node.lower.get_type(), node.upper.get_type()
        if not (isinstance(ltype, ArithmeticType) and isinstance(utype, ArithmeticType)):
            raise TypeInferenceError(f"expected float type for lower and upper bounds in randomf, got {ltype} and {utype}")
        node.set_type(FloatType())
    
    def visitCurrentTimeFunc(self, node: CurrentTimeFunc, ctx: TypeContext):
        node.set_type(FloatType())
    
    def visitTimeDiffFunc(self, node: TimeDiffFunc, ctx: TypeContext):
        node.a.accept(self, ctx)
        node.b.accept(self, ctx)
        atype, btype = node.a.get_type(), node.b.get_type()
        if not (isinstance(atype, FloatType) and isinstance(btype, FloatType)):
            raise TypeInferenceError(f"expected float type for operands in time_diff, got {atype} and {btype}")
        node.set_type(FloatType())
    
    def visitMinFunc(self, node: MinFunc, ctx: TypeContext):
        node.a.accept(self, ctx)
        node.b.accept(self, ctx)
        atype, btype = node.a.get_type(), node.b.get_type()
        if not atype.is_same(btype):
            raise TypeInferenceError(f"expected same type for operands in min, got {atype} and {btype}")
        node.set_type(atype)
    
    def visitMaxFunc(self, node: MaxFunc, ctx: TypeContext):
        node.a.accept(self, ctx)
        node.b.accept(self, ctx)
        atype, btype = node.a.get_type(), node.b.get_type()
        if not atype.is_same(btype):
            raise TypeInferenceError(f"expected same type for operands in max, got {atype} and {btype}")
        node.set_type(atype)
    
    def visitByteSizeFunc(self, node: ByteSizeFunc, ctx: TypeContext):
        node.var.accept(self, ctx)
        node.set_type(IntType())
            