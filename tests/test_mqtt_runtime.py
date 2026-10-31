"""Offline bridge tests, also runnable with Python 2.7 and a host libmosquitto 1.4.14.

CLASSE100X_MQTT_LIBRARY selects the native test library. All endpoints are ephemeral
IPv4 loopback sockets; this fixture never contacts an intercom or real broker.
"""
from __future__ import print_function

import ctypes
import os
import select
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "payloads", "mqtt", "files"))
import bridge
sys.path.pop(0)

BELL = b"*8*1#1#4#21*10##"
PRESS, RELEASE = b"*8*19*20##", b"*8*20*20##"
ACK = b"*#*1##"


def exact(stream, count):
    data = b""
    while len(data) < count:
        part = stream.recv(count - len(data))
        if not part:
            raise EOFError()
        data += part
    return data


def packet(kind, data):
    size, length = len(data), b""
    while True:
        digit = size % 128
        size //= 128
        length += struct.pack("B", digit | (128 if size else 0))
        if not size:
            return struct.pack("B", kind) + length + data


def field(data):
    return struct.pack("!H", len(data)) + data


class Server:
    def __init__(self, handler):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(8)
        self.socket.settimeout(5)
        self.address = self.socket.getsockname()
        self.errors = []
        self.streams = []

        def run():
            try:
                handler(self)
            except Exception as error:
                self.errors.append(error)

        self.thread = threading.Thread(target=run)
        self.thread.daemon = True
        self.thread.start()

    def accept(self):
        stream, _ = self.socket.accept()
        stream.settimeout(5)
        self.streams.append(stream)
        return stream

    def close(self):
        for stream in self.streams:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass
            stream.close()
        self.socket.close()
        self.thread.join(6)
        if self.thread.is_alive():
            raise AssertionError("fixture thread did not stop")


class Broker(Server):
    def __init__(self, retained=None, acknowledge=True):
        self.publications = []
        self.connect = None
        self.disconnected = False
        self.acknowledge = acknowledge
        self.retained = retained
        self.stream = None
        self.send_lock = threading.Lock()
        Server.__init__(self, self.serve)

    def send(self, kind, data):
        with self.send_lock:
            self.stream.sendall(packet(kind, data))

    def command(self, data, retained=False):
        self.send(0x31 if retained else 0x30, field(b"Bticino/rx") + data)

    def serve(self, server):
        self.stream = self.accept()
        try:
            while True:
                kind = struct.unpack("B", exact(self.stream, 1))[0]
                length, multiplier = 0, 1
                while True:
                    digit = struct.unpack("B", exact(self.stream, 1))[0]
                    length += (digit & 127) * multiplier
                    if digit < 128:
                        break
                    multiplier *= 128
                data = exact(self.stream, length)
                if kind == 0x10:
                    self.connect = data
                    self.send(0x20, b"\0\0")
                elif kind == 0x82:
                    self.send(0x90, data[:2] + b"\0")
                    if self.retained:
                        self.command(self.retained, True)
                elif kind >> 4 == 3:
                    count = struct.unpack("!H", data[:2])[0]
                    topic, payload = data[2:2 + count], data[2 + count:]
                    if kind & 6:
                        mid, payload = payload[:2], payload[2:]
                        if self.acknowledge:
                            self.send(0x40, mid)
                    self.publications.append((topic, payload, kind))
                elif kind == 0xc0:
                    self.send(0xd0, b"")
                elif kind == 0xe0:
                    self.disconnected = True
                    break
                else:
                    raise AssertionError("unexpected MQTT packet")
        except (EOFError, socket.error):
            pass


