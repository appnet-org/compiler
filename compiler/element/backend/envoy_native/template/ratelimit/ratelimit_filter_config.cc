#include <string>

#include "envoy/registry/registry.h"
#include "envoy/server/filter_config.h"

#include "ratelimit/ratelimit_filter.pb.h"
#include "ratelimit/ratelimit_filter.pb.validate.h"
#include "ratelimit_filter.h"

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
    Http::RatelimitFilterConfigSharedPtr config =
        std::make_shared<Http::RatelimitFilterConfig>(
            Http::RatelimitFilterConfig(proto_config, factory_ctx));

    return [config](Http::FilterChainFactoryCallbacks& callbacks) -> void {
      auto filter = new Http::RatelimitFilter(config);
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
