"""Local MCP clients launch this process as their Studio stdio server."""

import argparse
from importlib.metadata import version
import sys

from .protocol import MAX_MESSAGE, TOOLS, TOOLS_BY_NAME, decode, encode


PACKAGE_VERSION = version("arctos-studio-mcp")
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


class StdioServer:
    def __init__(self, call_tool):
        self.call_tool = call_tool
        self.version = None

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return self.error(None, -32600, "Invalid JSON-RPC request.")
        if "id" not in message:
            return None
        request_id = message["id"]
        if type(request_id) not in (str, int):
            return self.error(None, -32600, "Invalid request ID.")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "Expected an object for params.")

        method = message["method"]
        if method == "initialize":
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                return self.error(request_id, -32602, "Expected protocolVersion.")
            self.version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
            result = {"protocolVersion": self.version, "capabilities": {"tools": {}, "resources": {}},
                      "serverInfo": {"name": "arctos-studio", "version": PACKAGE_VERSION},
                      "instructions": "Work with the open Arctos Studio simulation. Turn on File → Studio MCP in Studio. "
                                      "Use get_scene and list_robot_library before editing. Scene positions are in metres. "
                                      "Use capture_viewport to inspect the rendered scene. Use plan_cartesian_waypoints and "
                                      "check_joint_path before previewing a proposed joint motion. Use execute_workflow "
                                      "to pass results between ordered Studio calls."}
        elif method == "ping":
            result = {}
        elif not self.version:
            return self.error(request_id, -32002, "Initialize the MCP session before calling tools.")
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        elif method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str) or name not in TOOLS_BY_NAME or not isinstance(arguments, dict):
                return self.error(request_id, -32602, "Expected a known tool name and an arguments object.")
            result = self._tool_result(name, arguments)
        else:
            return self.error(request_id, -32601, "Method not found.")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _tool_result(self, name, arguments):
        try:
            data = self.call_tool(name, arguments)
        except (RuntimeError, ValueError, OSError) as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}
        if name == "capture_viewport":
            image = {"type": "image", "mimeType": "image/png", "data": data["png"]}
            data = {key: value for key, value in data.items() if key != "png"}
        else:
            image = None
        result = {"content": [{"type": "text", "text": encode(data).decode("utf-8").rstrip()}]}
        if image is not None:
            result["content"].append(image)
        if self.version in SUPPORTED_VERSIONS[:2]:
            result["structuredContent"] = data
        return result

    @staticmethod
    def error(request_id, code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main():
    parser = argparse.ArgumentParser(description="Run the local Arctos Studio MCP server over stdio.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {PACKAGE_VERSION}")
    parser.parse_args()

    from PyQt5.QtCore import QCoreApplication

    from .ipc import call_studio

    app = QCoreApplication([])
    server = StdioServer(call_studio)
    while line := sys.stdin.buffer.readline(MAX_MESSAGE + 1):
        if len(line) > MAX_MESSAGE:
            # Drain the remainder so it cannot be mistaken for another request.
            while line and not line.endswith(b"\n"):
                line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
            response = server.error(None, -32700, "MCP message is too large.")
        else:
            try:
                message = decode(line)
            except (ValueError, RecursionError):
                response = server.error(None, -32700, "Invalid JSON.")
            else:
                response = server.handle(message)
        if response is not None:
            sys.stdout.buffer.write(encode(response))
            sys.stdout.buffer.flush()
        app.processEvents()
