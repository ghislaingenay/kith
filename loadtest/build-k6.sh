#!/bin/sh
# Builds ./loadtest/k6: k6 with the SSE extension, which Ask needs to time
# the first word of the streamed Answer. Stock k6 only sees the whole response.
# Needs Docker. Used by CI and by hand:
#   sh loadtest/build-k6.sh
set -eu

K6_VERSION=v2.3.0
XK6_SSE_VERSION=v0.2.0
XK6_IMAGE=grafana/xk6:1.4.14

cd "$(dirname "$0")"
docker run --rm -u "$(id -u):$(id -g)" -e GOCACHE=/tmp/go-cache -e GOPATH=/tmp/go \
  -v "$PWD:/xk6" -w /xk6 "$XK6_IMAGE" \
  build "$K6_VERSION" --with "github.com/phymbert/xk6-sse@$XK6_SSE_VERSION" --output /xk6/k6
./k6 version
