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
