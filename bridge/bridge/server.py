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

from bridge import llm as llm_mod
from bridge.protocol import (
    NpcInteract,
    NpcReply,
    SessionReset,
    parse_message,
)

log = logging.getLogger("bridge.server")


def _make_handler(client_factory):
    """Returns an _handle_npc_interact bound to a client (or None for echo mode)."""
    client = client_factory() if client_factory is not None else None

    async def handler(msg: NpcInteract, history: dict[str, list[dict]]) -> NpcReply:
        if client is None:
            text = f"You clicked {msg.npc}"
        else:
            user_text = ""  # phase 3: no free-text input from the player yet
            text = await llm_mod.reply(
                client=client,
                npc_name=msg.npc,
                player_name=msg.player,
                location=msg.location,
                history=history.get(msg.npc, []),
                user_text=user_text,
            )
        history.setdefault(msg.npc, []).append({"role": "user", "text": ""})
        history[msg.npc].append({"role": "assistant", "text": text})
        return NpcReply(id=msg.id, npc=msg.npc, text=text, done=True)

    return handler


async def _handle_client(ws, handler) -> None:
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
                reply_msg = await handler(msg, history)
                await ws.send(reply_msg.model_dump_json())

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
async def serve(host: str = "127.0.0.1", port: int = 8765, *, client_factory=None) -> AsyncIterator:
    """Start the server. If client_factory is None, the handler echoes."""
    handler = _make_handler(client_factory)

    async def per_client(ws):
        await _handle_client(ws, handler)

    server = await websockets.serve(per_client, host, port)
    try:
        yield server
    finally:
        server.close()
        await server.wait_closed()


async def _amain(host: str, port: int, use_llm: bool) -> None:
    factory = llm_mod.make_client if use_llm else None
    async with serve(host, port, client_factory=factory) as server:
        bound_port = server.sockets[0].getsockname()[1]
        log.info("listening on ws://%s:%s (llm=%s)", host, bound_port, use_llm)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--echo", action="store_true", help="Use echo handler instead of LLM.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        asyncio.run(_amain(args.host, args.port, use_llm=not args.echo))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
