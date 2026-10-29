# C100X firmware verification

These terms distinguish evidence about installed firmware from evidence about
the intercom's operation.

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
