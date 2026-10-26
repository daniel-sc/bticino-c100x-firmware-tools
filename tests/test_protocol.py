import socket
import threading
import time
import unittest

from classe100x.protocol import ACK, AuthenticationRequired, FrameStream, ProtocolError, ReadOnlyClient


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.writer = socket.socketpair()
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.stream = FrameStream(self.reader)

    def test_coalesced_frames_are_not_discarded(self):
        self.writer.sendall(b"*#13**16*1*5*8##" + ACK)
        self.assertEqual(self.stream.receive(time.monotonic() + 1), b"*#13**16*1*5*8##")
        self.assertEqual(self.stream.receive(time.monotonic() + 1), ACK)

    def test_fragmented_frame(self):
        self.stream.buffer.extend(b"*#13**16*1*5*8#")
        self.writer.sendall(b"#")
        self.assertEqual(self.stream.receive(time.monotonic() + 1), b"*#13**16*1*5*8##")

    def test_disconnect_mid_frame(self):
        self.writer.sendall(b"*#13**")
        self.writer.close()
        with self.assertRaisesRegex(ProtocolError, "during a frame"):
            self.stream.receive(time.monotonic() + 1)

    def test_bounded_unterminated_frame(self):
        self.writer.sendall(b"*" * 4096)
        with self.assertRaisesRegex(ProtocolError, "frame limit"):
            self.stream.receive(time.monotonic() + 1)

    def test_malformed_frame(self):
        self.writer.sendall(b"garbage##")
        with self.assertRaisesRegex(ProtocolError, "Malformed"):
            self.stream.receive(time.monotonic() + 1)

    def test_deadline(self):
        with self.assertRaisesRegex(ProtocolError, "Timed out"):
            self.stream.receive(time.monotonic() + 0.01)


class ClientTests(unittest.TestCase):
    def serve(self, replies):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(2)
        port = server.getsockname()[1]
        observed = []
        failures = []

        def worker():
            try:
                with server, server.accept()[0] as conn:
                    conn.settimeout(2)
                    conn.sendall(ACK)
                    stream = FrameStream(conn)
                    for response in replies:
                        observed.append(stream.receive(time.monotonic() + 2))
                        conn.sendall(response)
            except BaseException as exc:
                failures.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def finish():
            thread.join(3)
            server.close()
            self.assertFalse(thread.is_alive(), "test server did not exit")
            self.assertEqual(failures, [])

        self.addCleanup(finish)
        return port, observed

    def test_read_only_preflight_transcript(self):
        port, observed = self.serve([
            ACK,
            b"*#13**15*99##" + ACK,
            b"*#13**16*1*5*8##" + ACK,
            b"*#13**17*2*6##" + ACK,
            b"*#13**19*1*2*3*4##" + ACK,
            b"*#13**40*1*0##" + ACK,
            b"*#1013**1*99*6*1*0##" + ACK,
        ])
        with ReadOnlyClient("127.0.0.1", port) as client:
            result = client.inspect()
        self.assertEqual(result["firmware"], ("1", "5", "8"))
        self.assertEqual(result["object_model"], ("1", "0", "99"))
        self.assertEqual(observed, [b"*99*0##", b"*#13**15##", b"*#13**16##", b"*#13**17##", b"*#13**19##", b"*#13**40##", b"*#1013**1##"])

    def test_no_write_or_side_effect_queries(self):
        client = ReadOnlyClient("unused")
        for dimension in (30, 31, 35, 36, 37, 43, 44, 45):
            with self.subTest(dimension=dimension), self.assertRaises(ValueError):
                client.query(dimension)
        for family, dimension in ((13, 1), (1013, 15), (1013, 0), (14, 40)):
            with self.subTest(family=family, dimension=dimension), self.assertRaises(ValueError):
                client.query(dimension, family=family)

    def test_auth_challenge_is_not_echoed(self):
        port, _ = self.serve([b"*#123456789##"])
        client = ReadOnlyClient("127.0.0.1", port)
        with self.assertRaises(AuthenticationRequired) as ctx:
            client.__enter__()
        self.assertNotIn("123456789", str(ctx.exception))
        self.assertIsNone(client.stream)

    def test_missing_final_ack_closes_session(self):
        port, _ = self.serve([ACK, b"*#13**16*1*5*8##"])
        with ReadOnlyClient("127.0.0.1", port) as client:
            with self.assertRaises(ProtocolError):
                client.query(16)
            self.assertIsNone(client.stream)

    def test_wrong_dimension_is_not_accepted(self):
        port, _ = self.serve([ACK, b"*#13**17*2*6##" + ACK])
        with ReadOnlyClient("127.0.0.1", port) as client:
            with self.assertRaisesRegex(ProtocolError, "Unexpected"):
                client.query(16)

    def test_nonfinite_timeout_is_rejected(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ReadOnlyClient("unused", timeout=timeout)
