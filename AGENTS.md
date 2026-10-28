# Project working guide

## Read first

- `README.md`: setup and CLI use.
- `docs/ARCHITECTURE.md`: module boundaries, domain vocabulary and lifecycle.
- `docs/DECISIONS.md`: accepted ADRs and rationale.
- `docs/PROTOCOL.md`: exact commands and supporting device/vendor evidence.
- `docs/ACCEPTANCE.md`: dated validation record and remaining hardware work.
- `docs/OPERATIONS.md`: research SSH, private backups and continuation details.

## Constraints

- Preserve supplied firmware. The builder may modify a private copy of the pinned
  C100X 1.5.8 stock image; Home Assistant design is outside this project. The
  stock-device flash workflow must not require SSH.
- Builder payloads (raw debugfs commands and Python hooks) are trusted host code,
  not sandboxed. Keep builder dependencies out of the flasher runtime. Build and
  flash are separate commands; a build report never authorizes a device write.
- Establish device-changing commands from evidence. Do not guess parameters,
  replace the vendor flow with raw partition writes, retry uncertain writes or
  reboot as error cleanup.
- Keep read-only preflight separate from explicit flashing. Inject failures only
  in simulation, never by deliberately interrupting an actual write.
- Do not print credentials or commit vendor/research files, firmware or private
  backups. Authorized plain backups contain secrets and remain Git-ignored.
- A worker ACK, a completed sequence and functional acceptance are distinct
  evidence levels. Update the acceptance record only with observed results.

## Development

Use mise-managed tools. `mise run test` runs the offline Python suite without a
device or root. USB helper build/setup commands are in the README. Keep tests
offline unless a hardware step is explicitly being undertaken.

`research/TetherKit` is a separate upstream checkout with its own instructions;
read those before changing its code. Local research and `.local` contents are
not part of the tracked project. Record changed decisions in the ADRs, and keep
the usage, protocol and acceptance documents aligned with implementation/results.
