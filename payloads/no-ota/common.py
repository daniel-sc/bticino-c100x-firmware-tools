"""Pinned startup policy for the researched stock image; no vendor assets bundled."""
import hashlib
import posixpath
import re

from classe100x.firmware import FirmwareError

STACK = "/home/bticino/cfg/stack_open.xml"
CLOUD = "/home/bticino/cfg/bt_eliot"
BOOT = "/etc/rcS.d/S96-dedrifu.sh"
STOCK = {
    STACK: "c6122c1d478003485124655e0202fc9011e94e08d4e5682134db76bb8cac1142",
    CLOUD: "805294b7c0d2572ad178ca5378da12b7243c7293d4a21be22f2b232af094ad33",
}
OUTPUT = {
    STACK: "43f1b13b600cb8381532c75e373c7e8d1e71fa8af1d8c132ee9d81388472e52f",
    CLOUD: "9a88bc5beaeaa2a2a8582f725b221af975906e23852f36c48a9b3413c05e97ac",
}
# Pin both selectable XML variants and the code behind the researched policy.
# Exact XML bytes also verify Dedrifu=0 and contiguous remaining process entries.
UNCHANGED = {
    "/home/bticino/cfg/stack_open_reduced.xml": ("b952ab7696302a66faf11291f702ebd9894ce4c5b8789a4c7fd75dd8aebd68da", 0o664, 1000),
    "/etc/init.d/dedrifu.sh": ("4a596fde7da20c16fc01e4db642ce8927e5b5969dc77ba367818039a5b7cbc42", 0o755, 0),
    "/etc/init.d/bt_daemon-apps.sh": ("66bb2f2dd1aaf31c2cf7ffab8a18481f03c7b471315edc969377401617a303b5", 0o700, 0),
    "/etc/init.d/rcS": ("19ce896144ff4c85b826fe3cd5f940ff5d41ec19b6bb56f2966215da7888c7be", 0o755, 0),
    "/etc/init.d/rc": ("5402ffc0c316ff7e10acfdffa85e81b8af16e5281c5a714a848308bfe219b29e", 0o755, 0),
    "/bin/bt_hosts.sh": ("85f91bbb99928324018d107a91a06a688b29604643df24e861dfefefb145bb5c", 0o775, 1000),
    "/home/bticino/bin/bt_daemon": ("812189781d79a417f3b32dbd780cb89ec75cbb3aedffd99f91c1780889621b5a", 0o755, 1000),
    "/home/bticino/bin/bt_eliot": ("c13096ef94bdecc333cda8d0745edbf7d991b689566fcea225331e82fef56776", 0o755, 1000),
    "/home/bticino/bin/fw_manager": ("9b6aee9fbe5003a3b231ba61887f1a50dd818cbd66fa83bd045f1f2b7025b643", 0o755, 1000),
    "/home/bticino/bin/dedrifupdater": ("faae6c8fd4a876e4609e695b742302079430b287cd465d1f07d8593323ae518d", 0o755, 1000),
    "/home/bticino/bin/bt_device": ("e0db9d2d01e549479a0c3e832a6dbcb76a5d355d95b3105d00fe1eb303b604be", 0o755, 1000),
    "/home/bticino/lib/libdedrifupdater.so": ("4f8c9d45629c55777704f965fc9a8bb465d34df9228b5d417c5a174116b7bc6b", 0o755, 1000),
}


def require_digest(data, expected, path):
    if hashlib.sha256(data).hexdigest() != expected:
        raise FirmwareError(f"no-ota content check failed: {path}")


def require_pinned(image, path, expected, mode, owner):
    data = image.read(path, limit=8 * 1024**2)
    require_digest(data, expected, path)
    image.require_file(path, data, mode=mode, uid=owner, gid=owner)


def prerequisites(image):
    for path, (expected, mode, owner) in UNCHANGED.items():
        require_pinned(image, path, expected, mode, owner)
    # An INI can override/add daemon processes. Only the researched, absent case
    # is supported; do not attempt to interpret arbitrary vendor overrides.
    image.require_absent("/home/bticino/cfg/bt_daemon")


def require_no_updater_links(image):
    # Catch ordinary composition conflicts even if a payload changes the link's
    # ordering/name. This is not analysis of arbitrary trusted startup code.
    targets = {"/etc/init.d/dedrifu.sh", "/home/bticino/bin/fw_manager",
               "/home/bticino/bin/dedrifupdater"}
    inodes = {image.stat(path)["inode"] for path in targets}
    for level in ("S", "0", "1", "2", "3", "4", "5", "6"):
        directory = f"/etc/rc{level}.d"
        for name in image.names(directory):
            if not name.startswith(("S", "K")):
                continue
            path = f"{directory}/{name}"
            info = image.stat(path)
            target = re.search(r'Fast link dest: "([^"\n]+)"', info["raw"])
            if (info["inode"] in inodes or (target and
                    posixpath.normpath(posixpath.join(directory, target[1])) in targets)):
                raise FirmwareError(f"no-ota updater startup link remains: {path}")
