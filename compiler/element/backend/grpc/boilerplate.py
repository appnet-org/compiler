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
remote_read_{state_name}, err := http.Get("http://webdis-service-{element_name}:7379/MGET" + mget_args_{state_name})
if err == nil {{
	body, _ := io.ReadAll(remote_read_{state_name}.Body)
	remote_read_{state_name}.Body.Close()
	if remote_read_{state_name}.StatusCode < 300 {{
		_ = json.Unmarshal(body, &res)
		i := 0
		for key := range {state_name} {{
			if res.MGET[i] != nil {{
				{state_name}[key] = *res.MGET[i]
			}}
      i++
		}}
	}} else {{
		log.Println(remote_read_{state_name}.StatusCode)
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
	golang.org/x/net v0.29.0
	google.golang.org/grpc v1.66.2
	google.golang.org/protobuf v1.34.2
)

require (
	golang.org/x/sys v0.25.0 // indirect
	golang.org/x/text v0.18.0 // indirect
  	google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1 // indirect
)

replace {ProtoModuleName} => {ProtoModuleLocation}

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

build_sh = """
#!/usr/bin/env bash

WORKDIR=`dirname $(realpath $0)`
cd $WORKDIR

go build -trimpath -o interceptor.so -buildmode=plugin .

"""