class FramingTests(unittest.TestCase):
    def tearDown(self):
        bridge.STOP = False

    def test_fragmentation_coalescing_and_frame_limits(self):
        parser = bridge.Frames()
        self.assertEqual(parser.feed(BELL[:4]), [])
        self.assertEqual(parser.feed(BELL[4:] + PRESS + RELEASE[:3]), [BELL, PRESS])
        self.assertEqual(parser.feed(RELEASE[3:]), [RELEASE])
        for data in (b"hello##", b"*1##*2##", b"*1##\n", b"*" + b"1" * 4096):
            self.assertFalse(bridge.valid_frame(data))
        with self.assertRaises(bridge.BridgeError):
            bridge.Frames().feed(b"*" + b"1" * 4096)

    def test_monitor_handshake_preserves_partial_coalesced_event(self):
        def monitor(server):
            stream = server.accept()
            stream.sendall(ACK[:2])
            stream.sendall(ACK[2:])
            self.assertEqual(exact(stream, 7), b"*99*1##")
            stream.sendall(ACK + BELL[:5])
            stream.sendall(BELL[5:])

        server = Server(monitor)
        previous = bridge.MONITOR
        bridge.MONITOR = server.address
        try:
            stream = bridge.open_monitor()
            stream.settimeout(2)
            self.assertEqual(exact(stream, len(BELL)), BELL)
            stream.close()
        finally:
            bridge.MONITOR = previous
            server.close()
        self.assertEqual(server.errors, [])

    def test_log_rotation_and_credential_redaction(self):
        directory = tempfile.mkdtemp()
        try:
            log = bridge.Log(directory, (b"secret", b"123"))
            for _ in range(400):
                log("TX", b"*123*secret*" + b"7" * 4000 + b"##")
            paths = [os.path.join(directory, name) for name in os.listdir(directory)]
            self.assertEqual(len(paths), 2)
            self.assertLessEqual(sum(os.path.getsize(path) for path in paths), 1024 * 1024)
            for path in paths:
                with open(path, "rb") as source:
                    data = source.read()
                self.assertNotIn(b"secret", data)
                self.assertNotIn(b"123", data)
        finally:
            shutil.rmtree(directory)

    def test_log_rotation_errors_do_not_interrupt_bridge(self):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "bridge.log")
            with open(path, "wb") as output:
                output.write(b"x" * (512 * 1024))
            # rename(file, directory) raises OSError, distinct from IOError in 2.7.
            os.mkdir(path + ".1")
            bridge.Log(directory, ())("TX", BELL)
        finally:
            shutil.rmtree(directory)


