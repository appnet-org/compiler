#include <string>

#include "envoy/registry/registry.h"
#include "envoy/server/filter_config.h"

#include "appnet_filter/appnet_filter.pb.h"
#include "appnet_filter/appnet_filter.pb.validate.h"
#include "appnet_filter.h"

namespace Envoy {
namespace Server {
namespace Configuration {

class HttpSampleFilterConfigFactory : public NamedHttpFilterConfigFactory {
public:
  absl::StatusOr<Http::FilterFactoryCb> createFilterFactoryFromProto(const Protobuf::Message& proto_config,
                                                     const std::string&,
                                                     FactoryContext& context) override {

    return createFilter(Envoy::MessageUtil::downcastAndValidate<const sample::FilterConfig&>(
                            proto_config, context.messageValidationVisitor()),
                        context);
  }

  /**
   *  Return the Protobuf Message that represents your config incase you have config proto
   */
  ProtobufTypes::MessagePtr createEmptyConfigProto() override {
    return ProtobufTypes::MessagePtr{new sample::FilterConfig()};
  }

  std::string name() const override { return "sample"; }

private:
  Http::FilterFactoryCb createFilter(const sample::FilterConfig& proto_config, FactoryContext &factory_ctx) {
    Http::AppnetFilterConfigSharedPtr config =
        std::make_shared<Http::AppnetFilterConfig>(
            Http::AppnetFilterConfig(proto_config, factory_ctx));

    return [config](Http::FilterChainFactoryCallbacks& callbacks) -> void {
      auto filter = new Http::AppnetFilter(config);
      callbacks.addStreamFilter(Http::StreamFilterSharedPtr{filter});
    };
  }
};

/**
 * Static registration for this sample filter. @see RegisterFactory.
 */
static Registry::RegisterFactory<HttpSampleFilterConfigFactory, NamedHttpFilterConfigFactory>
    register_;

} // namespace Configuration
} // namespace Server
} // namespace Envoy
