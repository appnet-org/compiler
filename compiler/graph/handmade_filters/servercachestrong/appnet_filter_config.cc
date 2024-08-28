#include <string>

#include "envoy/registry/registry.h"
#include "envoy/server/filter_config.h"

#include "source/extensions/filters/http/servercachestrong/appnet_filter.pb.h"
#include "source/extensions/filters/http/servercachestrong/appnet_filter.pb.validate.h"
#include "appnet_filter.h"

namespace Envoy {
namespace Server {
namespace Configuration {

namespace appnetservercachestrong {

using namespace Envoy::Http::appnetservercachestrong;

class AppnetFilterConfigFactory : public NamedHttpFilterConfigFactory {
public:
  absl::StatusOr<Http::FilterFactoryCb> createFilterFactoryFromProto(const Protobuf::Message& proto_config,
                                                     const std::string&,
                                                     FactoryContext& context) override {

    return createFilter(Envoy::MessageUtil::downcastAndValidate<const ::appnetservercachestrong::FilterConfig&>(
                            proto_config, context.messageValidationVisitor()),
                        context);
  }

  /**
   *  Return the Protobuf Message that represents your config incase you have config proto
   */
  ProtobufTypes::MessagePtr createEmptyConfigProto() override {
    return ProtobufTypes::MessagePtr{new ::appnetservercachestrong::FilterConfig()};
  }

  std::string name() const override { return "appnetservercachestrong"; }

private:
  Http::FilterFactoryCb createFilter(const ::appnetservercachestrong::FilterConfig& proto_config, FactoryContext &factory_ctx) {
    AppnetFilterConfigSharedPtr config =
        std::make_shared<AppnetFilterConfig>(
            AppnetFilterConfig(proto_config, factory_ctx));

    // We leak it intentionally.
    auto _ = new AppNetWeakSyncTimer(
        config,
        factory_ctx.serverFactoryContext().mainThreadDispatcher(), 
        std::chrono::milliseconds(1000));
      
    // make compiler happy
    (void)_;

    return [config](Http::FilterChainFactoryCallbacks& callbacks) -> void {
      auto filter = new AppnetFilter(config);
      callbacks.addStreamFilter(Http::StreamFilterSharedPtr{filter});
    };
  }
};

/**
 * Static registration for this sample filter. @see RegisterFactory.
 */
static Registry::RegisterFactory<AppnetFilterConfigFactory, NamedHttpFilterConfigFactory>
    register_;

} // namespace appnetservercachestrong
} // namespace Configuration
} // namespace Server
} // namespace Envoy
