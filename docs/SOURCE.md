# Run from source and test

For the self-contained download, use the [README](../README.md). This page is for
developers on macOS. Clone or download the repository, then open Terminal in its
root directory (containing `mise.toml`).
For firmware building and SSH updates on Linux, see [the Linux guide](LINUX.md).

## Builder setup

Install [Homebrew](https://brew.sh), then:

```sh
brew install mise e2fsprogs dropbear openssl@3
mise trust
mise install python 7zip
mise exec -- python -m classe100x builder-doctor
```

The builder needs no compiler when using prebuilt Apple Silicon packages.
Homebrew source builds may require Xcode Command Line Tools. Allow 4 GiB free
space for firmware builds.

Follow [BUILDER.md](BUILDER.md), replacing `/Applications/C100X/c100x` with
`mise exec -- python -m classe100x`. Run from the repository root; store private
inputs and outputs under Git-ignored `.local/`, creating that directory first.
Run builds as your ordinary user.

Tools are discovered from PATH and standard Homebrew locations, including keg-only
e2fsprogs. `--debugfs`, `--e2fsck` and `--sevenzip` override paths; SSH inputs can
override `dropbearkey` and `openssl`. Bundled tools take precedence over PATH when
present; explicit overrides take precedence over both. Nothing is silently installed.

## USB helper setup

Install Xcode Command Line Tools with `xcode-select --install` if needed; full
Xcode is unnecessary. From the repository root:

```sh
brew install libusb pkgconf
mise install cmake
git clone https://github.com/XiaoMiku01/TetherKit.git research/TetherKit
git -C research/TetherKit checkout --detach 1ded051fd243c547fd6e250a898f0164cc30561d
mise run transport-build
mise exec -- ctest --test-dir .local/tetherkit-build --output-on-failure
```

For privileged commands in [FLASHING.md](FLASHING.md), replace
`sudo /Applications/C100X/c100x` with `sudo "$(mise which python)" -m classe100x`.
Use the repository root as your working directory and supply your firmware path.

For transport debugging, run `sudo "$(mise which python)" -m classe100x usb` in
one terminal and use `--external-usb` with the firmware CLI in another. This
advanced mode leaves transport lifetime and route verification to the caller.
`probe` also uses an existing connection; it does not start managed USB.

## Offline tests

```sh
mise run test
mise run test-builder
```

Tests use simulated devices and synthetic filesystems, without an intercom or
root. The full suite skips builder integration tests when tools are absent;
`test-builder` requires them. SSH fixtures also need OpenSSH keygen, Dropbear
keygen and OpenSSL. Real firmware validation is local, outside GitHub CI.

Native MQTT tests use loopback fixture servers and host libmosquitto 1.4.14:

```sh
mise exec -- python tests/build_mqtt_library.py
CLASSE100X_MQTT_LIBRARY="$PWD/.local/mqtt-native/mosquitto-1.4.14/lib/libmosquitto.so.1" mise run test
```

CI requires these tests; locally they skip without the environment variable.
`tests/test_mqtt_runtime.py` also runs under Python 2.7 for compatibility checks.
See [RELEASING.md](RELEASING.md) for packaging and [OPERATIONS.md](OPERATIONS.md)
for workspace-specific research notes.
