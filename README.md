# Voice Translation MCP Server

A Python MCP server exposing control tools for a real-time two-PC voice translation session.

---

## Setup

```bash
pip install mcp
python server.py
```

---

## Tools exposed

| Tool | What it does |
|------|-------------|
| `register_pc` | Register pc_a or pc_b as connected, get relay config back |
| `set_language` | Change what a PC speaks and what it hears |
| `switch_voice` | Swap the TTS voice for a PC's output |
| `route_audio` | Pause / resume translation, or switch relay rooms |
| `list_languages` | All supported BCP-47 codes |
| `list_voices` | All available TTS voices with provider info |
| `get_session_status` | Full snapshot of both PCs + relay state |

---

## Testing with the Python client

The server uses stdio transport and is meant to be launched by an MCP client. You can test all tools locally without Claude Desktop using this script.

Create `test_client.py` in the project folder:

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "server.py"  # or absolute path if running from elsewhere

async def main():
    params = StdioServerParameters(
        command="python",
        args=[SERVER]
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # Switch pc_b to speak French and hear English
            result = await session.call_tool("set_language", {
                "pc_id": "pc_b",
                "speaks": "fr",
                "hears": "en"
            })
            print(result.content[0].text)

            # Check full session status
            result = await session.call_tool("get_session_status", {})
            print(result.content[0].text)

asyncio.run(main())
```

Run it:

```bash
python test_client.py
```

---

## Connect to Claude Desktop

> **Note:** MCP server connections in Claude Desktop require a **Pro or Max subscription.**
> Use the Python test client above for free local testing.

Add this to your config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

On Windows, if `python` isn't on Claude Desktop's PATH, use the full Python executable path:

```json
{
  "mcpServers": {
    "voice-translation": {
      "command": "C:\\Program Files\\Python313\\python.exe",
      "args": ["C:\\Users\\yourname\\path\\to\\server.py"]
    }
  }
}
```

Then restart Claude Desktop. You can now say things like:

- "Switch pc_b to speak French and hear English"
- "What voices are available?"
- "Pause audio for pc_a"
- "Show me the session status"

---

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

---

## Supported languages

| Code | Language |
|------|----------|
| `en` | English |
| `hi` | Hindi |
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `ja` | Japanese |
| `zh` | Chinese (Simplified) |
| `ar` | Arabic |
| `pt` | Portuguese |
| `ru` | Russian |

---

## Available voices

| Name | Provider | Gender | Style |
|------|----------|--------|-------|
| `nova` | OpenAI | Female | Natural |
| `shimmer` | OpenAI | Female | Warm |
| `echo` | OpenAI | Male | Natural |
| `onyx` | OpenAI | Male | Deep |
| `rachel` | ElevenLabs | Female | Conversational |
| `adam` | ElevenLabs | Male | Conversational |

---

## Extending

To push language/voice changes to live clients in real time, add a WebSocket
broadcast inside each tool handler — e.g. after updating `SESSION_STATE`,
call `await relay_ws.send(json.dumps({"type": "config", **new_config}))`.

Session state is **in-memory** — it resets when the server restarts. The relay
URL defaults to `ws://localhost:8080`; update `SESSION_STATE["relay_url"]` in
`server.py` to point to your actual relay.
