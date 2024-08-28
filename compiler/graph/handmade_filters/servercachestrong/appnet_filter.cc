#include <netinet/in.h>
#include <string>
#include <random>
#include <chrono>
#include <mutex>
#include <algorithm>

#include "appnet_filter.h"
#include "source/extensions/filters/http/servercachestrong/echo.pb.h"

#include "envoy/server/filter_config.h"
#include "google/protobuf/extension_set.h"
#include "source/common/http/utility.h"
#include "source/common/http/message_impl.h"
#include "envoy/upstream/resource_manager.h"
#include "thirdparty/json.hpp"

namespace Envoy {
namespace Http {

namespace appnetservercachestrong {

#include "thirdparty/base64.h"

template <typename A, typename B> auto my_min(A a, B b) { return a < b ? a : b; }

template <typename A, typename B> auto my_max(A a, B b) { return a > b ? a : b; }

template <typename K, typename V>
std::optional<V> map_get_opt(const std::map<K, V>& m, const K& key) {
  auto it = m.find(key);
  if (it == m.end()) {
    return std::nullopt;
  }
  return std::make_optional(it->second);
}

std::string get_rpc_field(const ::appnetservercachestrong::Msg& rpc, const std::string& field) {
  if (field == "body") {
    return rpc.body();
  } else {
    throw std::runtime_error("Unknown field: " + field);
  }
}

void set_rpc_field(::appnetservercachestrong::Msg& rpc, const std::string& field,
                   const std::string& value) {
  if (field == "body") {
    rpc.set_body(value);
  } else {
    throw std::runtime_error("Unknown field: " + field);
  }
}

void replace_payload(Buffer::Instance* data, ::appnetservercachestrong::Msg& rpc) {
  std::string serialized;
  rpc.SerializeToString(&serialized);

  // drain the original data
  data->drain(data->length());
  // fill 0x00 and then the length of new message
  std::vector<uint8_t> new_data(5 + serialized.size());
  new_data[0] = 0x00;
  uint32_t len = serialized.size();
  *reinterpret_cast<uint32_t*>(&new_data[1]) = ntohl(len);
  std::copy(serialized.begin(), serialized.end(), new_data.begin() + 5);
  data->add(new_data.data(), new_data.size());
}

std::mutex global_state_lock;

bool init = false;
std::map<std::string, std::string> cache = {};

AppnetFilterConfig::AppnetFilterConfig(const ::appnetservercachestrong::FilterConfig&,
                                       Envoy::Server::Configuration::FactoryContext& ctx)
    : ctx_(ctx) {}

AppnetFilter::AppnetFilter(AppnetFilterConfigSharedPtr config)
    : config_(config), empty_callback_(new EmptyCallback{}) {

  std::lock_guard<std::mutex> guard(global_state_lock);
  if (!init) {
    init = true;

    // stmt MethodCall
    std::string temp_1 = "";
    temp_1 = "bomb";
    std::string temp_2 = "";
    temp_2 = "bomb";
    std::string temp_3 = "";
    temp_3 = "/SET/" + temp_1 + "/" + base64_encode(temp_2, true);
    {
      ENVOY_LOG(warn, "[AppNet Filter] Non-Blocking Webdis Request");
      this->sendWebdisRequest(temp_3, *empty_callback_);
    }
  }
}

AppnetFilter::~AppnetFilter() { ENVOY_LOG(warn, "[Appnet Filter] ~AppnetFilter"); }

void AppnetFilter::onDestroy() {}

FilterHeadersStatus AppnetFilter::decodeHeaders(RequestHeaderMap& headers, bool) {
  std::cerr << "decodeHeaders" << std::endl;
  ENVOY_LOG(warn, "[Appnet Filter] decodeHeaders headers={}, this={}", headers,
            static_cast<void*>(this));
  this->request_headers_ = &headers;
  return FilterHeadersStatus::StopIteration;
}

FilterDataStatus AppnetFilter::decodeData(Buffer::Instance& data, bool end_of_stream) {
  if (!end_of_stream)
    return FilterDataStatus::Continue;

  ENVOY_LOG(warn, "[Appnet Filter] decodeData this={}, end_of_stream={}", static_cast<void*>(this),
            end_of_stream);
  this->request_buffer_ = &data;
  this->in_decoding_or_encoding_ = true;
  this->startRequestAppnetNoCoroutine();

  if (this->req_appnet_blocked_) {
    ENVOY_LOG(warn, "[Appnet Filter] cached");
    return FilterDataStatus::StopIterationNoBuffer;
  } else {
    ENVOY_LOG(warn, "[Appnet Filter] not cached yet");
    return FilterDataStatus::Continue;
  }
}

void AppnetFilter::setDecoderFilterCallbacks(StreamDecoderFilterCallbacks& callbacks) {
  decoder_callbacks_ = &callbacks;
}

void AppnetFilter::setEncoderFilterCallbacks(StreamEncoderFilterCallbacks& callbacks) {
  encoder_callbacks_ = &callbacks;
}

FilterHeadersStatus AppnetFilter::encodeHeaders(ResponseHeaderMap& headers, bool) {
  ENVOY_LOG(warn, "[Appnet Filter] encodeHeaders this={}, headers={}", headers,
            static_cast<void*>(this), headers);
  this->response_headers_ = &headers;
  if (headers.get(LowerCaseString("appnet-local-reply")).empty() == false) {
    ENVOY_LOG(warn, "[Appnet Filter] encodeHeaders skip local reply");
    // We don't process the response if the request is blocked.
    return FilterHeadersStatus::Continue;
  }
  return FilterHeadersStatus::StopIteration;
}

FilterDataStatus AppnetFilter::encodeData(Buffer::Instance& data, bool end_of_stream) {
  if (this->req_appnet_blocked_) {
    // We don't process the response if the request is blocked.
    return FilterDataStatus::Continue;
  }

  ENVOY_LOG(warn, "[Appnet Filter] encodeData this={}, end_of_stream={}", static_cast<void*>(this),
            end_of_stream);
  this->response_buffer_ = &data;

  this->in_decoding_or_encoding_ = true;
  this->startResponseAppnetNoCorotine();
  return FilterDataStatus::Continue;
}

// For now, it's dedicated to the webdis response.
void AppnetFilter::onSuccess(const Http::AsyncClient::Request&,
                             Http::ResponseMessagePtr&& message) {
  ENVOY_LOG(warn, "[Appnet Filter] ExternalResponseCallback onSuccess");
  this->external_response_ = std::move(message);
  assert(message.get() == nullptr);
  this->in_decoding_or_encoding_ = false;

  if (this->external_response_ == nullptr) {
    ENVOY_LOG(warn, "ENVOY_LOG(error, \"[AppNet Filter] Webdis Request Failed\");");
    ENVOY_LOG(error, "[AppNet Filter] Webdis Request Failed");
    ENVOY_LOG(warn, "std::terminate();");
    std::terminate();
  }
  ENVOY_LOG(warn, "std::string response_str = this->external_response_->bodyAsString();");
  std::string response_str = this->external_response_->bodyAsString();
  ENVOY_LOG(warn, "[AppNet Filter] Webdis Response: {}", response_str);
  ENVOY_LOG(warn, "nlohmann::json j = nlohmann::json::parse(response_str);");
  nlohmann::json j = nlohmann::json::parse(response_str);


  ENVOY_LOG(warn, "std::optional<std::string> temp_7 = std::nullopt;");
  std::optional<std::string> temp_7 = std::nullopt;
  if (j.contains("GET") && j["GET"].is_null() == false) {
    ENVOY_LOG(warn, "temp_7.emplace(base64_decode(j[\"GET\"], false));");
    temp_7.emplace(base64_decode(j["GET"], false));
  }
  ENVOY_LOG(warn, "std::optional<std::string> res = temp_7;");
  std::optional<std::string> res = temp_7;
  if (res.has_value()) {
    ENVOY_LOG(warn, "std::string name = \"\";");
    std::string name = "";
    ENVOY_LOG(warn, "name = res.value();");
    name = res.value();
    if (name == "cached") {
      ENVOY_LOG(warn, "// stmt Send");
      // stmt Send
      std::function<void(ResponseHeaderMap & headers)> modify_headers = [](ResponseHeaderMap&
                                                                                headers) {
        ENVOY_LOG(
            warn,
            "headers.addCopy(LowerCaseString(\"appnet-local-reply\"), \"appnetservercachestrong\");");
        headers.addCopy(LowerCaseString("appnet-local-reply"), "appnetservercachestrong");
      };
      ENVOY_LOG(warn, "this->req_appnet_blocked_ = true;");
      this->req_appnet_blocked_ = true;
      this->decoder_callbacks_->sendLocalReply(Http::Code::Forbidden, "cache", modify_headers,
                                                absl::nullopt, "");
      return;
    } else {
      ENVOY_LOG(warn, "// stmt Send");
      // stmt Send
      std::function<void(ResponseHeaderMap & headers)> modify_headers = [](ResponseHeaderMap&
                                                                                headers) {
        ENVOY_LOG(
            warn,
            "headers.addCopy(LowerCaseString(\"appnet-local-reply\"), \"appnetservercachestrong\");");
        headers.addCopy(LowerCaseString("appnet-local-reply"), "appnetservercachestrong");
      };
      ENVOY_LOG(warn, "this->req_appnet_blocked_ = true;");
      this->req_appnet_blocked_ = true;
      this->decoder_callbacks_->sendLocalReply(Http::Code::Forbidden, "bomb", modify_headers,
                                                absl::nullopt, "");
      return;
    }
  } else {
    ENVOY_LOG(warn, "// stmt Send");
    // stmt Send
    if (this->in_decoding_or_encoding_ == false) {
      ENVOY_LOG(warn, "this->decoder_callbacks_->continueDecoding();");
      this->decoder_callbacks_->continueDecoding();
    }
    return;
  }
}

void AppnetFilter::onFailure(const Http::AsyncClient::Request&, Http::AsyncClient::FailureReason) {
  ENVOY_LOG(warn, "[Appnet Filter] ExternalResponseCallback onFailure");
  assert(0);
}

void AppnetFilter::onBeforeFinalizeUpstreamSpan(Tracing::Span&, const Http::ResponseHeaderMap*) {
  ENVOY_LOG(warn, "[Appnet Filter] ExternalResponseCallback onBeforeFinalizeUpstreamSpan");
}

bool AppnetFilter::sendWebdisRequest(const std::string path, Callbacks& callback) {
  return this->sendHttpRequest("webdis-service-servercachestrong", path, callback);
}

bool AppnetFilter::sendHttpRequest(const std::string cluster_name, const std::string path,
                                   Callbacks& callback) {
  auto cluster = this->config_->ctx_.serverFactoryContext().clusterManager().getThreadLocalCluster(
      cluster_name);
  if (!cluster) {
    ENVOY_LOG(warn, "cluster {} not found", cluster_name);
    assert(0);
    return false;
  }
  Http::RequestMessagePtr request = std::make_unique<Http::RequestMessageImpl>();

  request->headers().setMethod(Http::Headers::get().MethodValues.Get);
  request->headers().setHost("localhost:7379");
  ENVOY_LOG(warn, "[AppNet Filter] requesting path={}", path);
  request->headers().setPath(path);
  auto options = Http::AsyncClient::RequestOptions()
                     .setTimeout(std::chrono::milliseconds(1000))
                     .setSampled(absl::nullopt);
  cluster->httpAsyncClient().send(std::move(request), callback, options);
  return true;
}



void AppnetFilter::startRequestAppnetNoCoroutine() {
  this->setRoutingEndpoint(0);

  ENVOY_LOG(warn, "std::lock_guard<std::mutex> lock(global_state_lock);");
  std::lock_guard<std::mutex> lock(global_state_lock);
  ENVOY_LOG(warn, "::appnetservercachestrong::Msg rpc;");
  ::appnetservercachestrong::Msg rpc;
  ENVOY_LOG(warn, "std::vector<uint8_t> temp_4(this->request_buffer_->length());");
  std::vector<uint8_t> temp_4(this->request_buffer_->length());
  ENVOY_LOG(warn,
            "this->request_buffer_->copyOut(0, this->request_buffer_->length(), temp_4.data());");
  this->request_buffer_->copyOut(0, this->request_buffer_->length(), temp_4.data());
  ENVOY_LOG(warn, "rpc.ParseFromArray(temp_4.data() + 5, temp_4.size() - 5);");
  rpc.ParseFromArray(temp_4.data() + 5, temp_4.size() - 5);
  ENVOY_LOG(warn, "// stmt Assign");
  // stmt Assign
  ENVOY_LOG(warn, "std::string temp_5 = \"\";");
  std::string temp_5 = "";
  ENVOY_LOG(warn, "temp_5 = \"body\";");
  temp_5 = "body";
  ENVOY_LOG(warn, "std::string temp_6 = \"\";");
  std::string temp_6 = "";
  ENVOY_LOG(warn, "temp_6 = get_rpc_field(rpc, temp_5);");
  temp_6 = get_rpc_field(rpc, temp_5);
  {
    ENVOY_LOG(warn, "std::string temp_8 = \"\";");
    std::string temp_8 = "";
    ENVOY_LOG(warn, "temp_8 = \"/GET/\" + temp_6;");
    temp_8 = "/GET/" + temp_6;
    {
      ENVOY_LOG(warn, "this->external_response_ = nullptr;");
      this->external_response_ = nullptr;
      ENVOY_LOG(warn, "this->sendHttpRequest(\"webdis-service-servercachestrong\", temp_8, *this);");
      this->sendHttpRequest("webdis-service-servercachestrong", temp_8, *this);
      ENVOY_LOG(warn, "[AppNet Filter] Blocking HTTP Request Sent");
    }
  }
}


void AppnetFilter::startResponseAppnetNoCorotine() {
  {
      // resp header begin.
  } // resp header end.
  { // resp body begin.
    ENVOY_LOG(warn, "std::lock_guard<std::mutex> lock(global_state_lock);");
    std::lock_guard<std::mutex> lock(global_state_lock);
    ENVOY_LOG(warn, "::appnetservercachestrong::Msg rpc;");
    ::appnetservercachestrong::Msg rpc;
    ENVOY_LOG(warn, "std::vector<uint8_t> temp_9(this->response_buffer_->length());");
    std::vector<uint8_t> temp_9(this->response_buffer_->length());
    ENVOY_LOG(
        warn,
        "this->response_buffer_->copyOut(0, this->response_buffer_->length(), temp_9.data());");
    this->response_buffer_->copyOut(0, this->response_buffer_->length(), temp_9.data());
    ENVOY_LOG(warn, "rpc.ParseFromArray(temp_9.data() + 5, temp_9.size() - 5);");
    rpc.ParseFromArray(temp_9.data() + 5, temp_9.size() - 5);
    ENVOY_LOG(warn, "// stmt Assign");
    // stmt Assign
    ENVOY_LOG(warn, "std::string temp_10 = \"\";");
    std::string temp_10 = "";
    ENVOY_LOG(warn, "temp_10 = \"body\";");
    temp_10 = "body";
    ENVOY_LOG(warn, "std::string temp_11 = \"\";");
    std::string temp_11 = "";
    ENVOY_LOG(warn, "temp_11 = get_rpc_field(rpc, temp_10);");
    temp_11 = get_rpc_field(rpc, temp_10);
    ENVOY_LOG(warn, "std::string key = temp_11;");
    std::string key = temp_11;
    ENVOY_LOG(warn, "// stmt MethodCall");
    // stmt MethodCall
    ENVOY_LOG(warn, "std::string temp_12 = \"\";");
    std::string temp_12 = "";
    ENVOY_LOG(warn, "temp_12 = \"cached\";");
    temp_12 = "cached";
    ENVOY_LOG(warn, "std::string temp_13 = \"\";");
    std::string temp_13 = "";
    ENVOY_LOG(warn, "temp_13 = \"/SET/\" + key + \"/\" + base64_encode(temp_12, true);");
    temp_13 = "/SET/" + key + "/" + base64_encode(temp_12, true);
    {
      ENVOY_LOG(warn, "ENVOY_LOG(warn, \"[AppNet Filter] Non-Blocking Webdis Request\");");
      ENVOY_LOG(warn, "[AppNet Filter] Non-Blocking Webdis Request");
      ENVOY_LOG(warn, "this->sendWebdisRequest(temp_13, *empty_callback_);");
      this->sendWebdisRequest(temp_13, *empty_callback_);
    }
    ENVOY_LOG(warn, "return;");
    return;
  } // resp body end.

  return;
}

void AppNetWeakSyncTimer::onTick() {
  // ENVOY_LOG(warn, "[AppNet Filter] onTick");

  this->tick_timer_->enableTimer(this->timeout_);
}

} // namespace appnetservercachestrong

} // namespace Http
} // namespace Envoy
