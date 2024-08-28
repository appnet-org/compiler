#pragma once

#include <string>
#include <mutex>
#include <chrono>
#include <algorithm>

#include "envoy/server/factory_context.h"
#include "source/extensions/filters/http/common/pass_through_filter.h"

#include "source/extensions/filters/http/servercachestrong/appnet_filter.pb.h"
#include "source/common/http/message_impl.h" 

#include <coroutine>
#include <string_view>

namespace Envoy {
namespace Http {

namespace appnetservercachestrong {

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
    std::suspend_always final_suspend() noexcept {
      std::cerr << "final_suspend " << this << std::endl;
      return {};
    }
  };


  std::optional<std::coroutine_handle<promise_type>> handle_;

  explicit AppnetCoroutine(std::coroutine_handle<promise_type> handle)
      : handle_(handle) {
    std::cerr << "create app coroutine. this=" << this << std::endl;
  }

  AppnetCoroutine(const AppnetCoroutine& rhs) = delete;

  AppnetCoroutine(AppnetCoroutine&& rhs) {
    std::cerr << "move ctor from " << &rhs << " to " << this << std::endl;
    handle_ = rhs.handle_;
    rhs.handle_.reset();
  }

  ~AppnetCoroutine() {
    if (handle_.has_value()) {
      std::cerr << "destroy " << this << std::endl;
      assert(handle_.value().done());
      handle_.value().destroy();
    } else {
      std::cerr << "destroy " << this << " (no handle)" << std::endl;
    }
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
  AppnetFilterConfig(const ::appnetservercachestrong::FilterConfig& proto_config, Envoy::Server::Configuration::FactoryContext &context);
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


  int getRemoteEndpointNum() {
    auto &stream_info = this->decoder_callbacks_->streamInfo();
    auto cluster_info = stream_info.upstreamClusterInfo();
    if (cluster_info == nullptr) {
      ENVOY_LOG(info, "[AppNet Filter] cluster_info is null");
      PANIC("cluster_info is null");
    }
    ENVOY_LOG(info, "[AppNet Filter] cluster info: {}", cluster_info->get()->name());
    auto cluster = this->config_->ctx_.serverFactoryContext().clusterManager().getThreadLocalCluster(cluster_info->get()->name());
    if (!cluster) {
      ENVOY_LOG(info, "cluster not found");
      assert(0);
    }
    // check priority set num
    auto priority_set_num = cluster->prioritySet().hostSetsPerPriority().size();
    if (priority_set_num != 1) {
      ENVOY_LOG(info, "priority set num is not 1");
      assert(0);
    }
    auto host_list = cluster->prioritySet().hostSetsPerPriority()[0]->hosts();
    return host_list.size();
  }

  void setRoutingEndpoint(int x) {
    auto map = decoder_callbacks_->requestHeaders();

    if (map->get(LowerCaseString("dst")).empty()) {
      map->addCopy(LowerCaseString("dst"), x);
    } else {
      auto x_str = std::to_string(x);
      std::string_view x_str_view = x_str;
      map->setCopy(LowerCaseString("dst"), x_str_view);
    }
  }

private:
  StreamDecoderFilterCallbacks* decoder_callbacks_;
  StreamEncoderFilterCallbacks* encoder_callbacks_;
  Callbacks *empty_callback_;

  RequestHeaderMap *request_headers_;
  ResponseHeaderMap *response_headers_;
  
  Buffer::Instance *request_buffer_;
  Buffer::Instance *response_buffer_;

  std::optional<AppnetCoroutine> appnet_coroutine_;
  ResponseMessagePtr external_response_;
  std::optional<Awaiter*> http_awaiter_;

  std::mutex mutex_; // for onSuccess and decode/encode synchronization

  bool req_appnet_blocked_ = false;
  bool resp_appnet_blocked_ = false;
  
  bool in_decoding_or_encoding_ = false;

  void startRequestAppnetNoCoroutine();
  void startResponseAppnetNoCorotine();
  bool sendWebdisRequest(const std::string path, Callbacks& callback);
  bool sendHttpRequest(const std::string cluster_name, const std::string path, Callbacks &callback);
};

class EmptyCallback : public Http::AsyncClient::Callbacks {
public:
  void onSuccess(const Http::AsyncClient::Request&, Http::ResponseMessagePtr&&) override {}
  void onFailure(const Http::AsyncClient::Request&, Http::AsyncClient::FailureReason) override {}
  void onBeforeFinalizeUpstreamSpan(Tracing::Span&, const Http::ResponseHeaderMap*) override {}
};



using AppnetFilterConfigSharedPtr = std::shared_ptr<AppnetFilterConfig>;

inline EmptyCallback EMPTY_CALLBACK{};

class AppNetWeakSyncTimer : public Logger::Loggable<Logger::Id::filter> {
public:
  AppNetWeakSyncTimer(AppnetFilterConfigSharedPtr config, Event::Dispatcher& dispatcher, std::chrono::milliseconds timeout) 
    : config_(config), tick_timer_(dispatcher.createTimer([this]() -> void { onTick(); })), timeout_(timeout) {
    onTick();
  }
private:
  AppnetFilterConfigSharedPtr config_;
  Event::TimerPtr tick_timer_;
  std::chrono::milliseconds timeout_;

  
  void onTick();

  bool sendWebdisRequest(const std::string path, Http::AsyncClient::Callbacks &callback = EMPTY_CALLBACK) {
    auto cluster = this->config_->ctx_.serverFactoryContext().clusterManager().getThreadLocalCluster("webdis-service-servercachestrong");
    if (!cluster) {
    ENVOY_LOG(info, "webdis-service-servercachestrong not found");
    assert(0);
    return false;
    }
    Http::RequestMessagePtr request = std::make_unique<Http::RequestMessageImpl>();

    request->headers().setMethod(Http::Headers::get().MethodValues.Get);
    request->headers().setHost("localhost:7379");
    ENVOY_LOG(info, "[AppNet Filter OnTick] webdis requesting path={}", path);
    request->headers().setPath(path);
    auto options = Http::AsyncClient::RequestOptions()
            .setTimeout(std::chrono::milliseconds(1000))
            .setSampled(absl::nullopt);
    cluster->httpAsyncClient().send(std::move(request), callback, options);
    return true;
  }
};

} // namespace appnetservercachestrong

} // namespace Http
} // namespace Envoy
