from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional


class WasmType:
    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return self.name

    def is_basic(self) -> bool:
        return False

    def is_con(self) -> bool:
        return False

    def gen_init(self) -> str:
        raise NotImplementedError

    def gen_get(self, args):
        raise NotImplementedError

    def gen_set(self, args):
        raise NotImplementedError

    def gen_delete(self, args):
        raise NotImplementedError

    def gen_size(self):
        raise NotImplementedError


class WasmBasicType(WasmType):
    def __init__(self, name: str, init_val: Optional[str] = None):
        super().__init__(name)
        self.init_val = init_val

    def is_basic(self) -> bool:
        return True

    def gen_init(self) -> str:
        raise NotImplementedError


class WasmVecType(WasmType):
    def __init__(self, con: str, elem: WasmType) -> None:
        super().__init__(f"{con}<{elem.name}>")
        self.con = con
        self.elem = elem

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get({args[0]})"

    def gen_set(self, args: List[str]) -> str:
        assert len(args) == 2
        if args[0].endswith(".len()"):
            return f".push({args[1]})"
        else:
            return f".set({args[0]}, {args[1]})"

    def gen_delete(self, args):
        assert len(args) == 1
        return f".remove({args[0]})"

    def gen_size(self) -> str:
        return f".len()"


class WasmMapType(WasmType):
    def __init__(self, con: str, key: WasmType, value: WasmType) -> None:
        super().__init__(f"{con}<{key.name}, {value.name}>")
        self.con = con
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get(&{args[0]})"

    def gen_set(self, args: List[str]) -> str:
        assert len(args) == 2
        return f".insert({args[0]}, {args[1]})"


class WasmRpcType(WasmType):
    def __init__(self, name: str, fields: List[(str, WasmType)]):
        super().__init__(name)
        self.fields = fields

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return "." + args[0].strip('"')


class WasmFunctionType(WasmType):
    def __init__(self, name: str, args: List[WasmType], ret: WasmType, definition: str):
        super().__init__(name)
        self.args = args
        self.ret = ret
        self.definition = definition

    def __str__(self) -> str:
        return f"{self.name}({', '.join([str(i) for i in self.args])}) -> {self.ret}"

    def gen_def(self) -> str:
        return self.definition

    def gen_call(self, args: Optional[List[str]] = []) -> str:
        return f"{self.name}({', '.join(args)})"


class WasmVariable:
    def __init__(
        self,
        name: str,
        wasm_type: WasmType,
        temp: bool,
        rpc: bool,
        atomic: bool,
        mut: bool = True,
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = wasm_type
        self.temp = temp
        self.rpc = rpc
        self.atomic = atomic
        self.mut = mut

        if init is None:
            self.init = ""
        else:
            self.init = init

    def __str__(self) -> str:
        return f"{'mut ' if self.mut else ''}{self.name}: {self.type}"

    def gen_init_localvar(self) -> str:
        return f"let mut {self.name} = {self.init};"

    def gen_init_self(self) -> str:
        return f"self.{self.name} = {self.init};"

    def gen_struct_declaration(self) -> str:
        return f"{self.name}: {self.type.name}"


WasmGlobalFunctions = {}
