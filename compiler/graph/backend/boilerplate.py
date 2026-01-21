# gRPC templates

go_mod = """
module appnet.wiki/{ServiceName}

go 1.22.1

require (
	{ProtoModuleRequires}
	golang.org/x/net v0.29.0
	google.golang.org/grpc v1.66.2
	google.golang.org/protobuf v1.34.2
)

require (
	golang.org/x/sys v0.25.0 // indirect
	golang.org/x/text v0.18.0 // indirect
  google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1 // indirect
)

{ProtoModuleReplaces}

"""

go_sum = """
github.com/google/go-cmp v0.6.0 h1:ofyhxvXcZhMsU5ulbFiLKl/XBFqE1GSq7atu8tAmTRI=
github.com/google/go-cmp v0.6.0/go.mod h1:17dUlkBOakJ0+DkrSSNjCkIjxS6bF9zb3elmeNGIjoY=
golang.org/x/net v0.29.0 h1:5ORfpBpCs4HzDYoodCDBbwHzdR5UrLBZ3sOnUJmFoHo=
golang.org/x/net v0.29.0/go.mod h1:gLkgy8jTGERgjzMic6DS9+SP0ajcu6Xu3Orq/SpETg0=
golang.org/x/sys v0.25.0 h1:r+8e+loiHxRqhXVl6ML1nO3l1+oFoWbnlu2Ehimmi34=
golang.org/x/sys v0.25.0/go.mod h1:/VUhepiaJMQUp4+oa/7Zr1D23ma6VTLIYjOOTFZPUcA=
golang.org/x/text v0.18.0 h1:XvMDiNzPAl0jr17s6W9lcaIhGUfUORdGCNsuLmPG224=
golang.org/x/text v0.18.0/go.mod h1:BuEKDfySbSR4drPmRPG/7iBdf8hvFMuRexcpahXilzY=
google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1 h1:pPJltXNxVzT4pK9yD8vR9X75DaWYYmLGMsEvBfFQZzQ=
google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1/go.mod h1:UqMtugtsSgubUsoxbuAoiCXvqvErP7Gf0so0mK9tHxU=
google.golang.org/grpc v1.66.2 h1:3QdXkuq3Bkh7w+ywLdLvM56cmGvQHUMZpiCzt6Rqaoo=
google.golang.org/grpc v1.66.2/go.mod h1:s3/l6xSSCURdVfAnL+TqCNMyTDAGN6+lZeVxnZR128Y=
google.golang.org/protobuf v1.34.2 h1:6xV6lTsCfpGD21XK49h7MhtcApnLqkfYgPcdHftf6hg=
google.golang.org/protobuf v1.34.2/go.mod h1:qYOHts0dSfpeUzUFpOMr/WGzszTmLH+DiWniOlNbLDw=
"""

