#include <netinet/in.h>
#include <string>
#include <chrono>
#include <mutex>
#include "thirdparty/json.hpp"
#include "thirdparty/base64.h"

#include "appnet_filter.h"
#include "appnet_filter/echo.pb.h"

#include "envoy/server/filter_config.h"
#include "google/protobuf/extension_set.h"
#include "source/common/http/utility.h"
#include "source/common/http/message_impl.h" 
#include "envoy/upstream/resource_manager.h"


namespace Envoy {
namespace Http {


std::mutex init_lock;
bool init = false;
// !APPNET_STATE

AppnetFilterConfig::AppnetFilterConfig(
  const sample::FilterConfig&, Envoy::Server::Configuration::FactoryContext &ctx)
  : ctx_(ctx) { }

AppnetFilter::AppnetFilter(AppnetFilterConfigSharedPtr config)
  : config_(config), empty_callback_(new EmptyCallback{}) {

  std::lock_guard<std::mutex> guard(init_lock);
  if (!init) {
    init = true;

    // !APPNET_INIT
  }
}

AppnetFilter::~AppnetFilter() {}

void AppnetFilter::onDestroy() {}

FilterHeadersStatus AppnetFilter::decodeHeaders(RequestHeaderMap & headers, bool) {
  ENVOY_LOG(info, "[Appnet Filter] decodeHeaders {}", headers);
  this->request_headers_ = &headers;
  return FilterHeadersStatus::StopIteration;
}

FilterDataStatus AppnetFilter::decodeData(Buffer::Instance &data, bool end_of_stream) {
  if (!end_of_stream) 
    return FilterDataStatus::Continue;

  ENVOY_LOG(info, "[Appnet Filter] decodeData");
  this->request_buffer_ = &data;
  this->appnet_coroutine_.emplace(this->startRequestAppnet());
  this->appnet_coroutine_.value().handle_.resume(); // the coroutine will be started here.
  return FilterDataStatus::StopIterationAndBuffer;
}

void AppnetFilter::setDecoderFilterCallbacks(StreamDecoderFilterCallbacks& callbacks) {
  decoder_callbacks_ = &callbacks;
}

void AppnetFilter::setEncoderFilterCallbacks(StreamEncoderFilterCallbacks& callbacks) {
  encoder_callbacks_ = &callbacks;
}

FilterHeadersStatus AppnetFilter::encodeHeaders(ResponseHeaderMap& headers, bool) {
  ENVOY_LOG(info, "[Appnet Filter] encodeHeaders {}", headers);
  this->response_headers_ = &headers;
  return FilterHeadersStatus::StopIteration;
}

FilterDataStatus AppnetFilter::encodeData(Buffer::Instance &data, bool end_of_stream) {
  if (!end_of_stream) 
    return FilterDataStatus::Continue;

  ENVOY_LOG(info, "[Appnet Filter] encodeData");
  this->response_buffer_ = &data;
  this->appnet_coroutine_.emplace(this->startResponseAppnet());
  this->appnet_coroutine_.value().handle_.resume(); // the coroutine will be started here.
  return FilterDataStatus::StopIterationAndBuffer;
}

// For now, it's dedicated to the webdis response.
void AppnetFilter::onSuccess(const Http::AsyncClient::Request&,
                 Http::ResponseMessagePtr&& message) {

  // ENVOY_LOG(info, "[Appnet Filter] ExternalResponseCallback onSuccess");
  this->external_response_ = std::move(message);
  assert(message.get() == nullptr);
  // ENVOY_LOG(info, "[Appnet Filter] ExternalResponseCallback onSuccess (second step)");
  assert(this->webdis_awaiter_.has_value());
  this->webdis_awaiter_.value()->i_am_ready();
  // ENVOY_LOG(info, "[Appnet Filter] ExternalResponseCallback onSuccess (3rd step)");
}

void AppnetFilter::onFailure(const Http::AsyncClient::Request&,
                 Http::AsyncClient::FailureReason) {
  ENVOY_LOG(info, "[Appnet Filter] ExternalResponseCallback onFailure");
  assert(0);
}

void AppnetFilter::onBeforeFinalizeUpstreamSpan(Tracing::Span&,
                          const Http::ResponseHeaderMap*) {
  ENVOY_LOG(info, "[Appnet Filter] ExternalResponseCallback onBeforeFinalizeUpstreamSpan");
}

bool AppnetFilter::sendWebdisRequest(const std::string path, Callbacks &callback) {
  auto cluster = this->config_->ctx_.serverFactoryContext().clusterManager().getThreadLocalCluster("webdis_cluster");
  if (!cluster) {
    ENVOY_LOG(info, "webdis_cluster not found");
    assert(0);
    return false;
  }
  Http::RequestMessagePtr request = std::make_unique<Http::RequestMessageImpl>();

  request->headers().setMethod(Http::Headers::get().MethodValues.Get);
  request->headers().setHost("localhost:7379");
  ENVOY_LOG(info, "[Ratelimit Filter] webdis requesting path={}", path);
  request->headers().setPath(path);
  auto options = Http::AsyncClient::RequestOptions()
           .setTimeout(std::chrono::milliseconds(1000))
           .setSampled(absl::nullopt);
  cluster->httpAsyncClient().send(std::move(request), callback, options);
  return true;
}

AppnetCoroutine AppnetFilter::startRequestAppnet() {
  // !APPNET_REQUEST

  co_return;
}


AppnetCoroutine AppnetFilter::startResponseAppnet() {
  // !APPNET_RESPONSE

  co_return;
}

} // namespace Http
} // namespace Envoy
