"""联机 REST + WebSocket。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.xiangqi.rooms import room_manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    name: str = Field(default="玩家", max_length=24)
    color: str = "red"


class JoinRoomRequest(BaseModel):
    name: str = Field(default="玩家", max_length=24)


class RoomMoveRequest(BaseModel):
    token: str
    uci: str


class RoomResetRequest(BaseModel):
    token: str


@router.post("")
def create_room(req: CreateRoomRequest):
    color = "red" if req.color not in {"red", "black"} else req.color
    return {"status": "ok", **room_manager.create(req.name.strip() or "玩家", color)}


@router.post("/{room_id}/join")
def join_room(room_id: str, req: JoinRoomRequest):
    try:
        data = room_manager.join(room_id, req.name.strip() or "玩家")
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "ok", **data}


@router.get("/{room_id}")
def get_room(room_id: str):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(404, "房间不存在")
    return room.public_state()


@router.post("/{room_id}/move")
async def room_move(room_id: str, req: RoomMoveRequest):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(404, "房间不存在")
    result = room_manager.play_move(room, req.token, req.uci)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await room.broadcast({"type": "move", **result})
    return result


@router.post("/{room_id}/reset")
async def room_reset(room_id: str, req: RoomResetRequest):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(404, "房间不存在")
    result = room_manager.reset(room, req.token)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await room.broadcast({"type": "reset", **result})
    return result


@router.websocket("/{room_id}/ws")
async def room_ws(websocket: WebSocket, room_id: str, token: str = Query(...)):
    room = room_manager.get(room_id)
    if not room:
        await websocket.close(code=4404)
        return
    seat = room.seat_by_token(token)
    if not seat:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    seat.ws = websocket
    seat.connected = True
    await room.broadcast(
        {
            "type": "peer",
            "event": "joined",
            "color": seat.color,
            "name": seat.name,
            "state": room.public_state(),
        }
    )
    await websocket.send_json(
        {"type": "hello", "color": seat.color, "name": seat.name, "state": room.public_state()}
    )
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "move":
                result = room_manager.play_move(room, token, (msg.get("uci") or "").strip())
                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                else:
                    await room.broadcast({"type": "move", **result})
            elif mtype == "reset":
                result = room_manager.reset(room, token)
                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                else:
                    await room.broadcast({"type": "reset", **result})
    except WebSocketDisconnect:
        seat.connected = False
        seat.ws = None
        await room.broadcast(
            {
                "type": "peer",
                "event": "left",
                "color": seat.color,
                "name": seat.name,
                "state": room.public_state(),
            }
        )
