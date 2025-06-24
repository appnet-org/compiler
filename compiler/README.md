## Chain Compiler Usage

## Usage

```bash
sed -i 's|<COMPILER_DIR>|'"$(pwd)"'|g' examples/chain/echo.yaml
python compiler/main.py --spec examples/chain/echo.yaml -v 

usage: main.py [-h] -s SPEC_PATH [--opt_level {no,ignore,weak,strong}] [--replica REPLICA] [-t TAG] [-v] [--envoy_verbose] [--pseudo_property] [--pseudo_impl] [--dry_run] [--dump_property]
               [--opt_algorithm {cost,heuristics}] [--debug]

options:
  -h, --help            show this help message and exit
  -s SPEC_PATH, --spec_path SPEC_PATH
                        Path to user specification file.
  --opt_level {no,ignore,weak,strong}
                        Optimization level, default is weak. no: no optimization; ignore: aggresive, ignore equivalence requirements; weak: allow differences in drop rate, records, etc.; strong: strict
                        equivalence.
  --replica REPLICA     the number of replicas for each service, default is 1.
  -t TAG, --tag TAG     Tag number for the current version, used for seamless upgrades. Usually users do not need to manually configure this.
  -v, --verbose         [Dev] If added, request graphs (i.e., element chains) on each edge will be printed on the terminal.
  --envoy_verbose       [Dev] If added, verbose logging will be generated in envoy native filter.
  --pseudo_property     [Dev] If added, use hand-coded properties instead of auto-generated ones.
  --pseudo_impl         [Dev] If added, use hand-coded implementations instead of auto-generated ones.
  --dry_run             [Dev] If added, the compilation terminates after optimization (i.e., no backend scriptgen).
  --dump_property       [Dev] If added, dump the properties of each element in yaml format.
  --opt_algorithm {cost,heuristics}
                        [Dev] Optimization algorithm, default is cost. If heuristics is chosen, only intra-element optimizations (i.e., placement and processor changes) will be applied.
  --debug               [Dev] Print debug info.
```

The compiler will automatically install elements on all the nodes and
* Generate manifest files if the backend is Envoy. Use `kubectl apply -f <manifest-files>` to run the application


## Element Compiler Usage

Follow these steps if you want to interact with the element compiler directly.

The element compiler convert AppNet program to an IR. From IR, we can infer the element property (used by graph compiler). The element compiler also generates backend code for each element.

```bash
python compiler/test/element_compiler_test.py --element examples/elements/echo_elements/fault.appnet --backend sidecar_wasm --placement client --proto ping.proto --method_name PingEcho

usage: element_compiler_test.py [-h] -e ELEMENT_PATH [-v] [-n MOD_NAME] [-l MOD_LOCATION] -p PLACEMENT -r PROTO -m METHOD_NAME
                                -b BACKEND

options:
  -h, --help            show this help message and exit
  -e ELEMENT_PATH, --element_path ELEMENT_PATH
                        (Element_path',') *
  -v, --verbose         Print Debug info
  -p PLACEMENT, --placement PLACEMENT
                        Placement of the generated code
  -r PROTO, --proto PROTO
                        Filename of the Protobuf definition (e.g., hello.proto)
  -m METHOD_NAME, --method_name METHOD_NAME
                        Method Name (must be defined in proto)
  -b BACKEND, --backend BACKEND
                        Backend Code Target
  -n MOD_NAME, --mod_name MOD_NAME
                        Go Protobuf Module Name
  -l MOD_LOCATION, --mod_location MOD_LOCATION
                        Go Protobuf Module Location
```

Note:
- The grammar is defined (in BNF format) [**here**](./element/frontend/element.lark).
