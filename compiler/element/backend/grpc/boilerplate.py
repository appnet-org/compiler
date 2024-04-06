client_interceptor = """
package interceptor

import (
  "math/rand"
	"sync"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"golang.org/x/net/context"

	"google.golang.org/grpc"
)

{GlobalFuncDef}

func ClientInterceptor() grpc.UnaryClientInterceptor {{
  {GlobalVariables}
  {Init}
	return func(ctx context.Context, method string, req, reply interface{{}}, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {{
    {Request}
		
		err := invoker(ctx, method, req, reply, cc, opts...)

    {Response}
		return err
	}}
}}
"""

server_interceptor = """
package interceptor

import (
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"golang.org/x/net/context"

	"google.golang.org/grpc"
)

{GlobalFuncDef}

func FaultServer(optFuncs ...CallOption) grpc.UnaryServerInterceptor {{
	{GlobalVariables}
  {Init}
	return func(ctx context.Context, req interface{{}}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{{}}, error) {{
		{Request}
  
		h := handler(ctx, req) // deal with this (overlap with user variables)
    
    {Response}
    return
	}}
}
"""