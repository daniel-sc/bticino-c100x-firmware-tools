"""Private socket client for OpenSSH askpass; never import the application CLI."""

import os
import socket
import sys


def main():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(10)
            connection.connect(os.environ["C100X_ASKPASS_SOCKET"])
            answer = bytearray()
            while chunk := connection.recv(4098):
                answer.extend(chunk)
                if len(answer) > 4097:
                    return 1
        if not answer.endswith(b"\n") or b"\n" in answer[:-1] or b"\x00" in answer:
            return 1
        sys.stdout.buffer.write(answer)
        sys.stdout.buffer.flush()
        return 0
    except (OSError, KeyError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
