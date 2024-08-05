package(default_visibility = ["//visibility:public"])

load(
    "@envoy//bazel:envoy_build_system.bzl",
    "envoy_cc_binary",
    "envoy_cc_library",
    "envoy_cc_test",
)

licenses(["notice"])  # Apache 2

load("@envoy_api//bazel:api_build_system.bzl", "api_proto_package")

# api_proto_package()

envoy_cc_binary(
    name = "envoy",
    repository = "@envoy",
    deps = [
        "//lb_random:random_lb_lib",
        "//appnet_filter:appnet_filter_config",
        "@envoy//source/exe:envoy_main_entry_lib",
    ],
)
