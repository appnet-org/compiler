# ADN Element Compiler

Element compiler convert ADN program to an IR. From IR, we can infer the element property (used by graph compiler). The element compiler also generates backend code for each element.

## Usage

```
cd compiler
export PYTHONPATH=$PYTHONPATH:$(pwd):$(dirname $(pwd))
python ir_main.py -e acl -v True
# v for verbose, which is `false` by default
# refer to example/match-action for more engine names
```

## Supported Backends

- [**mRPC**](https://github.com/phoenix-dataplane/phoenix) 
- [**Envoy**](https://www.envoyproxy.io/) (via [**Proxy WASM**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk))
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))
    - In progress