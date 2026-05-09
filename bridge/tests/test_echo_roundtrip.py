import asyncio
import json

import pytest
import websockets

from bridge.server import serve


@pytest.mark.asyncio
async def test_echo_roundtrip():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({
                "type": "npc_interact",
                "v": 1,
                "id": "test-1",
                "npc": "Robin",
                "player": "Alex",
                "location": "Town",
                "ts": 1715251200,
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)

    msg = json.loads(raw)
    assert msg["type"] == "npc_reply"
    assert msg["id"] == "test-1"
    assert msg["npc"] == "Robin"
    assert "Robin" in msg["text"]


@pytest.mark.asyncio
async def test_session_reset_no_reply():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({
                "type": "session_reset",
                "v": 1,
                "reason": "returned_to_title",
            }))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), timeout=0.3)


@pytest.mark.asyncio
async def test_unknown_type_ignored_no_disconnect():
    async with serve(host="127.0.0.1", port=0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({"type": "mystery", "v": 1}))
            # then a real message; if the unknown one had killed the connection,
            # this would raise ConnectionClosed.
            await ws.send(json.dumps({
                "type": "npc_interact",
                "v": 1,
                "id": "test-2",
                "npc": "Lewis",
                "player": "Alex",
                "location": "Town",
                "ts": 1,
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
    assert json.loads(raw)["id"] == "test-2"
