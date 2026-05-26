# Voice Translation MCP Server

A Python MCP server exposing control tools for a real-time two-PC voice translation session.

## Setup

```bash
pip install mcp
python server.py
```

## Tools exposed

| Tool | What it does |
|---|---|
| `register_pc` | Register pc_a or pc_b as connected, get relay config back |
| `set_language` | Change what a PC speaks and what it hears |
| `switch_voice` | Swap the TTS voice for a PC's output |
| `route_audio` | Pause / resume translation, or switch relay rooms |
| `list_languages` | All supported BCP-47 codes |
| `list_voices` | All available TTS voices with provider info |
| `get_session_status` | Full snapshot of both PCs + relay state |

## Connect to Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "voice-translation": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

Then restart Claude Desktop. You can now say things like:
- "Switch pc_b to speak French and hear English"
- "What voices are available?"
- "Pause audio for pc_a"
- "Show me the session status"

## Architecture

```
Claude (MCP client)
    │  stdio
    ▼
server.py  ←── in-memory session state
    │
    │  (your relay client reads SESSION_STATE or
    │   you extend this to push updates over WebSocket)
    ▼
WebSocket relay  ←→  PC A browser client
                 ←→  PC B browser client
```

## Extending

To push language/voice changes to live clients in real time, add a WebSocket
broadcast inside each tool handler — e.g. after updating `SESSION_STATE`,
call `await relay_ws.send(json.dumps({"type": "config", **new_config}))`.
