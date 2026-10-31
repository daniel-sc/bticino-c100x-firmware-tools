#!/usr/bin/python
"""C100X live MQTT bridge. Python 2.7/3 compatible; uses the stock MQTT library.

One connection generation owns all pending data. Destroy it on failure rather
than replaying events or uncertain commands. No MQTT protocol implementation.
"""
from __future__ import print_function

import binascii
from collections import deque
import ctypes as C
import errno
import fcntl
import hashlib
import os
import re
import select
import signal
import socket
import sys
import time

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

CONFIG = "/etc/c100x-mqtt/config.ini"
STATE = "/var/volatile/tmp/c100x-mqtt"
MONITOR = ("127.0.0.1", 20000)
COMMAND = ("127.0.0.1", 30006)
LIMIT = 4096
STOP = False
PARENT = None
clock = getattr(time, "monotonic", lambda: os.times()[4])


def running():
    return not STOP and (PARENT is None or os.getppid() == PARENT)


class BridgeError(Exception):
    """Messages are fixed diagnostics, never library errors or configuration."""


def valid_frame(data):
    return (3 <= len(data) <= LIMIT and data.find(b"##") == len(data) - 2
            and re.match(br"\*[0-9*#]+##\Z", data) is not None)


class Frames:
    def __init__(self):
        self.buffer = b""

    def feed(self, data):
        self.buffer += data
        frames = []
        while b"##" in self.buffer:
            frame, self.buffer = self.buffer.split(b"##", 1)
            frame += b"##"
            if not valid_frame(frame):
                raise BridgeError("invalid OpenWebNet frame")
            frames.append(frame)
        if len(self.buffer) > LIMIT:
            raise BridgeError("OpenWebNet frame exceeds limit")
        return frames


def configuration(path):
    parser = configparser.RawConfigParser()
    with open(path, "r") as source:
        parser.readfp(source) if hasattr(parser, "readfp") else parser.read_file(source)
    result = dict(parser.items("mqtt"))
    # Hex is scalar encoding, not encryption: it preserves whitespace/non-ASCII
    # credentials without shell evaluation or config-parser interpolation.
    result["username"] = binascii.unhexlify(result.pop("username_hex"))
    result["password"] = binascii.unhexlify(result.pop("password_hex"))
    result["prefix"] = result["prefix"].encode("ascii")
    result["host"] = result["host"].encode("ascii")
    result["port"] = int(result["port"])
    return result


class Log:
    """Two bounded private files; no logging-package dependency on the target."""
    def __init__(self, directory, secrets):
        self.path = os.path.join(directory, "bridge.log")
        self.secrets = sorted([s for s in secrets if s], key=len, reverse=True)

    def __call__(self, message, data=b""):
        raw = message.encode("ascii") + (b" " + data if data else b"")
        for secret in self.secrets:
            raw = raw.replace(secret, b"<REDACTED>")
        line = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " +
                repr(raw[:8192]) + "\n").encode("ascii")
        try:
            size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
            if size + len(line) > 512 * 1024:
                os.rename(self.path, self.path + ".1")
            with open(self.path, "ab") as output:
                output.write(line)
        except (IOError, OSError):
            # Logging cannot delay or repeat a door command.
            pass


class Message(C.Structure):
    _fields_ = [("mid", C.c_int), ("topic", C.c_char_p), ("payload", C.c_void_p),
                ("payloadlen", C.c_int), ("qos", C.c_int), ("retain", C.c_bool)]


