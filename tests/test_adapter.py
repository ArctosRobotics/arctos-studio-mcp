import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtNetwork import QLocalServer


def request(request_id, method, **params):
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"


def initialize(protocol="2025-11-25"):
    return request(1, "initialize", protocolVersion=protocol, capabilities={},
                   clientInfo={"name": "adapter-test", "version": "1"})


def start_adapter(endpoint):
    code = ("from arctos_studio_mcp import ipc, server; "
            f"ipc.endpoint = lambda: {endpoint!r}; server.main()")
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_module_launch_and_catalog(self):
        session = initialize() + '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        session += request(2, "tools/list")
        result = subprocess.run([sys.executable, "-m", "arctos_studio_mcp"],
                                input=session, text=True, encoding="utf-8",
                                capture_output=True, check=True, timeout=15)
        self.assertEqual(result.stderr, "")
        handshake, catalog = [json.loads(line)["result"] for line in result.stdout.splitlines()]
        self.assertEqual(handshake["protocolVersion"], "2025-11-25")
        self.assertEqual(handshake["serverInfo"]["name"], "arctos-studio")
        tools = {tool["name"]: tool for tool in catalog["tools"]}
        self.assertTrue(tools["get_scene"]["annotations"]["readOnlyHint"])
        self.assertEqual(tools["add_robots"]["inputSchema"]["required"], ["robots"])
        self.assertIn("capture_viewport", tools)
        self.assertIn("execute_workflow", tools)

    def test_tool_round_trip_over_private_qt_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (f"arctos-mcp-test-{uuid4().hex}" if sys.platform == "win32"
                    else str(Path(directory) / "studio.sock"))
            studio = QLocalServer()
            self.assertTrue(studio.listen(path), studio.errorString())
            try:
                with start_adapter(path) as client:
                    try:
                        client.stdin.write(initialize() + request(2, "tools/call", name="get_scene",
                                                                  arguments={"model_limit": 5}))
                        client.stdin.flush()
                        studio.waitForNewConnection(5_000)
                        socket = studio.nextPendingConnection()
                        self.assertIsNotNone(socket)
                        if not socket.canReadLine():
                            socket.waitForReadyRead(5_000)
                        self.assertEqual(json.loads(bytes(socket.readLine())),
                                         {"name": "get_scene", "arguments": {"model_limit": 5}})
                        scene = {"robots": [], "models": [], "hardware_connected": False}
                        socket.write((json.dumps({"result": scene}) + "\n").encode("utf-8"))
                        if socket.bytesToWrite():
                            self.assertTrue(socket.waitForBytesWritten(5_000))
                        stdout, stderr = client.communicate(timeout=15)
                    finally:
                        if client.poll() is None:
                            client.kill()
                self.assertEqual(client.returncode, 0, stderr)
                self.assertEqual(stderr, "")
                response = json.loads(stdout.splitlines()[1])["result"]
                self.assertEqual(response["structuredContent"], scene)
                self.assertEqual(json.loads(response["content"][0]["text"]), scene)
            finally:
                studio.close()

    def test_missing_studio_returns_tool_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (f"arctos-mcp-test-{uuid4().hex}" if sys.platform == "win32"
                    else str(Path(directory) / "studio.sock"))
            with start_adapter(path) as client:
                try:
                    session = initialize("2024-11-05") + request(2, "tools/call", name="get_scene")
                    stdout, stderr = client.communicate(session, timeout=15)
                finally:
                    if client.poll() is None:
                        client.kill()
        self.assertEqual(client.returncode, 0, stderr)
        handshake, response = [json.loads(line)["result"] for line in stdout.splitlines()]
        self.assertEqual(handshake["protocolVersion"], "2024-11-05")
        self.assertTrue(response["isError"])
        self.assertIn("Studio MCP", response["content"][0]["text"])
