load(
    "@envoy//bazel:envoy_build_system.bzl",
    "envoy_cc_extension",
    "envoy_cc_library",
    "envoy_extension_package",
    "envoy_cc_binary",
)

licenses(["notice"])  # Apache 2

load("@envoy_api//bazel:api_build_system.bzl", "api_proto_package")

api_proto_package()

package(default_visibility = ["//visibility:public"])

envoy_cc_library(
    name = "random_lb_lib",
    srcs = ["config.cc", "random_lb.cc"],
    hdrs = ["config.h", "random_lb.h"],
    repository = "@envoy",
    deps = [
        ":pkg_cc_proto",
        "@envoy//source/common/http:utility_lib",
        "@envoy//source/extensions/load_balancing_policies/common:load_balancer_lib",
        "@envoy//source/common/common:minimal_logger_lib",
        "@envoy//source/common/upstream:load_balancer_context_base_lib",
        "@envoy//source/extensions/load_balancing_policies/common:factory_base",
        # "@envoy_api//envoy/extensions/load_balancing_policies/random/v3:pkg_cc_proto",
    ],
)


# envoy_cc_extension(
#     name = "config",
#     srcs = ["config.cc"],
#     hdrs = ["config.h"],
#     extra_visibility = [
#         "//test:__subpackages__",
#     ],
#     deps = [
#         ":random_lb_lib",
#         "//source/common/common:minimal_logger_lib",
#         "//source/common/upstream:load_balancer_context_base_lib",
#         "//source/extensions/load_balancing_policies/common:factory_base",
#         "@envoy_api//envoy/extensions/load_balancing_policies/random/v3:pkg_cc_proto",
#     ],
# )

# envoy_cc_library(
#     name = "random_lb_lib",
#     srcs = ["random_lb.cc"],
#     hdrs = ["random_lb.h"],
#     deps = ["//source/extensions/load_balancing_policies/common:load_balancer_lib"],
# )
