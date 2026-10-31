"""Host-only payload checks. Stock checksums are evidence, not redistributed code."""
import hashlib
import ipaddress
import re

from classe100x.firmware import FirmwareError

HASHES = {
    "/etc/init.d/rc": "5402ffc0c316ff7e10acfdffa85e81b8af16e5281c5a714a848308bfe219b29e",
    "/etc/inittab": "d1b2bbf70058109ab5b3c786201b59ebc035bd91997784b9846d305eea9bd260",
    "/usr/bin/python2.7": "58421be6dbcc6e5291e486a35f617cbfd2544dfe8bc3e1d7e33f112e10ce33cb",
    "/usr/lib/libpython2.7.so.1.0": "c2faeccb11ae5451416478d4d0b4ee50f06a48822ccc62023bf9dea5d90b86e3",
    "/usr/lib/libmosquitto.so.1": "4cc5fe6827a77c8e377431546e1fdcdda4e8e5f129246a4f106259e7172b0ecb",
    "/usr/lib/python2.7/ctypes/__init__.py": "1108a5cedabd761b635dd596bab5a6061e94491c8e800e9adb756eb780f9fcba",
    "/usr/lib/python2.7/ConfigParser.py": "6c61509f657410accda466d60982bdcd117ca42ae296f816da7ba920c4fb2c75",
    "/usr/lib/python2.7/collections.py": "735a95e3b509db8cd8481e70fc5c832fc970bfb3d9cac3e53112f70f4e06a4c6",
    "/usr/lib/python2.7/lib-dynload/_ctypes.so": "9bcd028876e58d637b4d89afb0407308d5b5b8710524f29a891c335a019534ec",
    "/usr/lib/python2.7/lib-dynload/select.so": "df4f9671b1bd5783c42dd8281592bb33c370f8e46d242f9f0e526c3417487d80",
    "/usr/lib/python2.7/lib-dynload/fcntl.so": "4daf82b5393375a57a97ddda369db5bb8878763c3fb982e06894b6e01bbffe1b",
    "/usr/lib/python2.7/lib-dynload/_socket.so": "4744a7d12e48193a0990f0e0600465b3752f16a674d5c79c5ad04ccb5ae38be3",
    "/usr/lib/python2.7/lib-dynload/_struct.so": "97f546955dc0e57da241f5a56078e2b56ab39ac1e65d5b3d981c3922de1f967c",
    "/usr/lib/libffi.so.6.0.4": "5133e238d8c8fe1d5cb6dea5122057cbaf64e4f85e0892fa63ef64ba3244edab",
    "/home/bticino/bin/openserver": "824f06f795744ae1c22738280df86872042075396669a0f968bff35fb06abc23",
    "/home/bticino/bin/bt_vct": "72852d4fd8c856aeb20348fcdcc14164d74c5b483353b7834aa4a02052e532a5",
    "/home/bticino/cfg/openserver": "fd5d7cf53be1e04c9778e8ac5bfc5a126b06240b8beba7a1b679e14392e7f299",
    "/home/bticino/cfg/stack_open.xml": "c6122c1d478003485124655e0202fc9011e94e08d4e5682134db76bb8cac1142",
    "/etc/init.d/bt_daemon-apps.sh": "66bb2f2dd1aaf31c2cf7ffab8a18481f03c7b471315edc969377401617a303b5",
    "/etc/init.d/flexisipsh": "19ea4ae54f129ceb00976833bd7aee8274bb107a8bc92bacb62ffcca2427216a",
}
LINKS = {"/usr/bin/python": "python2", "/usr/bin/python2": "python2.7",
         "/usr/lib/libffi.so.6": "libffi.so.6.0.4"}
STARTUP = {"/etc/rc5.d/S99c100x-mqtt": "../init.d/c100x-mqtt",
           "/etc/rc0.d/K01c100x-mqtt": "../init.d/c100x-mqtt",
           "/etc/rc6.d/K01c100x-mqtt": "../init.d/c100x-mqtt"}


def prerequisites(image):
    for path, expected in HASHES.items():
        data = image.read(path, limit=4 * 1024**2)
        if hashlib.sha256(data).hexdigest() != expected:
            raise FirmwareError("MQTT stock prerequisite changed")
    for path, target in LINKS.items():
        image.require_symlink(path, target)
    for path in ("/usr/bin/python2.7", "/home/bticino/bin/openserver", "/home/bticino/bin/bt_vct"):
        if not image.stat(path)["mode"] & 0o111:
            raise FirmwareError("MQTT runtime prerequisite is not executable")


def configuration(inputs):
    if set(inputs) - {"transport", "host", "port", "username", "password", "prefix"}:
        raise FirmwareError("Unknown MQTT input")
    if inputs.get("transport") != "plain":
        raise FirmwareError("MQTT v1 requires explicit transport: plain")
    try:
        host = str(ipaddress.IPv4Address(inputs["host"]))
        if not isinstance(inputs["host"], str) or host != inputs["host"]:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise FirmwareError("MQTT requires a numeric IPv4 host") from None
    port = inputs.get("port", 1883)
    if type(port) is not int or not 1 <= port <= 65535:
        raise FirmwareError("MQTT port must be an integer from 1 to 65535")
    prefix = inputs.get("prefix", "Bticino")
    if (not isinstance(prefix, str) or len(prefix) > 128
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix)):
        raise FirmwareError("MQTT prefix requires bounded ASCII topic levels without wildcards")
    credentials = []
    for key in ("username", "password"):
        value = inputs.get(key)
        if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512
                or any(ch in value for ch in "\x00\r\n")):
            raise FirmwareError("MQTT requires nonempty, bounded, single-line username and password")
        credentials.append(value.encode("utf-8").hex())
    return ("[mqtt]\nhost=%s\nport=%d\nprefix=%s\nusername_hex=%s\npassword_hex=%s\n"
            % (host, port, prefix, *credentials)).encode("ascii")
