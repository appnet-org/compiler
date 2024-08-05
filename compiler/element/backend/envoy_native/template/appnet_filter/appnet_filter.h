#pragma once

#include <string>
#include <mutex>
#include <chrono>
#include <algorithm>

#include "envoy/server/factory_context.h"
#include "source/extensions/filters/http/common/pass_through_filter.h"

#include "appnet_filter/appnet_filter.pb.h"

#include <coroutine>

namespace Envoy {
namespace Http {


struct AppnetCoroutine {
  struct promise_type {
    std::coroutine_handle<promise_type> *to_be_resumed_;

    AppnetCoroutine get_return_object() {
      std::cerr << "get_return_object " << this << std::endl;
      return AppnetCoroutine(std::coroutine_handle<promise_type>::from_promise(*this));
    }
    void unhandled_exception() noexcept {
      std::cerr << "unhandled exception" << std::endl;
      std::terminate();
    }
    void return_void() noexcept { }
    std::suspend_always initial_suspend() noexcept { 
      std::cerr << "initial_suspend " << this << std::endl;
      return {};
    }
    std::suspend_never final_suspend() noexcept {
      std::cerr << "final_suspend " << this << std::endl;
      return {};
    }
  };


  std::coroutine_handle<promise_type> handle_;

  explicit AppnetCoroutine(std::coroutine_handle<promise_type> handle)
      : handle_(handle) {
    std::cerr << "create app coroutine. handle_address=" << handle.address() << std::endl;
  }

  AppnetCoroutine(AppnetCoroutine&& rhs) {
    std::cerr << "move ctor from " << &rhs << " to " << this << std::endl;
    handle_ = rhs.handle_;
    rhs.handle_ = nullptr;
  }

  ~AppnetCoroutine() {
    std::cerr << "destroy " << this << std::endl;
    // if (handle_) {
    //   std::cerr << "still alive. destroy it" << std::endl;
    //   handle_.destroy();
    // }
  }
};

// Check https://zh.cppreference.com/w/cpp/language/coroutines#co_await.
struct Awaiter {
  std::mutex mutex_;
  bool ready_ = false;
  std::optional<std::coroutine_handle<AppnetCoroutine::promise_type>> to_be_resumed_;
  
  bool await_ready() noexcept { 
    std::cerr << "await_ready " << this << std::endl;
    std::lock_guard<std::mutex> lock(mutex_);

    return ready_;
  }

  bool await_suspend(std::coroutine_handle<AppnetCoroutine::promise_type> caller_handler) noexcept {
    std::cerr << "await_suspend " << this << std::endl;

    // Determine whether the webdis response arrived. 
    // If yes, just return false to continue the appnet coroutine.
    // If no, save the caller_handler to be resumed later.

    std::lock_guard<std::mutex> lock(mutex_);
    if (ready_) {
      return false;
    } else {
      to_be_resumed_ = caller_handler;
      return true;
    }
  }

  // the co_await statement uses this method to get the return value after 
  // the coroutine of this co_await is resumed.
  void await_resume() const noexcept {
    std::cerr << "await_resume " << this << std::endl;
  }

  // This function is called when the webdis response arrives. 
  // i.e. Filter::onSuccess()
  void i_am_ready() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::cerr << "i_am_ready " << this << std::endl;
    if (to_be_resumed_.has_value()) {
      // the caller is waiting for the response
      std::cerr << "resume the caller" << std::endl;
      to_be_resumed_.value().resume();
    } else {
      // the caller has not asked for the response yet.
      std::cerr << "no caller to resume" << std::endl;
      ready_ = true;
    }
  }
};


class AppnetFilterConfig {
public:
  AppnetFilterConfig(const sample::FilterConfig& proto_config, Envoy::Server::Configuration::FactoryContext &context);
  Envoy::Server::Configuration::FactoryContext &ctx_;
private:
};

using AppnetFilterConfigSharedPtr = std::shared_ptr<AppnetFilterConfig>;

class AppnetFilter 
      : public PassThroughFilter, 
        public Http::AsyncClient::Callbacks, 
        Logger::Loggable<Logger::Id::filter> {
public:
  AppnetFilter(AppnetFilterConfigSharedPtr);
  ~AppnetFilter();

  // Http::StreamFilterBase
  void onDestroy() override;

  // Http::StreamDecoderFilter
  FilterHeadersStatus decodeHeaders(RequestHeaderMap&, bool) override;
  FilterDataStatus decodeData(Buffer::Instance&, bool) override;
  void setDecoderFilterCallbacks(StreamDecoderFilterCallbacks&) override;

  // Http::StreamEncoderFilter
  FilterHeadersStatus encodeHeaders(ResponseHeaderMap&, bool) override;
  FilterDataStatus encodeData(Buffer::Instance&, bool) override;
  void setEncoderFilterCallbacks(StreamEncoderFilterCallbacks&) override;

  const AppnetFilterConfigSharedPtr config_;

  // Http::AsyncClient::Callbacks
  void onSuccess(const Http::AsyncClient::Request&, Http::ResponseMessagePtr&& message) override;
  void onFailure(const Http::AsyncClient::Request&, Http::AsyncClient::FailureReason) override;
  void onBeforeFinalizeUpstreamSpan(Tracing::Span&, const Http::ResponseHeaderMap*) override;

private:
  StreamDecoderFilterCallbacks* decoder_callbacks_;
  StreamEncoderFilterCallbacks* encoder_callbacks_;
  Callbacks *empty_callback_;

  RequestHeaderMap *request_headers_;
  ResponseHeaderMap *response_headers_;
  
  Buffer::Instance *request_buffer_;
  Buffer::Instance *response_buffer_;

  std::optional<Http::AppnetCoroutine> appnet_coroutine_;
  ResponseMessagePtr external_response_;
  std::optional<Awaiter*> webdis_awaiter_;

  AppnetCoroutine startRequestAppnet();
  AppnetCoroutine startResponseAppnet();
  bool sendWebdisRequest(const std::string path, Callbacks& filter);
};

class EmptyCallback : public Http::AsyncClient::Callbacks {
public:
  void onSuccess(const Http::AsyncClient::Request&, Http::ResponseMessagePtr&&) override {}
  void onFailure(const Http::AsyncClient::Request&, Http::AsyncClient::FailureReason) override {}
  void onBeforeFinalizeUpstreamSpan(Tracing::Span&, const Http::ResponseHeaderMap*) override {}
};

} // namespace Http
} // namespace Envoy