@unittest.skipUnless(os.environ.get("CLASSE100X_MQTT_LIBRARY"), "Set CLASSE100X_MQTT_LIBRARY for native ABI tests")
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.library = ctypes.CDLL(os.environ["CLASSE100X_MQTT_LIBRARY"])
        self.assertEqual(self.library.mosquitto_lib_init(), 0)
        self.addCleanup(self.library.mosquitto_lib_cleanup)
        self.logs = []
        self.previous = bridge.MONITOR, bridge.COMMAND
        bridge.STOP = False
        self.addCleanup(self.restore)

    def restore(self):
        bridge.STOP = False
        bridge.MONITOR, bridge.COMMAND = self.previous

    def client(self, broker):
        config = dict(host=b"127.0.0.1", port=broker.address[1], prefix=b"Bticino",
                      username=b"fixture-user", password=b"fixture-password")
        return bridge.MQTT(self.library, config, lambda *args: self.logs.append(args))

    def pump(self, client, condition):
        deadline = time.time() + 4
        while not condition():
            self.assertLess(time.time(), deadline, "MQTT fixture timed out")
            client.step()

    def test_native_callbacks_retained_rejection_and_orderly_offline(self):
        broker = Broker(retained=PRESS)
        self.addCleanup(broker.close)
        client = self.client(broker)
        try:
            self.pump(client, lambda: client.subscribed and self.logs)
            self.assertFalse(client.commands)
            # MQTT 3.1.1, clean session, retained QoS1 Will, credentials, keepalive.
            self.assertEqual(broker.connect[:10], b"\0\x04MQTT\x04\xee\0\x0f")
            self.assertIn(field(b"Bticino/LastWillT") + field(b"offline"), broker.connect)
            client.accepting = True
            broker.command(PRESS, True)
            broker.command(b'{"shell":"bad"}')
            broker.command(PRESS)
            broker.command(RELEASE)
            self.pump(client, lambda: len(client.commands) == 2)
            self.assertEqual([data for _, data in client.commands], [PRESS, RELEASE])
            for _ in range(20):
                broker.command(PRESS)
            self.pump(client, lambda: any("queue full" in row[0] for row in self.logs))
            self.assertEqual(len(client.commands), 16)
            client.publish("tx", BELL)
            client.publish("LastWillT", b"online", True)
            self.pump(client, lambda: not client.pending and len(broker.publications) == 2)
            self.assertEqual(broker.publications[0], (b"Bticino/tx", BELL, 0x30))
            self.assertEqual(broker.publications[1], (b"Bticino/LastWillT", b"online", 0x33))
        finally:
            client.close()
        broker.thread.join(2)
        self.assertTrue(broker.disconnected)
        self.assertEqual(broker.publications[-1], (b"Bticino/LastWillT", b"offline", 0x33))
        self.assertFalse(client.commands)
        self.assertEqual(broker.errors, [])

    def test_stalled_publication_destroys_without_suppressing_will(self):
        broker = Broker(acknowledge=False)
        self.addCleanup(broker.close)
        client = self.client(broker)
        try:
            self.pump(client, lambda: client.subscribed)
            client.publish("LastWillT", b"online", True)
            for mid in client.pending:
                client.pending[mid] -= 4
            with self.assertRaises(bridge.BridgeError):
                client.step()
        finally:
            client.close()
        broker.thread.join(2)
        self.assertFalse(broker.disconnected)

    def test_generation_events_commands_and_monitor_loss(self):
        release_monitor = threading.Event()
        received = []

        def monitor(server):
            stream = server.accept()
            stream.sendall(ACK)
            self.assertEqual(exact(stream, 7), b"*99*1##")
            stream.sendall(ACK + BELL[:6])
            stream.sendall(BELL[6:])
            release_monitor.wait(4)
            stream.shutdown(socket.SHUT_RDWR)

        def commands(server):
            for frame in (PRESS, RELEASE):
                stream = server.accept()
                received.append(exact(stream, len(frame)))
                stream.sendall(ACK)
                self.assertEqual(stream.recv(1), b"")
            release_monitor.set()

        monitor_server, command_server = Server(monitor), Server(commands)
        self.addCleanup(monitor_server.close)
        self.addCleanup(command_server.close)
        bridge.MONITOR, bridge.COMMAND = monitor_server.address, command_server.address
        broker = Broker()
        self.addCleanup(broker.close)
        client = self.client(broker)
        errors = []

        def run():
            try:
                bridge.generation(client, lambda *args: self.logs.append(args), b"fixture-start")
            except bridge.BridgeError as error:
                errors.append(str(error))
            finally:
                client.close()

        thread = threading.Thread(target=run)
        thread.start()
        try:
            deadline = time.time() + 3
            while not any(topic == b"Bticino/tx" for topic, _, _ in broker.publications):
                self.assertLess(time.time(), deadline)
                time.sleep(0.01)
            broker.command(PRESS)
            broker.command(RELEASE)
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(received, [PRESS, RELEASE])
            self.assertEqual(errors, ["monitor disconnected"])
            self.assertFalse(client.accepting)
            self.assertFalse(client.commands)
            self.assertIn((b"Bticino/tx", BELL, 0x30), broker.publications)
        finally:
            bridge.STOP = True
            release_monitor.set()
            thread.join(5)
        self.assertEqual(monitor_server.errors + command_server.errors + broker.errors, [])


if __name__ == "__main__":
    unittest.main()
