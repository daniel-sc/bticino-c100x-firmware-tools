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
A policy blocking manufacturer-initiated firmware installation while the
protected normal firmware runs, including app-approved and already-downloaded
updates, while permitting explicit USB flashing. Stock recovery and the earlier
stages of installing the protected firmware are outside this guarantee.
_Avoid_: Notification suppression, download blocking

**Staged vendor update**:
A manufacturer firmware package downloaded to the intercom and retained for
installation, including installation after a reboot.
_Avoid_: Installed update
