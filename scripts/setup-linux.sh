#!/usr/bin/env bash
# Internal development setup. Tests themselves remain offline and unprivileged.
set -euo pipefail

if [[ "$(uname -s)" != Linux ]] || ! command -v apt-get >/dev/null; then
    echo "This setup requires Ubuntu/Debian Linux." >&2
    exit 1
fi
if [[ "$EUID" == 0 ]]; then
    echo "Run setup as your ordinary user; only package installation uses sudo." >&2
    exit 1
fi

cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    build-essential ca-certificates e2fsprogs dropbear-bin openssl openssh-client
mise install python 7zip
mise exec -- python tests/build_mqtt_library.py
