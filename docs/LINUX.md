# Linux: building, SSH updates and experimental USB

Linux can build firmware and update an intercom over SSH. Current source also
implements experimental USB for native Ubuntu 24.04 and 26.04 Desktop x86-64 with
default NetworkManager. Read-only access, managed activation, normal/cancelled-session
cleanup and a complete flash with recovery handover passed on 26.04; the owner
also confirmed post-flash household functionality. Ubuntu 24.04 hardware coverage
remains open. Use a bundle built
from this source for USB; this does not imply older published assets include it.
Docker is optional for building and SSH, outside the USB reference configuration.

## Install the release bundle (recommended)

Download the `linux-x86_64.tar.gz` asset from [releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases).
It includes Python and builder tools and needs x86-64 Linux with glibc 2.39+,
OpenSSH client and CA certificates. On Ubuntu/Debian, those system dependencies
are `openssh-client` and `ca-certificates`.

```sh
tar -xzf c100x-*-linux-x86_64.tar.gz
./C100X/c100x builder-doctor
./C100X/c100x plan custom.fwz --transport ssh --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa
```

Use `./C100X/c100x` wherever the guides say `c100x`. Keep the whole folder together.
To update, extract the newer bundle into a fresh directory; keep firmware and
private settings outside it.

## Status

Linux hardware validation is limited. A contributor built firmware and updated
one C100X (`02*06*0`) from 1.5.7 to 1.5.8 using this Docker setup and earlier,
device-specific code. The generalized source-profile and SSH resume/recovery paths
have offline test coverage but no hardware validation yet. See [ACCEPTANCE.md](ACCEPTANCE.md).

## Scope

