"""Prepare a pinned host-only native test dependency; never installed in firmware."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

root = Path(".local/mqtt-native").resolve()
root.mkdir(parents=True, exist_ok=True)
archive = root / "mosquitto-1.4.14.tar.gz"
url = "https://codeload.github.com/eclipse-mosquitto/mosquitto/tar.gz/refs/tags/v1.4.14"
if not archive.exists():
    with urllib.request.urlopen(url, timeout=60) as response:
        archive.write_bytes(response.read(4 * 1024**2))
if hashlib.sha256(archive.read_bytes()).hexdigest() != "6e880a77c395db63fe5a0a5530ad255e65464534290ab65211c072f812462bde":
    raise SystemExit("Native MQTT test source checksum mismatch")
with tarfile.open(archive) as source:
    source.extractall(root, filter="data")
command = ["make", "-C", str(root / "mosquitto-1.4.14/lib"), "-j4", "libmosquitto.so.1",
           "WITH_TLS=no", "WITH_SRV=no"]
if sys.platform == "darwin":
    command.append("LIB_LDFLAGS=")
subprocess.run(command, check=True)
print("Native MQTT tests: set CLASSE100X_MQTT_LIBRARY to", root / "mosquitto-1.4.14/lib/libmosquitto.so.1")
