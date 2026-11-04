"""Shared exception diagnostics for terminals, reports and subprocess boundaries.

Use normal exception chaining and add_note() to extend diagnostics. Never collect
locals, argv, stdin or successful command output. Known secrets are replaced by
exact value; ordinary paths, usernames and original error messages stay useful.
"""

from pathlib import Path
import subprocess
import traceback

TEXT_LIMIT = 8192
_secrets = set()


def remember_secret(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str) and value:
        _secrets.add(value)


def clear_secrets():
    _secrets.clear()


def protect_inputs(inputs):
    """Recognize explicit secret fields, without guessing from arbitrary text."""
    if isinstance(inputs, dict):
        for name, value in inputs.items():
            if str(name).lower() in ("password", "secret", "token", "private_key"):
                remember_secret(value)
            elif isinstance(value, dict):
                protect_inputs(value)


def text(value, *, limit=TEXT_LIMIT):
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")
    else:
        value = str(value)
    for secret in sorted(_secrets, key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    value = "".join(c if c.isprintable() or c in "\n\t" else repr(c)[1:-1] for c in value)
    if limit is not None and len(value) > limit:
        value = "[earlier text truncated]\n" + value[-limit:]
    return value


def details(error, **values):
    for name, value in values.items():
        if value is not None and value != "" and value != b"":
            error.add_note(f"{name.replace('_', ' ')}: {text(value)}")
    return error


def tool_error(error, tool, status, stderr=b"", *, stdout=b""):
    return details(error, tool=str(tool), exit_status=status, stderr=stderr, stdout=stdout)


def failure(error, _seen=None):
    """JSON-compatible exception chain, including stacks even without --debug."""
    seen = set() if _seen is None else _seen
    seen.add(id(error))
    notes = list(getattr(error, "__notes__", ()))
    if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
        # str(SubprocessError) includes argv, which may contain authentication.
        command = error.cmd
        tool = Path(str(command[0])).name if isinstance(command, (list, tuple)) and command else "subprocess"
        if isinstance(error, subprocess.TimeoutExpired):
            message = f"{tool} timed out after {error.timeout} seconds"
        else:
            message = f"{tool} exited with status {error.returncode}"
        if error.stderr:
            notes.append("stderr: " + text(error.stderr))
    else:
        message = str(error)
    record = {"type": type(error).__name__, "message": text(message)}
    if notes:
        record["notes"] = [text(note) for note in notes]
    for field in ("errno", "returncode", "timeout"):
        value = getattr(error, field, None)
        if isinstance(value, (int, float)):
            record[field] = value
    record["traceback"] = text("".join(traceback.format_tb(error.__traceback__)), limit=None)
    cause = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    if cause is not None and id(cause) not in seen:
        record["cause"] = failure(cause, seen)
    return record


def format_failure(error, *, debug=False):
    def render(record):
        lines = []
        if debug and record["traceback"]:
            lines.append("Traceback (most recent call last):\n" + record["traceback"].rstrip())
        lines.append(f"{record['type']}: {record['message']}")
        lines.extend(record.get("notes", ()))
        if "cause" in record:
            lines.append("Caused by:\n" + render(record["cause"]))
        return "\n".join(lines)
    return render(failure(error))
