from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional


class RustType():
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


class RustBasicType(RustType):
    def __init__(self, name: str, init_val: Optional[str] = None):
        super().__init__(name)
        self.init_val = init_val

    def is_basic(self) -> bool:
        return True

    def gen_init(self) -> str:
        if self.init_val is None:
            return f"{self.name}::default()"
        else:
            return self.init_val


class RustVecType(RustType):
    def __init__(self, con: str, elem: RustType) -> None:
        super().__init__(f"{con}<{elem.name}>")
        self.con = con
        self.elem = elem

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert(len(args) == 1)
        return f".[{args[0]}]"

class RustMapType(RustType):
    def __init__(self, con: str, key: RustType, value: RustType) -> None:
        super().__init__(f"{con}<{key.name}, {value.name}>")
        self.con = con
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"{self.con}::new()"
    
    def gen_get(self, args: List[str]) -> str:
        assert(len(args) == 1)
        return f".[{args[0]}]"

class RustRpcType(RustType):
    def __init__(self, name: str, fields: List[(str, RustType)]):
        super().__init__(name)
        self.fields = fields
    
    def gen_get(self, args: List[str]) -> str:
        assert(len(args) == 1)
        return f".{args[0]}"

class RustFunctionType(RustType):
    def __init__(self, name: str, args: List[RustType], ret: RustType, definition: str):
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


class RustVariable():
    def __init__(
        self,
        name: str,
        rust_type: RustType,
        mut: bool = True,
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = rust_type
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


RustGlobalFunctions = {
    "cur_ts": RustFunctionType(
        "Gen_current_timestamp",
        [],
        RustBasicType("Instant"),
        "pub fn Gen_current_timestamp() -> Instant { Instant::now() }",
    ),
    "time_diff": RustFunctionType(
        "Gen_time_difference",
        [RustBasicType("Instant"), RustBasicType("Instant")],
        RustBasicType("f32"),
        "pub fn Gen_time_difference(a: Instant, b: Instant) -> f32 {(a - b).as_secs_f64() as f32}",
    ),
    "random_f64": RustFunctionType(
        "Gen_random_f64",
        [],
        RustBasicType("f64"),
        "pub fn Gen_random_f64() -> f64 { rand::random::<f64>() }",
    ),
    "min": RustFunctionType(
        "Gen_min",
        [RustBasicType("u64"), RustBasicType("u64")],
        RustBasicType("u32"),
        "pub fn Gen_min(a: u32, b: f32) -> u32 { (a as f32).min(b) as u32}",
    ),
}


# tx_struct = RustStructType(
#     "RpcMessageTx",
#     [
#         ("meta_buf_ptr", RustStructType("MetaBufferPtr", [])),
#         ("addr_backend", RustBasicType("usize")),
#     ],
# )

# rx_struct = RustStructType("RpcMessageRx", [("meta_buf_ptr", RustStructType("MetaBufferPtr", [])), ("addr_backend", RustBasicType("usize"))])
