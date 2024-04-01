client_interceptor = """
package interceptor

import (
  "math/rand"
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

func FaultServer(optFuncs ...CallOption) grpc.UnaryServerInterceptor {


	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		log.Println("Running FaultUnaryServerInterceptor")

		// Generate a random float between 0 and 1.
		rand.Seed(time.Now().UnixNano())
		p := rand.Float64()
		
		if p <= intOpts.abortProbability {
			return nil, status.Error(codes.Aborted, "request aborted by fault injection.")
		}

		return handler(ctx, req)
	}
}
"""