#include <netinet/in.h>
#include <string>
#include <chrono>
#include <mutex>
#include "thirdparty/json.hpp"
#include "thirdparty/base64.h"

#include "ratelimit_filter.h"
#include "ratelimit/echo.pb.h"

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

RatelimitFilterConfig::RatelimitFilterConfig(
  const sample::FilterConfig&, Envoy::Server::Configuration::FactoryContext &ctx)
  : ctx_(ctx) { }

RatelimitFilter::RatelimitFilter(RatelimitFilterConfigSharedPtr config)
  : config_(config), empty_callback_(new EmptyCallback{}) {

  std::lock_guard<std::mutex> guard(init_lock);
  if (!init) {
    init = true;

    // !APPNET_INIT
  }
}

RatelimitFilter::~RatelimitFilter() {}

void RatelimitFilter::onDestroy() {}

FilterHeadersStatus RatelimitFilter::decodeHeaders(RequestHeaderMap &, bool) {
  return FilterHeadersStatus::StopIteration;
}

FilterDataStatus RatelimitFilter::decodeData(Buffer::Instance &buf, bool end_of_stream) {
  if (!end_of_stream) 
    return FilterDataStatus::Continue;
  auto &stream_info = this->decoder_callbacks_->streamInfo();
  auto cluster_info = stream_info.upstreamClusterInfo();
  if (cluster_info == nullptr) {
    ENVOY_LOG(info, "[Ratelimit Filter] cluster_info is null");
    PANIC("cluster_info is null");
  }
  ENVOY_LOG(info, "[Ratelimit Filter] cluster info: {}", cluster_info->get()->name());
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
  for (auto host : host_list) {
    ENVOY_LOG(info, "host address: {}", host->address()->asString());
  }
  auto map = this->decoder_callbacks_->requestHeaders();
  int route_idx = 0
  map->addCopy(LowerCaseString("appnet_route_to"), route_idx);

  return FilterDataStatus::Continue;
}

void RatelimitFilter::setDecoderFilterCallbacks(StreamDecoderFilterCallbacks& callbacks) {
  decoder_callbacks_ = &callbacks;
}

void RatelimitFilter::setEncoderFilterCallbacks(StreamEncoderFilterCallbacks& callbacks) {
  encoder_callbacks_ = &callbacks;
}

FilterHeadersStatus RatelimitFilter::encodeHeaders(ResponseHeaderMap& headers, bool) {
  ENVOY_LOG(info, "[Ratelimit Filter] encodeHeaders {}", headers);
  return FilterHeadersStatus::Continue;
}

FilterDataStatus RatelimitFilter::encodeData(Buffer::Instance &, bool) {
  return FilterDataStatus::Continue;
}

void RatelimitFilter::onSuccess(const Http::AsyncClient::Request&,
                 Http::ResponseMessagePtr&&) {
}

void RatelimitFilter::onFailure(const Http::AsyncClient::Request&,
                 Http::AsyncClient::FailureReason) {
}

void RatelimitFilter::onBeforeFinalizeUpstreamSpan(Tracing::Span&,
                          const Http::ResponseHeaderMap*) {
  ENVOY_LOG(info, "[Ratelimit Filter] ExternalResponseCallback onBeforeFinalizeUpstreamSpan");
}

bool RatelimitFilter::sendWebdisRequest(const std::string path, Callbacks &callback) {
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

} // namespace Http
} // namespace Envoy
