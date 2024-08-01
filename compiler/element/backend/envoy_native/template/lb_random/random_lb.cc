#include "random_lb.h"

#include <netinet/in.h>
#include "envoy/server/factory_context.h"


namespace Envoy {
namespace Upstream {

HostConstSharedPtr MyRandomLoadBalancer::peekAnotherHost(LoadBalancerContext* context) {
  if (tooManyPreconnects(stashed_random_.size(), total_healthy_hosts_)) {
    return nullptr;
  }
  ENVOY_LOG(info, "peekAnotherHost()");
  return peekOrChoose(context, true);
}

HostConstSharedPtr MyRandomLoadBalancer::chooseHostOnce(LoadBalancerContext* context) {
  ENVOY_LOG(info, "chooseHostOnce()");
  return peekOrChoose(context, false);
}

HostConstSharedPtr MyRandomLoadBalancer::peekOrChoose(LoadBalancerContext* context, bool peek) {
  // print the header
  auto header = context->downstreamHeaders();

  // make sure the header is not null
  if (header == nullptr) {
    ENVOY_LOG(info, "header is null");
    return nullptr;
  }

  // make sure header exists
  if (header->get(Http::LowerCaseString("appnet_route_to")).empty()) {
    ENVOY_LOG(info, "header not found");
    return nullptr;
  }

  auto route_to =  header->get(Http::LowerCaseString("appnet_route_to"))[0]->value().getStringView();

  // cast it into index
  int route_to_idx = std::stoi(std::string(route_to));

  ENVOY_LOG(info, "get routing direction from filter: {}", route_to_idx);

  ENVOY_LOG(info, "peekOrChoose()");
  uint64_t random_hash = random(peek);
  const absl::optional<HostsSource> hosts_source = hostSourceToUse(context, random_hash);
  if (!hosts_source) {
    return nullptr;
  }

  const HostVector& hosts_to_use = hostSourceToHosts(*hosts_source);
  if (hosts_to_use.empty()) {
    return nullptr;
  }

  assert(0 <= route_to_idx && route_to_idx < static_cast<int>(hosts_to_use.size()));

  return hosts_to_use[route_to_idx];
}

} // namespace Upstream
} // namespace Envoy
