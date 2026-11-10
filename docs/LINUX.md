# Linux with Docker (experimental)

The tool was developed and validated on macOS. This page records a way to run its **SSH-only** part on Linux: building firmware and updating an intercom over the LAN. It was used on one setup (an Arch Linux host, Docker, the `python:3.14-slim` image and one C100X `02*06*0`) and has not been through the acceptance recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

## Status

On that setup the firmware was built with the commands below, and an intercom was updated from 1.5.7 to 1.5.8 over SSH. That update ran a first, device-specific form of the source-profile and resume code. The code as documented in this repository, and `plan-recovery` / `recover` over SSH, are covered by unit tests only and have not been run against an intercom.

## Scope

| | Linux with Docker |
|---|---|
| `builder-doctor`, `fetch-fw`, `build-fw`, `inspect-fw` | Available. |
| Wireless update: `plan`, `flash`, `plan-resume-recovery`, `resume-recovery`, and `plan-recovery` / `recover` with `--transport ssh` | Available. |
| USB networking and USB flashing (`usb`, and any device command without `--transport ssh`) | Not available: the USB helper is macOS-only. |
| Keeping the host awake during an update | Tries `systemd-inhibit`; warns if unavailable. See [Notes](#notes). |

In the commands below, `c100x` stands for `python -m classe100x`.

## Set up a container

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
c100x() { docker exec -it c100x sudo -u "$(id -un)" python -m classe100x "$@"; }
c100x builder-doctor
```

`-it` is required: the SSH passwords are read from a terminal. `builder-doctor` should end with `Core builder tools found and versions checked.`

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
- **Sleep.** On Linux the tool tries `systemd-inhibit` for the duration of the update. If it cannot acquire inhibition, it warns and continues. Docker usually cannot inhibit host sleep; keep the host awake yourself or wrap the Docker command on the host with `systemd-inhibit --what=sleep:idle --why="C100X update" docker exec -it ...`.
- **Keys.** The setup above used `--ssh-password` for both logins. `--ssh-key` takes a path inside the container, and an encrypted key has to be unlocked in an agent that the container cannot see by default. A dedicated, unencrypted key mounted read-only into the container is the simple alternative. This was not exercised.
- **Clean up.** `docker rm -f c100x` removes the container. The mounted directory keeps everything that was built.
