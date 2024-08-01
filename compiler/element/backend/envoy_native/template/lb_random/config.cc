#include "config.h"

#include "random_lb.h"

namespace Envoy {
namespace Extensions {
namespace LoadBalancingPolices {
namespace MyRandom {

TypedRandomLbConfig::TypedRandomLbConfig(const RandomLbProto& lb_config) : lb_config_(lb_config) {}

Upstream::LoadBalancerPtr RandomCreator::operator()(
    Upstream::LoadBalancerParams params, OptRef<const Upstream::LoadBalancerConfig> lb_config,
    const Upstream::ClusterInfo& cluster_info, const Upstream::PrioritySet&,
    Runtime::Loader& runtime, Envoy::Random::RandomGenerator& random, TimeSource&) {
  
  (void) lb_config;
  // std::cerr << "=============================================================================================" << std::endl;
  // const auto typed_lb_config = dynamic_cast<const TypedRandomLbConfig*>(lb_config.ptr());

  // if (typed_lb_config != nullptr) {
  //   return std::make_unique<Upstream::MyRandomLoadBalancer>(
  //       params.priority_set, params.local_priority_set, cluster_info.lbStats(), runtime, random,
  //       PROTOBUF_PERCENT_TO_ROUNDED_INTEGER_OR_DEFAULT(cluster_info.lbConfig(),
  //                                                      healthy_panic_threshold, 100, 50),
  //       typed_lb_config->lb_config_);
  // } else {
    return std::make_unique<Upstream::MyRandomLoadBalancer>(
        params.priority_set, params.local_priority_set, cluster_info.lbStats(), runtime, random,
        cluster_info.lbConfig());
  // }
}

/**
 * Static registration for the Factory. @see RegisterFactory.
 */
REGISTER_FACTORY(Factory, Upstream::TypedLoadBalancerFactory);

} // namespace Random
} // namespace LoadBalancingPolices
} // namespace Extensions
} // namespace Envoy
