from __future__ import annotations

from typing import List, Optional

from compiler.element.logger import ELEMENT_LOG as LOG


class GoType:
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

    def gen_get(self, args, vname, ename):
        raise NotImplementedError

    def gen_set(self, args, vname, ename, current_procedure):
        raise NotImplementedError

    def gen_delete(self, args):
        raise NotImplementedError

    def gen_size(self):
        raise NotImplementedError


class GoBasicType(GoType):
    def __init__(self, name: str, init_val: Optional[str] = None):
        super().__init__(name)
        self.init_val = init_val

    def is_basic(self) -> bool:
        return True

    def gen_init(self) -> str:
        match self.name:
            case "string":
                return '""'
            case "float32":
                return "0.0"
            case "float64":
                return "0.0"
            case _:
                return "0"

    def string_conversion(self, expression) -> str:
        match self.name:
            case "string":
                return expression
            case "uint32":
                return f"strconv.FormatUint(uint64({expression}), 10)"
            case "int":
                return f"strconv.FormatInt(int64({expression}), 10)"
            case "float64":
                return f"strconv.FormatFloat({expression}, 'f', -1, 64)"
        assert False, "unsupported key type"


class GoVecType(GoType):
    def __init__(self, elem_type: GoType) -> None:
        super().__init__(f"[]{elem_type.name}")
        self.elem_type = elem_type

    def gen_init(self) -> str:
        return f"make({self.name}, 0, 0)"

    def gen_get(self, args: List[str], vname: str, ename: str) -> str:
        assert len(args) == 1
        return f"[{args[0]}]"

    def gen_set(
        self, args: List[str], vname: str, ename: str, current_procedure: str
    ) -> str:
        assert len(args) == 2
        if args[0].startswith("len(") and args[0].endswith(")"):
            return f"= append({vname}, {args[1]})"
        else:
            return f"[{args[0]}] = {args[1]})"

    def gen_delete(self, args):
        raise NotImplementedError


class GoMapType(GoType):
    def __init__(self, key: GoType, value: GoType) -> None:
        super().__init__(f"map[{key.name}]{value.name}")
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"make({self.name})"

    def gen_get(self, args: List[str], vname: str, ename: str) -> str:
        assert len(args) == 1
        return f""" func() struct{{value {self.value.name}; ok bool}} {{
                        val, ok := {vname}[{args[0]}]
                        return struct{{value {self.value.name}; ok bool}} {{val, ok}}
                    }}()
                """

    def gen_set(
        self, args: List[str], vname: str, ename: str, current_procedure: str
    ) -> str:
        assert len(args) == 2
        return f"[{args[0]}] = {args[1]}"


class GoSyncMapType(GoType):
    # Calls external storage for every read/write
    def __init__(self, key: GoType, value: GoType) -> None:
        self.key = key
        self.value = value

    def gen_get(self, args: List[str], vname: str, ename: str) -> str:
        assert len(args) == 1
        return f"""func() struct{{value {self.value.name}; ok bool}} {{
                        remote_read, err := http.Get("http://webdis-service-{ename}:7379/GET/" + {self.key.string_conversion(args[0])} + "_{vname}")
                        var res struct {{
                            GET {self.value.name}
                        }}
                        if err == nil {{
                            body, _ := io.ReadAll(remote_read.Body)
                            remote_read.Body.Close()
                            if remote_read.StatusCode < 300 {{
                                _ = json.Unmarshal(body, &res)
                                return struct{{value {self.value.name}; ok bool}} {{res.GET, true}}
                            }} else {{
                                log.Println(remote_read.StatusCode)
                            }}
                        }}
                        return struct{{value {self.value.name}; ok bool}} {{res.GET, false}}
                    }}()"""

    def gen_set(
        self, args: List[str], vname: str, ename: str, current_procedure: str
    ) -> str:
        assert len(args) == 2
        return f"""func() {{
			        remote_write, err := http.Get("http://webdis-service-{ename}:7379/SET/" + {self.key.string_conversion(args[0])} + "_{vname}/" + {self.key.string_conversion(args[1])})
			        if err == nil {{
				        remote_write.Body.Close()
                        if remote_write.StatusCode > 299 {{
                            log.Println(remote_write.StatusCode)
                        }}
	        		}}
		        }}()"""


