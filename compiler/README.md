## Chain Compiler Usage

## Usage

```bash
# Run the graph compiler on demo.yml to generate element code and deployment scripts for mRPC.
sed -i 's|<COMPILER_DIR>|'"$(pwd)"'|g' examples/chain/echo.yaml
python compiler/main.py --spec examples/chain/echo.yaml --backend envoy -v --opt_level no

usage: main.py [-h] -s SPEC_PATH [-v] [--pseudo_property] [--pseudo_impl] -b {mrpc,envoy}
               [--mrpc_dir MRPC_DIR] [--dry_run] [--opt_level {no,ignore,weak,strong}]
               [--no_optimize] [--replica REPLICA] [--opt_algorithm OPT_ALGORITHM] [--debug]

options:
  -h, --help            show this help message and exit
  -s SPEC_PATH, --spec_path SPEC_PATH
                        Path to user specification file
  -v, --verbose         If added, request graphs (i.e., element chains) on each edge will be
                        printed on the terminal
  --pseudo_property     If added, use hand-coded properties instead of auto-generated ones
  --pseudo_impl         If added, use hand-coded impl instead of auto-generated ones
  -b, --backend {mrpc, grpc, sidecar_wasm, sidecar_native, ambient_wasm, ambient_native}
                        Backend name
  --mrpc_dir MRPC_DIR   Path to mrpc repo
  --dry_run             If added, the compilation terminates after optimization (i.e., no
                        backend scriptgen)
  --opt_level {no,ignore,weak,strong}
                        optimization level
  --no_optimize         If added, no optimization will be applied to GraphIR
  --replica REPLICA     #replica for each service
  --opt_algorithm OPT_ALGORITHM
  --debug               Print debug info
```

The compiler will automatically install elements on all the nodes and
* Generate `attach_all.sh` and `detach_all.sh` in `graph/gen` if the backend is mRPC.
* Generate manifest files if the backend is Envoy. Use `kubectl apply -f <manifest-files>` to run the application


## Element Compiler Usage

Follow these steps if you want to interact with the element compiler directly.

The element compiler convert AppNet program to an IR. From IR, we can infer the element property (used by graph compiler). The element compiler also generates backend code for each element.

```bash
python compiler/element_compiler_test.py --element examples/elements/echo_elements/fault.appnet --backend envoy --placement client --proto ping.proto --method_name PingEcho

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

## Supported Backends

- [**mRPC**](https://github.com/phoenix-dataplane/phoenix)
- [**Envoy**](https://www.envoyproxy.io/) (via [**Proxy WASM**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk))
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))

    - Requires user application to provide their Go protobuf code as a module, and use of the `mod_name` and `mod_location` flags.
<!-- ## Deployment

### Mrpc

Fire up phoenixos and hotel applications.

```bash
# in all worker machines
docker pull kristoffstarling/hotel-service:multi

# in $HOME/phoenix/eval/hotel-bench
# By default, the services are deployed at
# Frontend - h2
# Geo      - h3
# Profile  - h4
# Rate     - h5
# Search   - h6
./start_container
./start_phoenix
# in another terminal
./start_service
```

After running the compiler, use `attach_all.sh` and `detach_all.sh` to attach/detach elements.

```bash
# in compiler/graph/gen
chmod +x attach_all.sh
chmod +x detach_all.sh
./attach_all.sh  # attach all engines
./detach_all.sh  # detach all engines
```

## Limitations

* Container name is hard-coded (only support hotel reservation).
* Service deployment information is currently provided by the user in the specification file (should query the controller instead).
* The graph compiler will generate a globally-unique element name for each element instance, but it requires the element's library name to be identical to the element's specification filename. -->