class MQTT:
    """Single-threaded libmosquitto 1.4 ABI boundary; callbacks never block/raise."""
    def __init__(self, library, config, log):
        self.lib, self.log = library, log
        self.prefix = config["prefix"]
        self.connected = self.subscribed = self.accepting = False
        self.failure = None
        self.commands = deque()
        self.pending = {}
        self.last_sent = None
        self.callbacks = []  # ctypes callbacks must outlive the native client.
        self.client = None
        ptr, integer, text = C.c_void_p, C.c_int, C.c_char_p
        signatures = {
            "new": (ptr, [text, C.c_bool, ptr]), "destroy": (None, [ptr]),
            "username_pw_set": (integer, [ptr, text, text]),
            "opts_set": (integer, [ptr, integer, ptr]),
            "threaded_set": (integer, [ptr, C.c_bool]),
            "socket": (integer, [ptr]),
            "will_set": (integer, [ptr, text, integer, ptr, integer, C.c_bool]),
            "connect_async": (integer, [ptr, text, integer, integer]),
            "disconnect": (integer, [ptr]), "loop": (integer, [ptr, integer, integer]),
            "subscribe": (integer, [ptr, C.POINTER(integer), text, integer]),
            "publish": (integer, [ptr, C.POINTER(integer), text, integer, ptr, integer, C.c_bool]),
        }
        for name, (restype, args) in signatures.items():
            function = getattr(library, "mosquitto_" + name)
            function.restype, function.argtypes = restype, args
        # A prefix identifies one device on a broker; stable IDs prevent a dead
        # connection's delayed Will from overwriting a new generation's online.
        identity = b"c100x-" + hashlib.sha256(self.prefix).hexdigest()[:16].encode("ascii")
        self.client = library.mosquitto_new(identity, True, None)
        if not self.client:
            raise BridgeError("MQTT allocation failed")
        try:
            self.callback("connect", [integer], self.on_connect)
            self.callback("disconnect", [integer], self.on_disconnect)
            self.callback("subscribe", [integer, integer, C.POINTER(integer)], self.on_subscribe)
            self.callback("message", [C.POINTER(Message)], self.on_message)
            self.callback("publish", [integer], self.on_publish)
            version = integer(4)  # MQTT_PROTOCOL_V311; MOSQ_OPT_PROTOCOL_VERSION = 1.
            self.check(library.mosquitto_opts_set(self.client, 1, C.byref(version)))
            # Defer writes to loop()'s socket-readiness check. No library thread is
            # started; this also prevents CONNECT being written before TCP is ready.
            self.check(library.mosquitto_threaded_set(self.client, True))
            self.check(library.mosquitto_username_pw_set(self.client, config["username"], config["password"]))
            self.check(library.mosquitto_will_set(self.client, self.topic("LastWillT"), 7, b"offline", 1, True))
            self.check(library.mosquitto_connect_async(self.client, config["host"], config["port"], 15))
            fd = library.mosquitto_socket(self.client)
            if fd < 0 or not select.select([], [fd], [], 2)[1]:
                raise BridgeError("MQTT TCP connection timed out")
        except BaseException:
            library.mosquitto_destroy(self.client)
            self.client = None
            raise

    def topic(self, suffix):
        return self.prefix + b"/" + suffix.encode("ascii")

    def callback(self, name, args, handler):
        callback_type = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, *args)

        def guarded(client, userdata, *values):
            try:
                handler(*values)
            except Exception:
                self.failure = "MQTT callback failed"

        wrapped = callback_type(guarded)
        self.callbacks.append(wrapped)
        setter = getattr(self.lib, "mosquitto_" + name + "_callback_set")
        setter.argtypes, setter.restype = [C.c_void_p, callback_type], None
        setter(self.client, wrapped)

    def check(self, code):
        if code:
            raise BridgeError("MQTT operation failed (code %d)" % code)

    def on_connect(self, code):
        if code:
            self.failure = "MQTT connection rejected"
            return
        self.connected = True
        self.subscription = C.c_int()
        self.check(self.lib.mosquitto_subscribe(self.client, C.byref(self.subscription), self.topic("rx"), 0))

    def on_disconnect(self, code):
        self.connected = self.accepting = False
        self.failure = "MQTT disconnected"

    def on_subscribe(self, mid, count, granted):
        if mid != self.subscription.value or count != 1 or granted[0] != 0:
            self.failure = "MQTT subscription rejected"
        else:
            self.subscribed = True

    def on_message(self, pointer):
        message = pointer.contents
        if message.retain:
            self.log("retained command discarded")
            return
        if not self.accepting:
            return
        if message.topic != self.topic("rx") or not 0 < message.payloadlen <= LIMIT:
            self.log("invalid command discarded")
            return
        payload = C.string_at(message.payload, message.payloadlen)
        if not valid_frame(payload):
            self.log("invalid command discarded")
        elif len(self.commands) >= 16:
            self.log("command queue full; command discarded")
        else:
            self.log("RX", payload)
            self.commands.append((clock(), payload))

    def on_publish(self, mid):
        self.last_sent = mid
        self.pending.pop(mid, None)

    def publish(self, suffix, data, retained=False):
        if len(self.pending) >= 64:
            raise BridgeError("MQTT output backlog exceeded")
        mid = C.c_int()
        self.last_sent = None
        self.check(self.lib.mosquitto_publish(self.client, C.byref(mid), self.topic(suffix),
                                            len(data), data, 1 if retained else 0, retained))
        # QoS-0 callbacks may occur synchronously inside publish().
        if self.last_sent != mid.value:
            self.pending[mid.value] = clock()
        return mid.value

    def step(self):
        self.check(self.lib.mosquitto_loop(self.client, 50, 1))
        if self.failure:
            raise BridgeError(self.failure)
        if any(clock() - started > 3 for started in self.pending.values()):
            raise BridgeError("MQTT output stalled")

    def close(self):
        self.accepting = False
        self.commands.clear()
        try:
            if self.connected and not self.failure and not self.pending:
                mid = self.publish("LastWillT", b"offline", True)
                deadline = clock() + 1
                while mid in self.pending and clock() < deadline:
                    self.step()
                if mid not in self.pending:
                    self.lib.mosquitto_disconnect(self.client)
                    self.lib.mosquitto_loop(self.client, 50, 1)
            # Otherwise destroy without DISCONNECT: let the retained Will fire.
        except Exception:
            pass
        finally:
            self.lib.mosquitto_destroy(self.client)
            self.client = None
            self.pending.clear()


