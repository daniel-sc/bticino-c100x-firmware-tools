#!/usr/bin/env bash
# Build-only dependencies for the Ubuntu 24.04 x86-64 release runner.
set -euo pipefail
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && "$(uname -m)" == x86_64 ]] || {
    echo "Build the Linux release on Ubuntu 24.04 x86-64." >&2
    exit 1
}
# Exact Debian source packages accompany the binaries we redistribute.
sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
apt-get update
apt-get install -y --no-install-recommends \
    build-essential pkg-config patchelf python3 ca-certificates openssh-client git \
    libssl-dev libbz2-dev libffi-dev liblzma-dev libsqlite3-dev libreadline-dev \
    libncurses-dev zlib1g-dev libzstd-dev uuid-dev \
    e2fsprogs dropbear-bin 7zip openssl
