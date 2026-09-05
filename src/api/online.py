"""联机房间 REST + WebSocket。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.rooms import room_manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    name: str = Field(default="玩家", max_length=24)
    color: Literal["white", "black"] = "white"


class JoinRoomRequest(BaseModel):
    name: str = Field(default="玩家", max_length=24)


class RoomMoveRequest(BaseModel):
    token: str
    uci: str


class RoomResetRequest(BaseModel):
    token: str


@router.post("")
async def create_room(req: CreateRoomRequest):
    try:
        data = await room_manager.create(host_name=req.name.strip() or "玩家", host_color=req.color)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"status": "ok", **data}


@router.post("/{room_id}/join")
async def join_room(room_id: str, req: JoinRoomRequest):
    try:
        data = await room_manager.join(room_id, name=req.name.strip() or "玩家")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "ok", **data}


@router.get("/{room_id}")
def get_room(room_id: str):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在或已过期")
    return room.public_state()


@router.post("/{room_id}/move")
async def room_move(room_id: str, req: RoomMoveRequest):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在或已过期")
    result = await room_manager.play_move(room, req.token, req.uci)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await room.broadcast({"type": "move", **result})
    return result


@router.post("/{room_id}/reset")
async def room_reset(room_id: str, req: RoomResetRequest):
    room = room_manager.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在或已过期")
    result = await room_manager.reset_game(room, req.token)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
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
    room.touch()
    await room.broadcast(
        {
            "type": "peer",
            "event": "joined",
            "color": seat.color,
            "name": seat.name,
            "state": room.public_state(),
        }
    )
    await websocket.send_json({"type": "hello", "color": seat.color, "name": seat.name, "state": room.public_state()})

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if mtype == "move":
                uci = (msg.get("uci") or "").strip()
                result = await room_manager.play_move(room, token, uci)
                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                    continue
                payload = {"type": "move", **result}
                await room.broadcast(payload)
                continue
            if mtype == "reset":
                result = await room_manager.reset_game(room, token)
                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                    continue
                await room.broadcast({"type": "reset", **result})
                continue
            if mtype == "sync":
                await websocket.send_json({"type": "state", "state": room.public_state()})
                continue
            await websocket.send_json({"type": "error", "message": f"未知消息: {mtype}"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if seat.ws is websocket:
            seat.ws = None
            seat.connected = False
            room.touch()
            try:
                await room.broadcast(
                    {
                        "type": "peer",
                        "event": "left",
                        "color": seat.color,
                        "name": seat.name,
                        "state": room.public_state(),
                    }
                )
            except Exception:
                pass
