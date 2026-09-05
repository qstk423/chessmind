"""FEN 纠错工具：修改格子棋子 / 行棋方。"""
from __future__ import annotations

import chess


PIECE_MAP = {
    "K": chess.Piece.from_symbol("K"),
    "Q": chess.Piece.from_symbol("Q"),
    "R": chess.Piece.from_symbol("R"),
    "B": chess.Piece.from_symbol("B"),
    "N": chess.Piece.from_symbol("N"),
    "P": chess.Piece.from_symbol("P"),
    "k": chess.Piece.from_symbol("k"),
    "q": chess.Piece.from_symbol("q"),
    "r": chess.Piece.from_symbol("r"),
    "b": chess.Piece.from_symbol("b"),
    "n": chess.Piece.from_symbol("n"),
    "p": chess.Piece.from_symbol("p"),
}


def board_grid(fen: str) -> dict:
    """返回 64 格符号矩阵，供前端纠错面板使用。"""
    board = chess.Board(fen)
    squares = {}
    for sq in chess.SQUARES:
        name = chess.square_name(sq)
        piece = board.piece_at(sq)
        squares[name] = piece.symbol() if piece else ""
    return {
        "fen": board.fen(),
        "turn": "w" if board.turn == chess.WHITE else "b",
        "squares": squares,
        "is_valid": True,
    }


def set_square_piece(fen: str, square: str, piece_symbol: str | None) -> dict:
    """
    设置某格棋子。piece_symbol 为空 / '.' / '-' 表示清空。
    返回新 FEN；非法则 error。
    """
    try:
        board = chess.Board(fen)
        sq = chess.parse_square(square)
    except (ValueError, AttributeError) as e:
        return {"error": f"非法坐标或 FEN：{e}"}

    sym = (piece_symbol or "").strip()
    if sym in ("", "-", "empty", "."):
        board.remove_piece_at(sq)
    else:
        piece = PIECE_MAP.get(sym)
        if piece is None:
            return {"error": f"未知棋子符号：{sym}（用 KQRBNPkqrbnp）"}
        board.set_piece_at(sq, piece)

    # 清除可能失效的易位/吃过路兵，保持可解析
    try:
        # python-chess 在随意摆子后可能仍给出 FEN
        new_fen = board.fen()
        # 再 parse 一次确保合法棋盘字符串
        chess.Board(new_fen)
        return {"fen": new_fen, "grid": board_grid(new_fen)}
    except ValueError as e:
        return {"error": f"修改后局面非法：{e}"}


def set_turn(fen: str, turn: str) -> dict:
    t = turn.strip().lower()
    side = "w" if t in ("w", "white") else "b" if t in ("b", "black") else None
    if not side:
        return {"error": "turn 必须是 w/b"}
    parts = fen.split()
    if len(parts) < 2:
        return {"error": "FEN 不完整"}
    parts[1] = side
    new_fen = " ".join(parts)
    try:
        board = chess.Board(new_fen)
        return {"fen": board.fen(), "grid": board_grid(board.fen())}
    except ValueError as e:
        return {"error": f"非法 FEN：{e}"}