| | Linux |
|---|---|
| `builder-doctor`, `fetch-fw`, `build-fw`, `inspect-fw` | Available. |
| `plan`, `flash`, `plan-recovery`, `recover` with `--transport ssh` | Available. |
| `plan-resume-recovery`, `resume-recovery` (always SSH) | Available. |
| USB networking and USB flashing | Experimental; Ubuntu 24.04 and 26.04 Desktop x86-64 reference targets. |
| Keeping the host awake during an update | Tries `systemd-inhibit`; warns if unavailable. See [Notes](#notes). |

## Experimental native USB

Download, extract and run; no package installation is expected on the reference
Ubuntu 24.04/26.04 Desktop setups. The bundle includes `ip`; Ubuntu supplies native USB
drivers, NetworkManager and its matching `nmcli` client. Stock-device flashing
requires no SSH. Server/networkd, derivatives, other kernels, containers and WSL
receive no dedicated compatibility work. Missing drivers or network conflicts
stop with instructions; the tool installs nothing and edits no persistent settings.

```sh
sudo ./C100X/c100x plan custom.fwz
# Only after reviewing preflight and explicitly deciding to flash:
sudo ./C100X/c100x flash custom.fwz
```

Keep the computer awake, USB connected and device power stable throughout USB
flashing. Automatic sleep inhibition currently belongs to the SSH update path.

The command discovers exactly one USB `1da4:0056` device and its network interface.
It activates an in-memory, non-autoconnecting profile with `192.168.129.2/30`,
without default routes or DNS. Each transport check requires the route to `.1`
and source `.2` through that USB interface. Interfaces are rediscovered across
normal/recovery boots; names are not assumed stable. On exit, the temporary
profile is deleted and the previous connection is restored only if the original
interface incarnation remains. Another active C100X session is rejected.

The readiness wait also allows NetworkManager to recognize and manage a newly
enumerated interface. An interface that remains unmanaged fails at the deadline;
configuration and route errors still stop immediately.

On cleanup failure, inspect NetworkManager connections named `c100x-usb-*`.
Abrupt process death cannot guarantee cleanup; these profiles are in-memory, not
saved configuration. Stop the old process before removing its temporary profile.
Linux storage automount/unmount behavior is still a hardware-check item; the
existing macOS storage-unmount helper does not run on Linux.

### Prepared hardware session

Before connecting hardware: run offline checks, build/relocate/smoke-test the
bundle, select and inspect the intended FWZ, and prepare space for private logs.
Then, on Ubuntu Desktop:

1. Record Ubuntu/kernel version and `nmcli --version`. Connect one powered device.
2. Run `sudo ./C100X/c100x usb` in a terminal; in another run
   `./C100X/c100x probe`. This changes host networking but sends no device writes.
   Record the USB interface/driver (`readlink /sys/class/net/<interface>/device/driver`),
   `ip -j -4 route get 192.168.129.1`, and any mounted USB storage.
3. Stop `usb` with Ctrl-C. Check that the temporary profile disappeared and prior
   networking returned. Run `sudo ./C100X/c100x plan custom.fwz` and check cleanup
   again. If native binding/preflight fails, investigate before authorizing writes.
4. With separate owner authorization, perform the full `flash` above. Observe four
   transfers, three verified reboots, normal/recovery driver handovers and final
   host cleanup. Never deliberately interrupt a write or reboot as error cleanup.
5. Verify calls, two-way audio/video, door release and selected SSH/MQTT features.
   Record observed results in ACCEPTANCE.md, including storage behavior. An
   unexpected stop or binding issue may require another focused session.

## Optional: run from source with Docker

Use Docker to test unreleased code, keep builder dependencies off the host, or
provide a compatible userspace when the release bundle cannot run on your host.
Otherwise, use the release bundle above.

The example below uses an Arch Linux host with `python:3.14-slim`.
Here, `c100x` stands for `python -m classe100x` inside the container.

No image has to be built. One container only has to stay running while you work. Add `sudo` to the `docker` commands if your user is not in the `docker` group.

### 1. Start it from the project directory

The directory is mounted at `/app`, so the firmware, the cache and the evidence stay on the host.

```bash
docker run -dit --name c100x -v "$PWD:/app" -w /app python:3.14-slim sleep infinity
```

### 2. Install the tools

```bash
docker exec c100x sh -c 'apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates dropbear-bin e2fsprogs openssh-client openssl p7zip-full sudo'
```

`dropbear-bin` provides `dropbearkey` for the SSH payload, `e2fsprogs` provides `debugfs` and `e2fsck`, and `openssh-client` provides the `ssh`, `ssh-keyscan` and `ssh-keygen` that the tool runs from `/usr/bin`. `p7zip-full` pulls in `7zip`, which provides `7z`. `sudo` is used in step 4.

### 3. Create a user with your host IDs

Building refuses to run as root. Using the same UID and GID as on the host keeps the files in the mounted directory yours.

```bash
docker exec c100x sh -c "groupadd -g $(id -g) $(id -un) && useradd -m -u $(id -u) -g $(id -g) -s /bin/sh $(id -un)"
```

The commands fail if the UID or GID is already taken in the container.

### 4. Define a shortcut

```bash
c100x() {
  systemd-inhibit --what=sleep:idle --why="C100X update" \
    docker exec -it c100x sudo -u "$(id -un)" python -m classe100x "$@"
}
c100x builder-doctor
```

`-it` is required: the SSH passwords are read from a terminal. `builder-doctor` should end with `Core builder tools found and versions checked.`

Define this function in your host shell. The host's `systemd-inhibit` holds the
sleep/idle lock while `docker exec` runs; the container needs no systemd access.

## Build and update

Paths are paths inside the container (`/app/...`).

```bash
c100x fetch-fw --stock c100x-1.5.8 --cache /app/.cache
c100x build-fw --stock c100x-1.5.8 --cache /app/.cache --payload ssh \
  --ssh-public-key /app/c100x_ecdsa.pub --ssh-password \
  --output /app/custom.fwz --report /app/custom.build.json
c100x inspect-fw /app/custom.fwz
c100x plan --transport ssh --host 192.168.1.20 --ssh-user root2 --ssh-password \
  --destination-ssh-user root2 --destination-ssh-password /app/custom.fwz
```

- The public key must be ECDSA P-256 or RSA. The stock Dropbear rejects Ed25519 (`Stock Dropbear requires an ECDSA P-256 or legacy RSA public key`).
- `--report` must not exist yet.
- `--destination-ssh-password` asks for the password given to `build-fw`. Without it the tool tries the existing password and stops with `Destination password does not match both images`.
- Replace `plan` by `flash` only after `plan` passes. See [the wireless procedure](FLASHING.md#wireless-updates-over-ssh), and [Resuming an interrupted wireless update](FLASHING.md#resuming-an-interrupted-wireless-update) if a flash stops.

## Notes

- **Host names.** Multicast DNS does not normally work inside the default Docker network, so the default `Bticino-Classe100X.local` will not resolve. Pass the IPv4 address of the intercom, or a DNS name, with `--host`.
- **Files.** The recovery readback copies the recovery partitions into the working directory (`c100x-verification-*`), which needs at least 512 MiB free. The evidence report stays there afterwards.
- **Trusted identity.** The identity of the intercom is stored under the home of the container user (`~/Library/Application Support/C100X/trust`, a path inherited from macOS). Removing the container forgets it.
- **Sleep.** On native Linux the tool tries `systemd-inhibit` for the duration of the update. If it cannot acquire inhibition, it warns and continues. With Docker, the host-side shortcut above provides sleep prevention; the tool inside the container may still warn that inhibition is unavailable.
- **Keys.** The setup above used `--ssh-password` for both logins. `--ssh-key` takes a path inside the container, and an encrypted key has to be unlocked in an agent that the container cannot see by default. A dedicated, unencrypted key mounted read-only into the container is the simple alternative. This was not exercised.
- **Clean up.** `docker rm -f c100x` removes the container. The mounted directory keeps everything that was built.