class GoRpcType(GoType):
    def __init__(self, name: str, fields: List[(str, GoType)]):
        super().__init__(name)
        self.fields = fields

    def snake_to_pascal_case(name: str) -> str:
        # snake_case pb field to PascalCase go pb field
        split_snake = name.strip('"').split("_")
        return "".join(w.title() for w in split_snake)

    def gen_get(self, args: List[str], vname: str, ename: str) -> str:
        assert len(args) == 1
        return f".{GoRpcType.snake_to_pascal_case(args[0])}"

    def gen_set(self, args, vname, ename, current_procedure) -> str:
        assert len(args) == 2
        return f".{GoRpcType.snake_to_pascal_case(args[0])} = {args[1]}"


class GoFunctionType(GoType):
    def __init__(
        self,
        name: str,
        args: List[GoType],
        ret: GoType,
        definition: str,
    ):
        super().__init__(name)
        self.args = args
        self.ret = ret
        self.definition = definition

    def __str__(self) -> str:
        return f"{self.name}({', '.join([str(i) for i in self.args])}) {self.ret}"

    def gen_def(self) -> str:
        return self.definition

    def gen_call(self, args: Optional[List[str]] = []) -> str:
        return f"{self.name}({', '.join(args)})"


class GoVariable:
    def __init__(
        self,
        name: str,
        go_type: GoType,
        temp: bool,
        rpc: bool,
        atomic: bool,
        consistency: str = None,
        combiner: str = "LWW",
        persistence: bool = False,
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = go_type
        self.temp = temp
        self.rpc = rpc
        self.atomic = atomic
        # if consistency is set to True, it means that this variable needs to be synchronized across all element instances.
        # Thus, we need to access a remote storage on every call.
        self.consistency = consistency
        # Combiner function for this variable. If not set, the default combiner function (last writer wins) is used.
        self.combiner = combiner
        # if persistence is set to True, it means that this variable needs to be persisted.
        self.persistence = persistence

        if init is None:
            self.init = ""
        else:
            self.init = init

    def __str__(self) -> str:
        return f"{self.name}: {self.type}"

    def gen_init(self) -> str:
        lock = ""
        if self.atomic:
            lock = f"; var {self.name}_mutex sync.RWMutex;"
        return f"var {self.name} {self.type} = {self.init}{lock}"


GoGlobalFunctions = {
    "current_time": GoFunctionType(
        "gen_current_timestamp",
        [],
        GoBasicType("float64"),
        """func gen_current_timestamp() float64 {
	        return float64(time.Now().UnixMicro())
        }""",
    ),
    "time_diff": GoFunctionType(
        "gen_time_difference",
        [GoBasicType("float64"), GoBasicType("float64")],
        GoBasicType("float64"),
        "func gen_time_difference(a, b float64) float64 { return (a - b) / 1000000.0 }",
    ),
    "random_float64": GoFunctionType(
        # TODO(nikolabo): should the random functions be taking bounds parameters? wasm takes but doesn't use any
        "gen_random_float64",
        [GoBasicType("float64"), GoBasicType("float64")],
        GoBasicType("float64"),
        "func gen_random_float64(a, b float64) float64 { return rand.Float64() }",
    ),
    "random_uint32": GoFunctionType(
        "gen_random_uint32",
        [GoBasicType("uint32"), GoBasicType("uint32")],
        GoBasicType("uint32"),
        "func gen_random_uint32(a, b uint32) uint32 { return rand.Uint32() }",
    ),
    "min_uint64": GoFunctionType(
        "gen_min_u64",
        [GoBasicType("uint64"), GoBasicType("uint64")],
        GoBasicType("uint64"),
        "func gen_min_uint64(a, b uint64) uint64 { return min(a, b) }",
    ),
    "min_float64": GoFunctionType(
        "gen_min_float64",
        [GoBasicType("float64"), GoBasicType("float64")],
        GoBasicType("float64"),
        "func gen_min_float64(a, b float64) float64 { return min(a, b) }",
    ),
    "max_float64": GoFunctionType(
        "gen_max_float64",
        [GoBasicType("float64"), GoBasicType("float64")],
        GoBasicType("float64"),
        "func gen_max_float64(a, b float64) float64 { return max(a, b) }",
    ),
}
