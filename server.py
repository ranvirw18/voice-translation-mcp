"""
Real-Time Voice Translation MCP Server
Exposes tools to control language, voice, and routing
for a two-PC live translation session.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-translation-mcp")

# ---------------------------------------------------------------------------
# In-memory session state
# ---------------------------------------------------------------------------

SESSION_STATE: dict[str, Any] = {
    "pc_a": {
        "id": "pc_a",
        "speaks": "en",
        "hears": "hi",
        "voice": "nova",
        "connected": False,
        "last_seen": None,
    },
    "pc_b": {
        "id": "pc_b",
        "speaks": "hi",
        "hears": "en",
        "voice": "shimmer",
        "connected": False,
        "last_seen": None,
    },
    "relay_url": "ws://localhost:8080",
    "active_room": "default",
}

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "zh": "Chinese (Simplified)",
    "ar": "Arabic",
    "pt": "Portuguese",
    "ru": "Russian",
}

AVAILABLE_VOICES: dict[str, dict] = {
    "nova":    {"provider": "openai", "gender": "female", "style": "natural"},
    "shimmer": {"provider": "openai", "gender": "female", "style": "warm"},
    "echo":    {"provider": "openai", "gender": "male",   "style": "natural"},
    "onyx":    {"provider": "openai", "gender": "male",   "style": "deep"},
    "rachel":  {"provider": "elevenlabs", "gender": "female", "style": "conversational"},
    "adam":    {"provider": "elevenlabs", "gender": "male",   "style": "conversational"},
}

# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

app = Server("voice-translation-mcp")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="set_language",
            description=(
                "Set the spoken language for a PC and what language it should hear. "
                "Call this to reconfigure either participant mid-session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pc_id": {
                        "type": "string",
                        "enum": ["pc_a", "pc_b"],
                        "description": "Which PC to configure",
                    },
                    "speaks": {
                        "type": "string",
                        "description": "BCP-47 language code for what this PC speaks (e.g. 'en', 'hi')",
                    },
                    "hears": {
                        "type": "string",
                        "description": "BCP-47 language code for what this PC wants to hear (e.g. 'hi', 'en')",
                    },
                },
                "required": ["pc_id", "speaks", "hears"],
            },
        ),
        Tool(
            name="switch_voice",
            description="Switch the TTS voice used when synthesizing speech for a PC.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pc_id": {
                        "type": "string",
                        "enum": ["pc_a", "pc_b"],
                        "description": "Which PC's output voice to change",
                    },
                    "voice": {
                        "type": "string",
                        "description": "Voice name (use list_voices to see options)",
                    },
                },
                "required": ["pc_id", "voice"],
            },
        ),
        Tool(
            name="route_audio",
            description=(
                "Control audio routing: pause/resume translation for a PC, "
                "or switch to a new relay room."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["pause", "resume", "switch_room"],
                        "description": "Routing action to perform",
                    },
                    "pc_id": {
                        "type": "string",
                        "enum": ["pc_a", "pc_b", "all"],
                        "description": "Which PC(s) to affect",
                    },
                    "room": {
                        "type": "string",
                        "description": "Room name (only for switch_room action)",
                    },
                },
                "required": ["action", "pc_id"],
            },
        ),
        Tool(
            name="list_languages",
            description="List all supported languages with their BCP-47 codes.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_voices",
            description="List all available TTS voices with provider and style info.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_session_status",
            description="Get the full current state of the translation session — both PCs, relay, room.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="register_pc",
            description="Register a PC as connected (called by each client on startup).",
            inputSchema={
                "type": "object",
                "properties": {
                    "pc_id": {
                        "type": "string",
                        "enum": ["pc_a", "pc_b"],
                    },
                },
                "required": ["pc_id"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info("Tool called: %s  args=%s", name, arguments)

    if name == "set_language":
        return _set_language(arguments)

    if name == "switch_voice":
        return _switch_voice(arguments)

    if name == "route_audio":
        return _route_audio(arguments)

    if name == "list_languages":
        return _list_languages()

    if name == "list_voices":
        return _list_voices()

    if name == "get_session_status":
        return _get_session_status()

    if name == "register_pc":
        return _register_pc(arguments)

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _set_language(args: dict) -> list[TextContent]:
    pc_id = args["pc_id"]
    speaks = args["speaks"]
    hears = args["hears"]

    if speaks not in SUPPORTED_LANGUAGES:
        return [TextContent(type="text", text=f"Unsupported language code '{speaks}'. Use list_languages to see options.")]
    if hears not in SUPPORTED_LANGUAGES:
        return [TextContent(type="text", text=f"Unsupported language code '{hears}'. Use list_languages to see options.")]

    prev = dict(SESSION_STATE[pc_id])
    SESSION_STATE[pc_id]["speaks"] = speaks
    SESSION_STATE[pc_id]["hears"] = hears

    result = {
        "success": True,
        "pc_id": pc_id,
        "previous": {"speaks": prev["speaks"], "hears": prev["hears"]},
        "updated": {"speaks": speaks, "hears": hears},
        "labels": {
            "speaks": SUPPORTED_LANGUAGES[speaks],
            "hears": SUPPORTED_LANGUAGES[hears],
        },
        "message": (
            f"{pc_id} will now speak {SUPPORTED_LANGUAGES[speaks]} "
            f"and hear {SUPPORTED_LANGUAGES[hears]}."
        ),
        "relay_config": _build_relay_config(pc_id),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _switch_voice(args: dict) -> list[TextContent]:
    pc_id = args["pc_id"]
    voice = args["voice"]

    if voice not in AVAILABLE_VOICES:
        return [TextContent(type="text", text=f"Unknown voice '{voice}'. Use list_voices to see available options.")]

    prev_voice = SESSION_STATE[pc_id]["voice"]
    SESSION_STATE[pc_id]["voice"] = voice
    info = AVAILABLE_VOICES[voice]

    result = {
        "success": True,
        "pc_id": pc_id,
        "previous_voice": prev_voice,
        "new_voice": voice,
        "voice_info": info,
        "message": f"{pc_id} output voice switched from '{prev_voice}' to '{voice}' ({info['provider']}, {info['style']}).",
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _route_audio(args: dict) -> list[TextContent]:
    action = args["action"]
    pc_id = args["pc_id"]

    targets = ["pc_a", "pc_b"] if pc_id == "all" else [pc_id]

    if action in ("pause", "resume"):
        connected = action == "resume"
        for t in targets:
            SESSION_STATE[t]["connected"] = connected
        result = {
            "success": True,
            "action": action,
            "affected": targets,
            "message": f"Audio {action}d for: {', '.join(targets)}.",
        }

    elif action == "switch_room":
        room = args.get("room")
        if not room:
            return [TextContent(type="text", text="'room' is required for switch_room action.")]
        SESSION_STATE["active_room"] = room
        result = {
            "success": True,
            "action": "switch_room",
            "new_room": room,
            "relay_url": f"{SESSION_STATE['relay_url']}?room={room}",
            "message": f"All clients should reconnect to room '{room}'.",
        }
    else:
        return [TextContent(type="text", text=f"Unknown action: {action}")]

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _list_languages() -> list[TextContent]:
    result = {
        "supported_languages": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ],
        "count": len(SUPPORTED_LANGUAGES),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _list_voices() -> list[TextContent]:
    result = {
        "available_voices": [
            {"name": name, **info}
            for name, info in AVAILABLE_VOICES.items()
        ],
        "count": len(AVAILABLE_VOICES),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_session_status() -> list[TextContent]:
    result = {
        "session": {
            "relay_url": SESSION_STATE["relay_url"],
            "active_room": SESSION_STATE["active_room"],
        },
        "pc_a": SESSION_STATE["pc_a"],
        "pc_b": SESSION_STATE["pc_b"],
        "translation_pairs": [
            {
                "from_pc": "pc_a",
                "to_pc": "pc_b",
                "direction": f"{SUPPORTED_LANGUAGES.get(SESSION_STATE['pc_a']['speaks'], '?')} → {SUPPORTED_LANGUAGES.get(SESSION_STATE['pc_b']['speaks'], '?')}",
            },
            {
                "from_pc": "pc_b",
                "to_pc": "pc_a",
                "direction": f"{SUPPORTED_LANGUAGES.get(SESSION_STATE['pc_b']['speaks'], '?')} → {SUPPORTED_LANGUAGES.get(SESSION_STATE['pc_a']['speaks'], '?')}",
            },
        ],
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _register_pc(args: dict) -> list[TextContent]:
    pc_id = args["pc_id"]
    SESSION_STATE[pc_id]["connected"] = True
    SESSION_STATE[pc_id]["last_seen"] = datetime.utcnow().isoformat()

    result = {
        "success": True,
        "pc_id": pc_id,
        "config": SESSION_STATE[pc_id],
        "relay": {
            "url": SESSION_STATE["relay_url"],
            "room": SESSION_STATE["active_room"],
            "connect_to": f"{SESSION_STATE['relay_url']}?room={SESSION_STATE['active_room']}",
        },
        "message": f"{pc_id} registered. Connect WebSocket to relay and start streaming.",
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_relay_config(pc_id: str) -> dict:
    """Return the WebSocket relay config this PC should use after a language change."""
    pc = SESSION_STATE[pc_id]
    return {
        "relay_url": SESSION_STATE["relay_url"],
        "room": SESSION_STATE["active_room"],
        "stt_language": pc["speaks"],
        "tts_language": pc["hears"],
        "voice": pc["voice"],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    logger.info("Starting Voice Translation MCP server (stdio transport)...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
