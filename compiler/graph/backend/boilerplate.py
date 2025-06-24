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