intercept_init = """
package main

import (
  "context"

	"google.golang.org/grpc"
)

{GlobalFuncDef}
var killed bool

type interceptInit struct{{}}

func (interceptInit) ClientInterceptor() grpc.UnaryClientInterceptor {{
  {ClientMethodInterceptors}

	return func(ctx context.Context, method string, req, reply interface{{}}, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {{
		{ClientMethodMatches}

		return invoker(ctx, method, req, reply, cc, opts...)
	}}
}}
func (interceptInit) ServerInterceptor() grpc.UnaryServerInterceptor {{
	{ServerMethodInterceptors}

	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {{
    {ServerMethodMatches}

		return handler(ctx, req)
	}}
}}
func (interceptInit) Kill() {{
	killed = true
}}

var InterceptInit interceptInit

// chained interceptor generation from https://github.com/grpc/grpc-go/blob/4e8f9d4a1e93923dd83816dba9470990ed031ac9/server.go#L1185
func chainUnaryServerInterceptors(interceptors []grpc.UnaryServerInterceptor) grpc.UnaryServerInterceptor {{
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {{
		return interceptors[0](ctx, req, info, getChainUnaryHandler(interceptors, 0, info, handler))
	}}
}}

func getChainUnaryHandler(interceptors []grpc.UnaryServerInterceptor, curr int, info *grpc.UnaryServerInfo, finalHandler grpc.UnaryHandler) grpc.UnaryHandler {{
	if curr == len(interceptors)-1 {{
		return finalHandler
	}}
	return func(ctx context.Context, req any) (any, error) {{
		return interceptors[curr+1](ctx, req, info, getChainUnaryHandler(interceptors, curr+1, info, finalHandler))
	}}
}}

// chained interceptor generation from https://github.com/grpc/grpc-go/blob/55cd7a68b3c18a0f76ea9c1be37221a5b901a798/clientconn.go#L435
func chainUnaryClientInterceptors(interceptors []grpc.UnaryClientInterceptor) grpc.UnaryClientInterceptor {{
	var chainedInt grpc.UnaryClientInterceptor
	if len(interceptors) == 0 {{
		chainedInt = nil
	}} else if len(interceptors) == 1 {{
		chainedInt = interceptors[0]
	}} else {{
		chainedInt = func(ctx context.Context, method string, req, reply any, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {{
			return interceptors[0](ctx, method, req, reply, cc, getChainUnaryInvoker(interceptors, 0, invoker), opts...)
		}}
	}}
	return chainedInt
}}

func getChainUnaryInvoker(interceptors []grpc.UnaryClientInterceptor, curr int, finalInvoker grpc.UnaryInvoker) grpc.UnaryInvoker {{
	if curr == len(interceptors)-1 {{
		return finalInvoker
	}}
	return func(ctx context.Context, method string, req, reply any, cc *grpc.ClientConn, opts ...grpc.CallOption) error {{
		return interceptors[curr+1](ctx, method, req, reply, cc, getChainUnaryInvoker(interceptors, curr+1, finalInvoker), opts...)
	}}
}}
"""

client_method_match = """
if method == "{FullMethodName}" {{
  if {MethodName}_interceptor == nil {{
    {MethodName}_interceptor = chainUnaryClientInterceptors([]grpc.UnaryClientInterceptor{{ {InterceptorList} }})
  }}

  return {MethodName}_interceptor(ctx, method, req, reply, cc, invoker, opts...)
}}
"""

server_method_match = """
if info.FullMethod == "{FullMethodName}" {{
  if {MethodName}_interceptor == nil {{
    {MethodName}_interceptor = chainUnaryServerInterceptors([]grpc.UnaryServerInterceptor{{ {InterceptorList} }})
  }}

  return {MethodName}_interceptor(ctx, req, info, handler)
}}
"""

# Envoy templates

attach_yml_sidecar_wasm = """apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {metadata_name}
spec:
  workloadSelector:
    labels:
      {service_label}: {service}
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: {bound}
      listener:
        portNumber: {port}
        filterChain:
          filter:
            name: "envoy.filters.network.http_connection_manager"
            subFilter:
              name: "envoy.filters.http.router"
    patch:
      operation: INSERT_FIRST
      value:
        name: envoy.filters.http.wasm
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
          config:
            name: {name}
            root_id: {name}
            vm_config:
              vm_id: {vmid}
              runtime: envoy.wasm.runtime.v8
              code:
                local:
                  filename: {filename}
              allow_precompiled: false
  - applyTo: CLUSTER
    match:
        context: {bound}
    patch:
      operation: ADD
      value:
        name: "webdis-service-{ename}"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: webdis-service-{ename}
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: webdis-service-{ename}
                        port_value: 7379
---
"""


attach_yml_ambient_wasm = """apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {metadata_name}
  namespace: default
spec:
  workloadSelector:
    labels:
      gateway.networking.k8s.io/gateway-name: {service}-waypoint
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: {bound}
      listener:
        filterChain:
          filter:
            name: "envoy.filters.network.http_connection_manager"
            subFilter:
              name: "envoy.filters.http.router"
    patch:
      operation: INSERT_FIRST
      value:
        name: envoy.filters.http.wasm
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
          config:
            name: {name}
            root_id: {name}
            vm_config:
              vm_id: {vmid}
              runtime: envoy.wasm.runtime.v8
              code:
                local:
                  filename: {filename}
              allow_precompiled: false
  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "webdis-service-{ename}"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: webdis-service-{ename}
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: webdis-service-{ename}
                        port_value: 7379
---
"""


