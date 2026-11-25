"""Local, same-user transport between the stdio process and the Qt application."""

import hashlib
import os
from pathlib import Path
import stat
import tempfile
import time

from PyQt5.QtNetwork import QLocalSocket

from .protocol import MAX_MESSAGE, decode, encode


CALL_TIMEOUT_MS = 120_000


def endpoint():
    if os.name == "nt":
        identity = str(Path.home()).casefold().encode("utf-8")
        return "arctos-studio-mcp-" + hashlib.sha256(identity).hexdigest()[:16]
    return str(Path(tempfile.gettempdir()) / f"arctos-mcp-{os.getuid()}" / "studio.sock")


def prepare_endpoint(name):
    if os.name == "nt":
        return str(Path(tempfile.gettempdir()) / (name + ".lock"))
    directory = Path(name).parent
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f"Studio MCP needs a private socket directory at {directory}.")
    return str(directory / "studio.lock")


def call_studio(name, arguments):
    packet = encode({"name": name, "arguments": arguments})
    if len(packet) > MAX_MESSAGE:
        raise ValueError("Studio request is too large.")
    socket = QLocalSocket()
    socket.setReadBufferSize(MAX_MESSAGE + 1)
    try:
        socket.connectToServer(endpoint())
        if not socket.waitForConnected(2_000):
            raise RuntimeError("Open Arctos Studio and turn on File → Studio MCP, then try again.")
        if socket.write(packet) != len(packet):
            raise RuntimeError("Could not send the request to Studio.")
        deadline = time.monotonic() + CALL_TIMEOUT_MS / 1000
        while not socket.canReadLine():
            if socket.bytesAvailable() >= MAX_MESSAGE:
                raise RuntimeError("Studio returned a response that is too large.")
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0 or not socket.waitForReadyRead(remaining):
                if socket.canReadLine():
                    break
                raise RuntimeError("Studio did not finish replying. Inspect the scene before retrying an edit.")
        response = decode(bytes(socket.readLine()))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]
    finally:
        socket.abort()
