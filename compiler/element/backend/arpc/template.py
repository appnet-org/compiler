sidecar_arpc_template = """package main

import (
	"context"
	"fmt"
	"math/rand"
	"time"

    {Imports}
	"github.com/appnet-org/arpc/pkg/logging"
	"github.com/appnet-org/proxy/util"
	"go.uber.org/zap"
)

// ExampleElement is a simple example element that logs requests and responses
type {ElementName} struct {{
    name string
    {GlobalVarDec}
}}

func randomf(lower, upper float64) float64 {{ 
	return lower + rand.Float64() * (upper - lower)
}}

func current_time() float64 {{
    return float64(time.Now().UnixMicro())
}}

func time_diff(a, b float64) float64 {{
    return (a - b) / 1000000.0
}}

{GlobalFunc}

func (e *{ElementName}) init() {{
	{InitCode}
}}

// ProcessRequest processes incoming requests
func (e *{ElementName}) ProcessRequest(ctx context.Context, packet *util.BufferedPacket) (*util.BufferedPacket, util.PacketVerdict, context.Context, error) {{
	if packet == nil {{
		return packet, util.PacketVerdictPass, ctx, nil
	}}
	{ReqCode}
}}

// ProcessResponse processes outgoing responses
func (e *{ElementName}) ProcessResponse(ctx context.Context, packet *util.BufferedPacket) (*util.BufferedPacket, util.PacketVerdict, context.Context, error) {{
	if packet == nil {{
		return packet, util.PacketVerdictPass, ctx, nil
	}}
	{RespCode}
}}

// Name returns the name of this element
func (e *{ElementName}) Name() string {{
    return e.name
}}

// RPCElement is the interface that elements must implement
// NOTE: This must match the interface defined in cmd/proxy/element.go
// For proper type sharing, consider moving RPCElement to a shared package
type RPCElement interface {{
	ProcessRequest(ctx context.Context, packet *util.BufferedPacket) (*util.BufferedPacket, util.PacketVerdict, context.Context, error)
	ProcessResponse(ctx context.Context, packet *util.BufferedPacket) (*util.BufferedPacket, util.PacketVerdict, context.Context, error)
	Name() string
}}

// ExampleElementInit implements the elementInit interface required by the plugin loader
type {ElementName}Init struct {{
	element *{ElementName}
}}

// Element returns the RPCElement instance as interface{{}}
// NOTE: Must return interface{{}} (not a specific type) for plugin type assertion to work
func (e *{ElementName}Init) Element() interface{{}} {{
	return e.element
}}

// Init is called when the plugin is initialized
func (e *{ElementName}Init) Init() {{
	e.element.init()
}}

// Kill is called when the plugin is being unloaded (optional cleanup)
func (e *{ElementName}Init) Kill() {{
	// Cleanup any background goroutines or resources here
	// For this example, there's nothing to clean up
	logging.Info("ExampleElement: Plugin being unloaded, performing cleanup")
}}

// ElementInit is the exported symbol that the plugin loader looks for
// This must be named exactly "ElementInit"
//
// IMPORTANT: Export as interface{{}} so that plugin.Lookup returns *interface{{}},
// which the elementloader can dereference to get the concrete type that
// implements Element() and Kill() methods.
var ElementInit interface{{}} = &{ElementName}Init{{
	element: &{ElementName}{{
		name: "{ElementName}",
        {GlobalVarInit}
	}},
}}

// init function is called when the plugin is loaded
func init() {{
	fmt.Println("{ElementName} plugin loaded successfully")
}}
"""