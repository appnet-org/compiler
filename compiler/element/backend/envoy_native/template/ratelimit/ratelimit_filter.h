#pragma once

#include <string>
#include <mutex>
#include <chrono>
#include <algorithm>

#include "envoy/server/factory_context.h"
#include "source/extensions/filters/http/common/pass_through_filter.h"

#include "ratelimit/ratelimit_filter.pb.h"

namespace Envoy {
namespace Http {

class RatelimitFilterConfig {
public:
  RatelimitFilterConfig(const sample::FilterConfig& proto_config, Envoy::Server::Configuration::FactoryContext &context);
  Envoy::Server::Configuration::FactoryContext &ctx_;
private:
};

using RatelimitFilterConfigSharedPtr = std::shared_ptr<RatelimitFilterConfig>;

class RatelimitFilter 
      : public PassThroughFilter, 
        public Http::AsyncClient::Callbacks, 
        Logger::Loggable<Logger::Id::filter> {
public:
  RatelimitFilter(RatelimitFilterConfigSharedPtr);
  ~RatelimitFilter();

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

  const RatelimitFilterConfigSharedPtr config_;

  // Http::AsyncClient::Callbacks
  void onSuccess(const Http::AsyncClient::Request&, Http::ResponseMessagePtr&& message) override;
  void onFailure(const Http::AsyncClient::Request&, Http::AsyncClient::FailureReason) override;
  void onBeforeFinalizeUpstreamSpan(Tracing::Span&, const Http::ResponseHeaderMap*) override;

private:
  StreamDecoderFilterCallbacks* decoder_callbacks_;
  StreamEncoderFilterCallbacks* encoder_callbacks_;
  Callbacks *empty_callback_;

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
