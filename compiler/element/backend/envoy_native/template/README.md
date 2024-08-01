# How to use

## Set Up Webdis

```bash
# clone the repo from https://github.com/jokerwyt/go-echo-example
go run server.go
go run frontend.go

# start webdis
sudo apt-get update && sudo apt-get install -y make gcc libc6-dev libevent-dev git && git clone https://github.com/nicolasff/webdis.git && cd webdis && make && ./webdis

bazel build //cache:envoy -c fastbuild
bazel-bin/cache/envoy -c envoy.yaml

# normal pass
curl localhost:8080/?key=apple

# cache hit
curl localhost:8080/?key=apple

# normal pass
curl localhost:8080/?key=banana

# cache hit
curl localhost:8080/?key=banana
```



<!-- # Envoy filter example

This project demonstrates the linking of additional filters with the Envoy binary.
A new filter `echo2` is introduced, identical modulo renaming to the existing
[`echo`](https://github.com/envoyproxy/envoy/blob/master/source/extensions/filters/network/echo/echo.h)
filter. Integration tests demonstrating the filter's end-to-end behavior are
also provided.

For an example of additional HTTP filters, see [here](http-filter-example).

[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/envoyproxy/envoy-filter-example/badge)](https://securityscorecards.dev/viewer/?uri=github.com/envoyproxy/envoy-filter-example)

## Building

To build the Envoy static binary:

1. `git submodule update --init`
2. `bazel build //:envoy`

## Testing

To run the `echo2` integration test:

`bazel test //:echo2_integration_test`

To run the regular Envoy tests from this project:

`bazel test @envoy//test/...`

## How it works

The [Envoy repository](https://github.com/envoyproxy/envoy/) is provided as a submodule.
The [`WORKSPACE`](WORKSPACE) file maps the `@envoy` repository to this local path.

The [`BUILD`](BUILD) file introduces a new Envoy static binary target, `envoy`,
that links together the new filter and `@envoy//source/exe:envoy_main_entry_lib`. The
`echo2` filter registers itself during the static initialization phase of the
Envoy binary as a new filter. -->
