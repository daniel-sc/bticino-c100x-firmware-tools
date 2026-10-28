"""Fixed C100X 1.5.8 FTP settings from the public MyHOME Suite 3.5.38 profile."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class VendorProfile:
    normal: Credentials
    recovery: Credentials


# Source: default/resTargetDir4/devices/2266_1.5_BT/xml/Protocol/protocol.xml
# Installer SHA-256: 707d8a43a5296a1ea87c33f111e9269c8bbd0fe524ac5efe87bdede8b6eb311b
# providerId=BTESUProtocolXPProvider, modObj=1.0.99, watershedVer=always.
# These shared vendor settings are public profile data, not user credentials.
# Keep the two environments explicit even though this profile uses the same pair.
# See docs/PROTOCOL.md for provenance and the device-side verification evidence.
C100X_PROFILE = VendorProfile(
    normal=Credentials("cfguser", "22K2mk7d"),       # ftp_*_updateFw
    recovery=Credentials("cfguser", "22K2mk7d"),     # ftp_*_UpdateRecovery
)