def open_monitor():
    stream = socket.create_connection(MONITOR, 2)
    deadline = clock() + 3
    try:
        for request in (None, b"*99*1##"):
            if request:
                stream.sendall(request)
            reply = b""
            while len(reply) < 6:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise BridgeError("monitor handshake timed out")
                stream.settimeout(remaining)
                # Leave coalesced events (including partial frames) in the socket.
                data = stream.recv(6 - len(reply))
                if not data:
                    raise BridgeError("monitor closed during handshake")
                reply += data
            if reply != b"*#*1##":
                raise BridgeError("monitor handshake rejected")
        stream.setblocking(False)
        return stream
    except BaseException:
        stream.close()
        raise


class Command:
    """One bounded nonblocking exchange; closing never retries a partial write."""
    def __init__(self, payload):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setblocking(False)
        self.remaining = payload
        self.frames = Frames()
        self.deadline = clock() + 2
        self.connecting = True
        try:
            code = self.socket.connect_ex(COMMAND)
            if code not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK):
                raise BridgeError("local command connect failed")
        except BaseException:
            self.socket.close()
            raise

    def step(self):
        if clock() >= self.deadline:
            raise BridgeError("local command timed out; delivery uncertain")
        readable, writable, _ = select.select([self.socket], [self.socket] if self.remaining else [], [], 0)
        if writable:
            if self.connecting:
                if self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                    raise BridgeError("local command connect failed")
                self.connecting = False
            count = self.socket.send(self.remaining)
            if count == 0:
                raise BridgeError("local command closed during write")
            self.remaining = self.remaining[count:]
        if readable:
            data = self.socket.recv(LIMIT)
            if not data:
                raise BridgeError("local command closed; delivery uncertain")
            frames = self.frames.feed(data)
            if frames:
                if self.remaining or frames[0] != b"*#*1##":
                    raise BridgeError("local command not acknowledged")
                return True
        return False

    def close(self):
        self.socket.close()


