"""Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own Discord
account: read DMs/servers, send messages, etc.

This exists because no maintained, ready-made MCP server does this — using a personal
account's token outside Discord's official Bot API is against Discord's Terms of Service
(self-botting), and official libraries (discord.js 11.4+, discord.py) deliberately dropped
user-token support to stop it. discord.py-self is the unofficial fork that restores it.
This was the user's explicit, informed choice after being told the ban risk twice.

Setup:
  1. Get your Discord user token: log into discord.com in a browser, open DevTools (F12) ->
     Application -> Local Storage -> https://discord.com -> copy the "token" value.
  2. Set it as DISCORD_USER_TOKEN in this server's env in mcp_servers.json. Never paste this
     token anywhere else — it is full, unscoped access to your account with no revocation
     granularity, unlike an OAuth token.
  3. Run: python discord_selfbot_server.py (jarvis.py's MCP client launches this for you once
     configured; you don't need to run it by hand).
"""

import asyncio
import os

import discord
from mcp.server.mcpserver import MCPServer

TOKEN = os.environ.get("DISCORD_USER_TOKEN", "").strip()

server = MCPServer("discord-selfbot")
client = discord.Client()
_ready = asyncio.Event()


@client.event
async def on_ready() -> None:
    _ready.set()


async def _resolve_channel(channel_id: str):
    cid = int(channel_id)
    channel = client.get_channel(cid)
    if channel is None:
        channel = await client.fetch_channel(cid)
    return channel


@server.tool()
async def list_servers() -> str:
    """Lists the Discord servers (guilds) this account is a member of, with their IDs."""
    await _ready.wait()
    if not client.guilds:
        return "Not a member of any servers."
    return "\n".join(f"{g.name} (id={g.id})" for g in client.guilds)


@server.tool()
async def list_dm_channels() -> str:
    """Lists currently open DM conversations, with their channel IDs."""
    await _ready.wait()
    dms = [c for c in client.private_channels if isinstance(c, discord.DMChannel)]
    if not dms:
        return "No open DM conversations."
    return "\n".join(f"{c.recipient} (channel_id={c.id})" for c in dms)


@server.tool()
async def find_dm_with_user(username: str) -> str:
    """Finds a DM channel ID by matching a username against currently open DM conversations."""
    await _ready.wait()
    needle = username.lower()
    matches = [
        c
        for c in client.private_channels
        if isinstance(c, discord.DMChannel) and needle in str(c.recipient).lower()
    ]
    if not matches:
        return f"No open DM found matching {username!r}. Try list_dm_channels to see what's open."
    return "\n".join(f"{c.recipient} -> channel_id={c.id}" for c in matches)


@server.tool()
async def read_messages(channel_id: str, limit: int = 20) -> str:
    """Reads the most recent messages from a server channel or DM, given its channel_id."""
    await _ready.wait()
    channel = await _resolve_channel(channel_id)
    lines = []
    async for msg in channel.history(limit=min(max(int(limit), 1), 100)):
        lines.append(f"[{msg.created_at.isoformat(timespec='minutes')}] {msg.author}: {msg.content}")
    lines.reverse()
    return "\n".join(lines) or "(no messages)"


@server.tool()
async def send_message(channel_id: str, content: str) -> str:
    """Sends a message to a server channel or DM, given its channel_id. Fires immediately."""
    await _ready.wait()
    channel = await _resolve_channel(channel_id)
    await channel.send(content)
    return f"Sent to channel {channel_id}."


async def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_USER_TOKEN is not set.")
    async with client:
        client_task = asyncio.create_task(client.start(TOKEN))
        try:
            await server.run_stdio_async()
        finally:
            client_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