attach_yml_ambient_native = """apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {metadata_name}
  namespace: default
spec:
  workloadSelector:
    labels:
      gateway.networking.k8s.io/gateway-name: {service}-waypoint
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: {bound}
      listener:
        filterChain:
          filter:
            name: "envoy.filters.network.http_connection_manager"
            subFilter:
              name: "envoy.filters.http.router"
    patch:
      operation: INSERT_BEFORE
      value:
        name: appnet{ename}
        typed_config:
          "@type": "type.googleapis.com/xds.type.v3.TypedStruct"
          type_url: "type.googleapis.com/appnet{ename}.FilterConfig"
  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "webdis-service-{ename}"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: webdis-service-{ename}
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: webdis-service-{ename}
                        port_value: 7379
  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "load-manager"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: load-manager
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: load-manager
                        port_value: 8080

  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "shard-manager"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: shard-manager
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: shard-manager
                        port_value: 8080
---
"""


attach_yml_sidecar_native = """apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {metadata_name}
spec:
  workloadSelector:
    labels:
      {service_label}: {service}
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: {bound}
      listener:
        portNumber: {port}
        filterChain:
          filter:
            name: "envoy.filters.network.http_connection_manager"
            subFilter:
              name: "envoy.filters.http.router"
    patch:
      operation: INSERT_FIRST
      value:
        name: appnet{ename}
        typed_config:
          "@type": "type.googleapis.com/xds.type.v3.TypedStruct"
          type_url: "type.googleapis.com/appnet{ename}.FilterConfig"
  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "webdis-service-{ename}"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: webdis-service-{ename}
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: webdis-service-{ename}
                        port_value: 7379
  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "load-manager"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: load-manager
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: load-manager
                        port_value: 8080

  - applyTo: CLUSTER
    match:
        context: SIDECAR_OUTBOUND
    patch:
      operation: ADD
      value:
        name: "shard-manager"
        connect_timeout: 5s
        type: STRICT_DNS
        lb_policy: ROUND_ROBIN
        load_assignment:
          cluster_name: shard-manager
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: shard-manager
                        port_value: 8080
---
"""


# aRPC templates

arpc_go_mod = """
module appnet.wiki/{ServiceName}

go 1.24.0

replace github.com/appnet-org/arpc => /users/xzhu/arpc
{ExtraReplaces}
require (
	github.com/appnet-org/arpc v0.0.0-00010101000000-000000000000
	github.com/appnet-org/arpc/benchmark/kv-store-symphony-element v0.0.0-00010101000000-000000000000
	github.com/appnet-org/arpc/cmd/proxy v0.0.0-20260121015706-909e25aff3d6
	go.uber.org/zap v1.27.1
)

require (
	capnproto.org/go/capnp/v3 v3.1.0-alpha.1 // indirect
	github.com/colega/zeropool v0.0.0-20230505084239-6fb4a4f75381 // indirect
	go.uber.org/multierr v1.11.0 // indirect
	golang.org/x/sync v0.17.0 // indirect
	google.golang.org/protobuf v1.36.10 // indirect
)


"""

