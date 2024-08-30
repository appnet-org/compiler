client_interceptor = """
package main

import (
  "math/rand"
	"sync"
	"time"
	"encoding/json"
	"io"
	"log"
	"net/http"

  {ProtoImport}
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"golang.org/x/net/context"

	"google.golang.org/grpc"
)

func {FilterName}ClientInterceptor() grpc.UnaryClientInterceptor {{
  {GlobalVariables}
  {Init}
  {OnTick}
	return func(ctx context.Context, method string, req, reply interface{{}}, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {{
		md, _ := metadata.FromOutgoingContext(ctx)
		rpc_id, _ := strconv.ParseUint(md.Get("appnet-rpc-id")[0], 10, 32)
		_ = rpc_id

        tag := md.Get("appnet-config-version")[0]
        if tag != "{Tag}" {{
			// version mismatch, skip
			return invoker(ctx, method, req, reply, cc, opts...)
		}}

    {Request}

		err := invoker(ctx, method, req, reply, cc, opts...)

    {Response}
		return err
	}}
}}
"""

server_interceptor = """
package main

import (
  "math/rand"
	"sync"
	"time"
	"encoding/json"
	"io"
	"log"
	"net/http"

  {ProtoImport}
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"golang.org/x/net/context"

	"google.golang.org/grpc"
)

func {FilterName}ServerInterceptor() grpc.UnaryServerInterceptor {{
	{GlobalVariables}
  {Init}
  {OnTick}
	return func(ctx context.Context, req interface{{}}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{{}}, error) {{
		md, _ := metadata.FromIncomingContext(ctx)
		rpc_id, _ := strconv.ParseUint(md.Get("appnet-rpc-id")[0], 10, 32)
    	_ = rpc_id

        tag := md.Get("appnet-config-version")[0]
        if tag != "{Tag}" {{
			// version mismatch, skip
			return handler(ctx, req);
		}}

    {Request}

		var reply any
    var err error
		if reply, err = handler(ctx, req); err == nil {{
    	{Response}
		}}

    return reply, err
	}}
}}
"""

on_tick_wrapper = """
go func() {{
	for !killed {{
		var res struct{{ MGET []*string }}
		{StateOnTick}
		time.Sleep(2 * time.Second)
	}}
}}()
"""

on_tick_template = """
mset_args_{state_name} := ""
for key, value := range {state_name} {{
	mset_args_{state_name} += fmt.Sprint("/", key, "_{state_name}", "/", value)
}}
http.Get("http://webdis-service-{element_name}:7379/MSET" + mset_args_{state_name})
mget_args_{state_name} := ""
for key := range {state_name} {{
	mget_args_{state_name} += fmt.Sprint("/", key, "_{state_name}")
}}
remote_read, err := http.Get("http://webdis-service-{element_name}:7379/MGET" + mget_args_{state_name})
if err == nil {{
	body, _ := io.ReadAll(remote_read.Body)
	remote_read.Body.Close()
	if remote_read.StatusCode < 300 {{
		_ = json.Unmarshal(body, &res)
		i := 0
		for key := range {state_name} {{
			if res.MGET[i] != nil {{
				{state_name}[key] = *res.MGET[i]
			}}
      i++
		}}
	}} else {{
		log.Println(remote_read.StatusCode)
	}}
}}
"""

intercept_init = """
package main

import (
	"google.golang.org/grpc"
)

{GlobalFuncDef}
var killed bool

type interceptInit struct{{}}

func (interceptInit) ClientInterceptors() []grpc.UnaryClientInterceptor {{
	return []grpc.UnaryClientInterceptor{{{ClientInterceptor}}}
}}
func (interceptInit) ServerInterceptors() []grpc.UnaryServerInterceptor {{
	return []grpc.UnaryServerInterceptor{{{ServerInterceptor}}}
}}

var InterceptInit interceptInit
"""

go_mod = """
module appnet.wiki/{FilterName}

go 1.22.1

require (
	{ProtoModuleName} v0.0.0-00010101000000-000000000000
	golang.org/x/net v0.24.0
	google.golang.org/grpc v1.63.2
	google.golang.org/protobuf v1.33.0
)

require (
	golang.org/x/sys v0.19.0 // indirect
	golang.org/x/text v0.14.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20240227224415-6ceb2ff114de // indirect
)

replace {ProtoModuleName} => {ProtoModuleLocation}

"""

go_sum = """
github.com/google/go-cmp v0.6.0 h1:ofyhxvXcZhMsU5ulbFiLKl/XBFqE1GSq7atu8tAmTRI=
github.com/google/go-cmp v0.6.0/go.mod h1:17dUlkBOakJ0+DkrSSNjCkIjxS6bF9zb3elmeNGIjoY=
golang.org/x/net v0.24.0 h1:1PcaxkF854Fu3+lvBIx5SYn9wRlBzzcnHZSiaFFAb0w=
golang.org/x/net v0.24.0/go.mod h1:2Q7sJY5mzlzWjKtYUEXSlBWCdyaioyXzRB2RtU8KVE8=
golang.org/x/sys v0.19.0 h1:q5f1RH2jigJ1MoAWp2KTp3gm5zAGFUTarQZ5U386+4o=
golang.org/x/sys v0.19.0/go.mod h1:/VUhepiaJMQUp4+oa/7Zr1D23ma6VTLIYjOOTFZPUcA=
golang.org/x/text v0.14.0 h1:ScX5w1eTa3QqT8oi6+ziP7dTV1S2+ALU0bI+0zXKWiQ=
golang.org/x/text v0.14.0/go.mod h1:18ZOQIKpY8NJVqYksKHtTdi31H5itFRjB5/qKTNYzSU=
google.golang.org/genproto/googleapis/rpc v0.0.0-20240227224415-6ceb2ff114de h1:cZGRis4/ot9uVm639a+rHCUaG0JJHEsdyzSQTMX+suY=
google.golang.org/genproto/googleapis/rpc v0.0.0-20240227224415-6ceb2ff114de/go.mod h1:H4O17MA/PE9BsGx3w+a+W2VOLLD1Qf7oJneAoU6WktY=
google.golang.org/grpc v1.63.2 h1:MUeiw1B2maTVZthpU5xvASfTh3LDbxHd6IJ6QQVU+xM=
google.golang.org/grpc v1.63.2/go.mod h1:WAX/8DgncnokcFUldAxq7GeB5DXHDbMF+lLvDomNkRA=
google.golang.org/protobuf v1.33.0 h1:uNO2rsAINq/JlFpSdYEKIZ0uKD/R9cpdv0T+yoGwGmI=
google.golang.org/protobuf v1.33.0/go.mod h1:c6P6GXX6sHbq/GpV6MGZEdwhWPcYBgnhAHhKbcUYpos=
"""

build_sh = """
#!/usr/bin/env bash

WORKDIR=`dirname $(realpath $0)`
cd $WORKDIR

go build -trimpath -o interceptor.so -buildmode=plugin .

"""
