# Arctos Studio MCP

Connect a local AI client to the Arctos Studio robot simulator. Inspect the open workcell, build a scene, plan and preview simulated motion, write targets to the Studio timeline, and capture the viewport.

## Quick start on Windows

You need Python 3.10 or later and an [Arctos Studio build](https://arctosrobotics.com/product/arctos-studio-2/) with **File → Studio MCP**. The adapter and Studio run on the same computer under the same user account.

The first Windows installer with the MCP bridge is pending. If your Studio build already has **File → Studio MCP**, you can connect it now.

1. Open Studio and enable **File → Studio MCP**. Keep that window open. One Studio window can listen at a time.
2. Download or clone this repository and open PowerShell in its root folder. Install the adapter in a virtual environment.

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install .
   $server = (Resolve-Path .\.venv\Scripts\arctos-studio-mcp.exe).Path
   & $server --version
   ```

3. Register it with your client and start a new client session. Choose the command for your client.

   ```powershell
   codex mcp add arctos-studio -- $server
   claude mcp add --transport stdio --scope user arctos-studio -- $server
   gemini mcp add --transport stdio --scope user arctos-studio $server
   ```

4. Try this prompt for a read-only connection check.

   > Use Arctos Studio MCP to inspect the open scene. List the robots and models you find, then capture the viewport.

The adapter uses MCP over local standard input and output (stdio). It requires no adapter API key or HTTP endpoint. Any local MCP client that can launch a stdio process can use the executable or run `python -m arctos_studio_mcp` with the Python interpreter where the package is installed.

### Desktop clients

In [Claude Desktop](https://modelcontextprotocol.io/docs/develop/connect-local-servers), add the server to `%APPDATA%\Claude\claude_desktop_config.json`. Replace the example command with the absolute path printed by `$server`, and escape each backslash in JSON.

```json
{
  "mcpServers": {
    "arctos-studio": {
      "command": "C:\\path\\to\\arctos-studio-mcp\\.venv\\Scripts\\arctos-studio-mcp.exe"
    }
  }
}
```

In [VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers), add the same executable to the `servers` object in your user or workspace `mcp.json` and set its `type` to `stdio`.

## What you can do

| Area | Common tools |
| --- | --- |
| Scene and camera | `get_scene`, `open_scene`, `save_scene`, `undo_scene_edit`, `get_view`, `capture_viewport` |
| Models and drawings | `create_primitives`, `import_models`, `transform_model`, `import_drawings` |
| Robots and frames | `list_robot_library`, `add_robots`, `move_robot_base`, `list_frames`, `transform_points` |
| Motion | `forward_kinematics`, `solve_inverse_kinematics`, `plan_cartesian_waypoints`, `check_joint_path`, `preview_joint_path` |
| Studio timeline | `get_program`, `add_program_targets`, `remove_program_targets`, `rename_program` |
| Workflows | `execute_workflow` |

The client can discover the full catalog and argument schemas through MCP `tools/list`. Scene coordinates and dimensions use metres with world Z up. Rotary joints use degrees and linear joints use millimetres. File tools accept absolute local paths. `save_scene` creates a new `.arctos` file and protects existing files from overwrite.

This integration works on the simulator. Scene edits require a disconnected robot controller and idle simulation. `check_joint_path` samples joint limits and end-of-chain clearance against model bounds. It omits full-arm, gripper, and self-collision checks, so use its results for simulation review.

## Troubleshooting

- **The client shows tools, but calls fail.** Tool discovery works as soon as the adapter starts. Open Studio, enable **File → Studio MCP**, and retry under the same Windows user. If the menu item is missing, install a Studio build that includes the bridge.
- **The client cannot start the server.** Run `& $server --version` in PowerShell. Update the client entry if you moved or reinstalled the virtual environment, then restart the client.
- **An edit is blocked.** Disconnect any robot controller, pause physics, stop playback or motion previews, and close any open Studio dialog.
- **A large import or workflow times out.** The adapter waits up to 120 seconds for Studio. For Codex, set `tool_timeout_sec = 130` in the existing `[mcp_servers.arctos-studio]` section. Check the scene before retrying an edit. [Codex MCP configuration](https://developers.openai.com/codex/mcp)

## Development

Install the package into a virtual environment and run `python -m unittest discover -s tests -v` with that environment's interpreter. The tests exercise the installed stdio process, MCP tool discovery, and a private Qt IPC connection. For Studio-side changes, update the adapter's packaged tool catalog and IPC code alongside the matching Studio bridge.

The adapter is licensed under [GPL-3.0-only](LICENSE).