def generation(mqtt, log, started):
    monitor = command = None
    parser = Frames()
    connected_at = clock()
    try:
        while running():
            mqtt.step()
            if not running():
                break
            if monitor is None:
                if clock() - connected_at > 10:
                    raise BridgeError("MQTT readiness timed out")
                if not mqtt.subscribed:
                    continue
                monitor = open_monitor()
                mqtt.publish("start_date", started, True)
                mqtt.publish("LastWillT", b"online", True)
                mqtt.accepting = True
                log("online")
            readable, _, _ = select.select([monitor], [], [], 0)
            if readable:
                data = monitor.recv(LIMIT)
                if not data:
                    raise BridgeError("monitor disconnected")
                for frame in parser.feed(data):
                    log("TX", frame)
                    mqtt.publish("tx", frame)
            if command is None and mqtt.commands:
                received, payload = mqtt.commands.popleft()
                if clock() - received > 2:
                    log("expired pending command discarded")
                else:
                    command = Command(payload)
            if command is not None:
                if command.step():
                    log("command acknowledged")
                    command.close()
                    command = None
    finally:
        mqtt.accepting = False
        mqtt.commands.clear()
        if command is not None:
            command.close()
        if monitor is not None:
            monitor.close()


def pause(seconds):
    until = clock() + seconds
    while running() and clock() < until:
        time.sleep(min(0.2, max(0, until - clock())))


def worker(config, log):
    library = C.CDLL("libmosquitto.so.1")
    library.mosquitto_lib_init.argtypes = []
    library.mosquitto_lib_init.restype = C.c_int
    library.mosquitto_lib_cleanup.argtypes = []
    library.mosquitto_lib_cleanup.restype = C.c_int
    if library.mosquitto_lib_init():
        raise BridgeError("MQTT library initialization failed")
    delay = 1
    started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()).encode("ascii")
    try:
        while running():
            mqtt = None
            attempt = clock()
            try:
                mqtt = MQTT(library, config, log)
                generation(mqtt, log, started)
            except Exception as error:
                log(str(error) if isinstance(error, BridgeError) else "bridge I/O failed")
            finally:
                if mqtt is not None:
                    mqtt.close()
            if clock() - attempt >= 60:
                delay = 1
            if running():
                log("offline; reconnect in %d seconds" % delay)
                pause(delay)
                delay = min(30, delay * 2)
    finally:
        library.mosquitto_lib_cleanup()


def interrupted(signum, frame):
    global STOP
    STOP = True


def supervise(lock):
    global PARENT
    config = configuration(CONFIG)
    log = Log(STATE, (config["username"], config["password"]))
    log("supervisor started")
    delay = 1
    while not STOP:
        began = clock()
        supervisor_pid = os.getpid()
        pid = os.fork()
        if pid == 0:
            PARENT = supervisor_pid
            try:
                worker(config, log)
                os._exit(0)
            except BaseException:
                os._exit(1)  # No tracebacks containing config or callback data.
        ended = 0
        while not STOP:
            ended, status = os.waitpid(pid, os.WNOHANG)
            if ended:
                break
            time.sleep(0.2)
        if STOP and not ended:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            deadline = clock() + 5
            while clock() < deadline:
                ended, status = os.waitpid(pid, os.WNOHANG)
                if ended:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        if STOP:
            break
        log("worker exited; restarting")
        if clock() - began >= 60:
            delay = 1
        pause(delay)
        delay = min(30, delay * 2)
    log("supervisor stopped")


def main(action):
    os.umask(0o077)
    if not os.path.isdir(STATE):
        os.mkdir(STATE, 0o700)
    with open(os.path.join(STATE, "lock"), "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            if action == "start":
                return 0
            lock.seek(0)
            pid = int(lock.read())
            # A reused PID must not turn stop into a signal to another service.
            with open("/proc/%d/cmdline" % pid, "rb") as proc:
                if os.path.abspath(__file__).encode("utf-8") not in proc.read().split(b"\0"):
                    raise BridgeError("supervisor identity mismatch")
            if action == "status":
                return 0
            os.kill(pid, signal.SIGTERM)
            until = clock() + 8
            while clock() < until:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return 0
                except IOError:
                    time.sleep(0.1)
            raise BridgeError("supervisor stop timed out")
        if action != "start":
            return 3 if action == "status" else 0
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, interrupted)
        supervise(lock)
    return 0


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("start", "stop", "status"):
            raise BridgeError("expected start, stop or status")
        sys.exit(main(sys.argv[1]))
    except Exception:
        print("C100X MQTT service failed; inspect private runtime logs", file=sys.stderr)
        sys.exit(1)
