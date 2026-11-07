# C100X firmware behavior and verification

These terms describe firmware update behavior and distinguish evidence about
installed firmware from evidence about the intercom's operation.

## Language

**Recovery integrity verification**:
An assessment of the installed recovery components against their expected
contents and filesystem consistency requirements. It is not proof of recovery
bootability or functioning update services.
_Avoid_: Recovery works, safe recovery

**Recovery boot verification**:
Evidence that the intercom has started its recovery environment and responds
through the required update interface.
_Avoid_: Recovery integrity verification

**Functional acceptance**:
Observed confirmation that the intercom's required household functions and
selected firmware features work after an update.
_Avoid_: Worker completion, protocol completion

**OTA prevention**:
A policy blocking manufacturer-initiated firmware installation in a protected
environment, including app-approved and already-downloaded updates, while
permitting explicit owner-controlled installation. Protection of one environment
does not imply protection of another or of earlier installation stages.
_Avoid_: Notification suppression, download blocking

**Owner wireless update**:
A firmware installation explicitly initiated by the owner over a wireless network.
It is distinct from manufacturer-initiated installation and does not imply
unattended completion or wireless recovery after failure.
_Avoid_: Manufacturer OTA, automatic update

**Owner update coordinator**:
The authority directing the stages of an owner wireless update and recording
its outcome. Its completion report is distinct from functional acceptance.
_Avoid_: Firmware payload, manufacturer update service

**Staged vendor update**:
A manufacturer firmware package downloaded to the intercom and retained for
installation, including installation after a reboot.
_Avoid_: Installed update