arpc_go_sum = """
capnproto.org/go/capnp/v3 v3.1.0-alpha.1 h1:8/sMnWuatR99G0L0vmnrXj0zVP0MrlyClRqSmqGYydo=
capnproto.org/go/capnp/v3 v3.1.0-alpha.1/go.mod h1:2vT5D2dtG8sJGEoEKU17e+j7shdaYp1Myl8X03B3hmc=
github.com/colega/zeropool v0.0.0-20230505084239-6fb4a4f75381 h1:d5EKgQfRQvO97jnISfR89AiCCCJMwMFoSxUiU0OGCRU=
github.com/colega/zeropool v0.0.0-20230505084239-6fb4a4f75381/go.mod h1:OU76gHeRo8xrzGJU3F3I1CqX1ekM8dfJw0+wPeMwnp0=
github.com/davecgh/go-spew v1.1.1 h1:vj9j/u1bqnvCEfJOwUhtlOARqs3+rkHYY13jYWTU97c=
github.com/davecgh/go-spew v1.1.1/go.mod h1:J7Y8YcW2NihsgmVo/mv3lAwl/skON4iLHjSsI+c5H38=
github.com/google/go-cmp v0.7.0 h1:wk8382ETsv4JYUZwIsn6YpYiWiBsYLSJiTsyBybVuN8=
github.com/google/go-cmp v0.7.0/go.mod h1:pXiqmnSA92OHEEa9HXL2W4E7lf9JzCmGVUdgjX3N/iU=
github.com/philhofer/fwd v1.1.2 h1:bnDivRJ1EWPjUIRXV5KfORO897HTbpFAQddBdE8t7Gw=
github.com/philhofer/fwd v1.1.2/go.mod h1:qkPdfjR2SIEbspLqpe1tO4n5yICnr2DY7mqEx2tUTP0=
github.com/pmezard/go-difflib v1.0.0 h1:4DBwDE0NGyQoBHbLQYPwSUPoCMWR5BEzIk/f1lZbAQM=
github.com/pmezard/go-difflib v1.0.0/go.mod h1:iKH77koFhYxTK1pcRnkKkqfTogsbg7gZNVY4sRDYZ/4=
github.com/stretchr/testify v1.9.0 h1:HtqpIVDClZ4nwg75+f6Lvsy/wHu+3BoSGCbBAcpTsTg=
github.com/stretchr/testify v1.9.0/go.mod h1:r2ic/lqez/lEtzL7wO/rwa5dbSLXVDPFyf8C91i36aY=
github.com/tinylib/msgp v1.1.9 h1:SHf3yoO2sGA0veCJeCBYLHuttAVFHGm2RHgNodW7wQU=
github.com/tinylib/msgp v1.1.9/go.mod h1:BCXGB54lDD8qUEPmiG0cQQUANC4IUQyB2ItS2UDlO/k=
github.com/tj/assert v0.0.3 h1:Df/BlaZ20mq6kuai7f5z2TvPFiwC3xaWJSDQNiIS3Rk=
github.com/tj/assert v0.0.3/go.mod h1:Ne6X72Q+TB1AteidzQncjw9PabbMp4PBMZ1k+vd1Pvk=
go.uber.org/goleak v1.3.0 h1:2K3zAYmnTNqV73imy9J1T3WC+gmCePx2hEGkimedGto=
go.uber.org/goleak v1.3.0/go.mod h1:CoHD4mav9JJNrW/WLlf7HGZPjdw8EucARQHekz1X6bE=
go.uber.org/multierr v1.11.0 h1:blXXJkSxSSfBVBlC76pxqeO+LN3aDfLQo+309xJstO0=
go.uber.org/multierr v1.11.0/go.mod h1:20+QtiLqy0Nd6FdQB9TLXag12DsQkrbs3htMFfDN80Y=
go.uber.org/zap v1.27.1 h1:08RqriUEv8+ArZRYSTXy1LeBScaMpVSTBhCeaZYfMYc=
go.uber.org/zap v1.27.1/go.mod h1:GB2qFLM7cTU87MWRP2mPIjqfIDnGu+VIO4V/SdhGo2E=
golang.org/x/sync v0.17.0 h1:l60nONMj9l5drqw6jlhIELNv9I0A4OFgRsG9k2oT9Ug=
golang.org/x/sync v0.17.0/go.mod h1:9KTHXmSnoGruLpwFjVSX0lNNA75CykiMECbovNTZqGI=
google.golang.org/protobuf v1.36.10 h1:AYd7cD/uASjIL6Q9LiTjz8JLcrh/88q5UObnmY3aOOE=
google.golang.org/protobuf v1.36.10/go.mod h1:HTf+CrKn2C3g5S8VImy6tdcUvCska2kB7j23XfzDpco=
gopkg.in/yaml.v3 v3.0.1 h1:fxVm/GzAzEWqLHuvctI91KS9hhNmmWOoWu0XTYJS7CA=
gopkg.in/yaml.v3 v3.0.1/go.mod h1:K4uyk7z7BCEPqu6E+C64Yfv1cQ7kz7rIZviUmN+EgEM=
"""