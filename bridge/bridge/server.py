"""WebSocket server for the Stardew AI bridge.

Phase 2: echoes a static reply per click.
Later phases extend `_handle_npc_interact` to call the LLM / MCP client.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import websockets
from websockets.asyncio.server import ServerConnection

from bridge.protocol import (
    NpcInteract,
    NpcReply,
    SessionReset,
    parse_message,
)

log = logging.getLogger("bridge.server")


async def _handle_npc_interact(msg: NpcInteract, history: dict[str, list[dict]]) -> NpcReply:
    """Phase 2: pure echo. Phase 3 swaps the body for an LLM call."""
    text = f"You clicked {msg.npc}"
    history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
    history[msg.npc].append({"role": "assistant", "text": text})
    return NpcReply(id=msg.id, npc=msg.npc, text=text, done=True)


async def _handle_client(ws: ServerConnection) -> None:
    history: dict[str, list[dict]] = {}
    log.info("client connected: %s", ws.remote_address)
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            msg = parse_message(raw)
            if msg is None:
                log.warning("ignoring malformed/unknown frame: %r", raw[:200])
                continue

            if isinstance(msg, NpcInteract):
                log.info("Player clicked %s id=%s loc=%s", msg.npc, msg.id, msg.location)
                reply = await _handle_npc_interact(msg, history)
                await ws.send(reply.model_dump_json())

            elif isinstance(msg, SessionReset):
                log.info("session_reset (%s); clearing history", msg.reason)
                history.clear()

            else:
                log.debug("ignoring message of type %s on server", msg.type)
    except websockets.ConnectionClosed:
        pass
    finally:
        log.info("client disconnected")


@asynccontextmanager
async def serve(host: str = "127.0.0.1", port: int = 8765) -> AsyncIterator:
    """Start the server; yield the underlying websockets.Server.

    Returning the underlying object lets tests read the bound port when port=0.
    """
    server = await websockets.serve(_handle_client, host, port)
    try:
        yield server
    finally:
        server.close()
        await server.wait_closed()


async def _amain(host: str, port: int) -> None:
    async with serve(host, port) as server:
        bound_port = server.sockets[0].getsockname()[1]
        log.info("listening on ws://%s:%s", host, bound_port)
        await asyncio.Future()  # run forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        asyncio.run(_amain(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
