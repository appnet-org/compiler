lib_rs = """
use proxy_wasm::traits::{{Context, HttpContext}};
use proxy_wasm::types::{{Action, LogLevel}};
use proxy_wasm::traits::RootContext;

// use prost::Message;
// TODO: Change if your change the proto file
pub mod ping {{
    include!(concat!(env!("OUT_DIR"), "/ping_pb.rs"));
}}

// TODO: Add global variable here

#[no_mangle]
pub fn _start() {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {{ Box::new({FilterName}Root) }});
    proxy_wasm::set_http_context(|context_id, _| -> Box<dyn HttpContext> {{
        Box::new({FilterName}Body {{ context_id }})
    }});
    {Init}
}}

struct {FilterName}Root;

impl Context for {FilterName}Root {{}}

impl RootContext for {FilterName}Root {{
    fn on_vm_start(&mut self, _: usize) -> bool {{
        log::warn!("executing on_vm_start");
        true
    }}
}}

{GlobalVariables}

struct {FilterName}Body {{
    #[allow(unused)]
    context_id: u32,
}}

impl Context for {FilterName}Body {{}}

impl HttpContext for {FilterName}Body {{
    fn on_http_request_headers(&mut self, _num_of_headers: usize, end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_request_headers");
        if !end_of_stream {{
            return Action::Continue;
        }}
        {RequestHeaders}
        Action::Continue
    }}

    fn on_http_request_body(&mut self, _body_size: usize, end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_request_body");
        if !end_of_stream {{
            return Action::Pause;
        }}
        {RequestBody}
        Action::Continue
    }}

    fn on_http_response_headers(&mut self, _num_headers: usize, end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_response_headers");
        if !end_of_stream {{
            return Action::Continue;
        }}
        {ResponseHeaders}
        Action::Continue
    }}

    fn on_http_response_body(&mut self, _body_size: usize, end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_response_body");
        if !end_of_stream {{
            return Action::Pause;
        }}
        {ResponseBody}
        Action::Continue
    }}
}}
"""
