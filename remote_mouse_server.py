import asyncio
import json
import os
import websockets

# Store pending pairing rooms: { "123456": websocket }
rooms = {}


async def handler(websocket):
    current_room = None
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            code = data.get("code")

            # 1. Student creates room
            if msg_type == "create_room":
                rooms[code] = websocket
                current_room = code
                await websocket.send(json.dumps({"status": "room_created"}))

            # 2. Teacher joins room
            elif msg_type == "join_room":
                if code in rooms:
                    partner = rooms[code]
                    current_room = code
                    # Notify both sides that peer is ready
                    await partner.send(json.dumps({"type": "peer_connected"}))
                    await websocket.send(json.dumps({"type": "peer_connected"}))
                else:
                    await websocket.send(json.dumps({"error": "invalid_code"}))

            # 3. Relay WebRTC signaling data (offer, answer, ICE candidates)
            elif msg_type == "signal":
                if current_room in rooms:
                    # Forward to the other party
                    target = (
                        rooms[current_room]
                        if websocket != rooms[current_room]
                        else None
                    )
                    if target:
                        await target.send(json.dumps(data))

    except Exception:
        pass
    finally:
        # Clean up on disconnect
        if current_room and current_room in rooms and rooms[current_room] == websocket:
            del rooms[current_room]


async def main():
    # Render assigns a dynamic port via environment variable
    port = int(os.environ.get("PORT", 10000))
    async with websockets.serve(handler, "0.0.0.0", port):
        print(f"Signaling server running on port {port}")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
