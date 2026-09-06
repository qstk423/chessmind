"""SQLite 持久化：对局历史与复盘摘要。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chesscouncil.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                mode TEXT,
                title TEXT,
                result TEXT,
                fen_start TEXT,
                fen_current TEXT,
                pgn TEXT,
                move_count INTEGER DEFAULT 0,
                review_json TEXT,
                meta_json TEXT
            )
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
        if "owner_id" not in cols:
            conn.execute("ALTER TABLE games ADD COLUMN owner_id TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_owner_updated ON games(owner_id, updated_at DESC)"
        )
        conn.commit()


def upsert_game(
    *,
    game_id: str,
    mode: str | None = None,
    title: str | None = None,
    result: str | None = None,
    fen_start: str | None = None,
    fen_current: str | None = None,
    pgn: str | None = None,
    move_count: int | None = None,
    review: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO games (
                    id, created_at, updated_at, mode, title, result,
                    fen_start, fen_current, pgn, move_count, review_json, meta_json, owner_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    now,
                    now,
                    mode,
                    title or f"对局 {game_id[:8]}",
                    result,
                    fen_start,
                    fen_current,
                    pgn,
                    move_count or 0,
                    json.dumps(review, ensure_ascii=False) if review is not None else None,
                    json.dumps(meta, ensure_ascii=False) if meta is not None else None,
                    owner_id,
                ),
            )
        else:
            fields = ["updated_at = ?"]
            values: list[Any] = [now]
            mapping = {
                "mode": mode,
                "title": title,
                "result": result,
                "fen_start": fen_start,
                "fen_current": fen_current,
                "pgn": pgn,
                "move_count": move_count,
                "owner_id": owner_id,
            }
            for k, v in mapping.items():
                if v is not None:
                    fields.append(f"{k} = ?")
                    values.append(v)
            if review is not None:
                fields.append("review_json = ?")
                values.append(json.dumps(review, ensure_ascii=False))
            if meta is not None:
                fields.append("meta_json = ?")
                values.append(json.dumps(meta, ensure_ascii=False))
            values.append(game_id)
            conn.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        return get_game(game_id) or {"id": game_id}


def list_games(limit: int = 30, owner_id: str | None = None) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        if owner_id:
            rows = conn.execute(
                """
                SELECT id, created_at, updated_at, mode, title, result,
                       fen_current, move_count, pgn, owner_id
                FROM games
                WHERE owner_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (owner_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, updated_at, mode, title, result,
                       fen_current, move_count, pgn, owner_id
                FROM games
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_game(game_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    for key in ("review_json", "meta_json"):
        raw = data.get(key)
        if raw:
            try:
                data[key.replace("_json", "")] = json.loads(raw)
            except json.JSONDecodeError:
                data[key.replace("_json", "")] = None
        else:
            data[key.replace("_json", "")] = None
    return data


def adopt_orphan_games(owner_id: str) -> int:
    """将 owner_id 为空的历史记录归属到指定浏览器身份（升级兼容）。"""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE games
            SET owner_id = ?
            WHERE owner_id IS NULL OR owner_id = ''
            """,
            (owner_id,),
        )
        conn.commit()
        return cur.rowcount


def delete_game(game_id: str) -> bool:
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        conn.commit()
        return cur.rowcount > 0
