"""中国象棋规则：走法、将军、绝杀、FEN。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable

START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
PIECE_NAMES = {
    "R": "车", "N": "马", "B": "相", "A": "仕", "K": "帅", "C": "炮", "P": "兵",
    "r": "车", "n": "马", "b": "象", "a": "士", "k": "将", "c": "炮", "p": "卒",
}


VALID_PIECES = set("RNBAKCPrnbakcp")


@dataclass(frozen=True)
class Move:
    fr: int
    fc: int
    tr: int
    tc: int

    @property
    def uci(self) -> str:
        return f"{chr(97 + self.fc)}{9 - self.fr}{chr(97 + self.tc)}{9 - self.tr}"

    @classmethod
    def from_uci(cls, uci: str) -> "Move":
        uci = (uci or "").strip().lower()
        if len(uci) != 4:
            raise ValueError("非法着法编码")
        if uci[0] not in "abcdefghi" or uci[2] not in "abcdefghi":
            raise ValueError("非法着法编码")
        if not (uci[1].isdigit() and uci[3].isdigit()):
            raise ValueError("非法着法编码")
        fc, tc = ord(uci[0]) - 97, ord(uci[2]) - 97
        fr, tr = 9 - int(uci[1]), 9 - int(uci[3])
        if not (0 <= fr < 10 and 0 <= tr < 10 and 0 <= fc < 9 and 0 <= tc < 9):
            raise ValueError("格子越界")
        return cls(fr, fc, tr, tc)


def empty_board() -> list[list[str | None]]:
    return [[None for _ in range(9)] for _ in range(10)]


def parse_fen(fen: str) -> tuple[list[list[str | None]], str, int, int]:
    parts = fen.strip().split()
    if len(parts) < 2:
        raise ValueError("FEN 不完整")
    side_token = parts[1].lower()
    if side_token not in {"w", "b", "r", "red", "black"}:
        raise ValueError("行棋方非法")
    rows = parts[0].split("/")
    if len(rows) != 10:
        raise ValueError("FEN 行数错误")
    board = empty_board()
    for r, row in enumerate(rows):
        c = 0
        for ch in row:
            if ch.isdigit():
                c += int(ch)
                if c > 9:
                    raise ValueError("FEN 列数错误")
            else:
                if ch not in VALID_PIECES:
                    raise ValueError(f"非法棋子字符: {ch}")
                if c >= 9:
                    raise ValueError("FEN 列数错误")
                board[r][c] = ch
                c += 1
        if c != 9:
            raise ValueError("FEN 列数错误")
    red_k = sum(1 for r in range(10) for c in range(9) if board[r][c] == "K")
    black_k = sum(1 for r in range(10) for c in range(9) if board[r][c] == "k")
    if red_k != 1 or black_k != 1:
        raise ValueError("局面必须恰好各有一枚帅/将")
    turn = "red" if side_token.startswith("w") or side_token in {"r", "red"} else "black"
    half = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    full = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 1
    if half < 0 or full < 1:
        raise ValueError("半回合/回合计数非法")
    # 将帅须在九宫
    rk = find_king(board, "red")
    bk = find_king(board, "black")
    if not rk or not palace_ok("red", rk[0], rk[1]):
        raise ValueError("红帅不在九宫")
    if not bk or not palace_ok("black", bk[0], bk[1]):
        raise ValueError("黑将不在九宫")
    return board, turn, half, full


def board_to_fen(board, turn: str, halfmove: int = 0, fullmove: int = 1) -> str:
    rows = []
    for r in range(10):
        empty = 0
        out = []
        for c in range(9):
            p = board[r][c]
            if not p:
                empty += 1
            else:
                if empty:
                    out.append(str(empty))
                    empty = 0
                out.append(p)
        if empty:
            out.append(str(empty))
        rows.append("".join(out))
    side = "w" if turn == "red" else "b"
    return f"{'/'.join(rows)} {side} - - {halfmove} {fullmove}"


def color_of(piece: str | None) -> str | None:
    if not piece:
        return None
    return "red" if piece.isupper() else "black"


def in_board(r: int, c: int) -> bool:
    return 0 <= r < 10 and 0 <= c < 9


def find_king(board, color: str) -> tuple[int, int] | None:
    target = "K" if color == "red" else "k"
    for r in range(10):
        for c in range(9):
            if board[r][c] == target:
                return r, c
    return None


def count_between(board, fr: int, fc: int, tr: int, tc: int) -> int:
    count = 0
    if fr == tr:
        a, b = sorted((fc, tc))
        for c in range(a + 1, b):
            if board[fr][c]:
                count += 1
    elif fc == tc:
        a, b = sorted((fr, tr))
        for r in range(a + 1, b):
            if board[r][fc]:
                count += 1
    return count


def palace_ok(color: str, r: int, c: int) -> bool:
    if not (3 <= c <= 5):
        return False
    return (7 <= r <= 9) if color == "red" else (0 <= r <= 2)


def pseudo_legal(board, fr: int, fc: int, tr: int, tc: int) -> bool:
    if not in_board(tr, tc):
        return False
    piece = board[fr][fc]
    if not piece:
        return False
    target = board[tr][tc]
    side = color_of(piece)
    if color_of(target) == side:
        return False
    t = piece.lower()
    dr, dc = tr - fr, tc - fc
    ar, ac = abs(dr), abs(dc)

    if t == "r":
        return (dr == 0 or dc == 0) and count_between(board, fr, fc, tr, tc) == 0
    if t == "c":
        if dr != 0 and dc != 0:
            return False
        screens = count_between(board, fr, fc, tr, tc)
        return screens == 1 if target else screens == 0
    if t == "n":
        if not ((ar == 2 and ac == 1) or (ar == 1 and ac == 2)):
            return False
        leg_r = fr + (dr // 2 if ar == 2 else 0)
        leg_c = fc + (dc // 2 if ac == 2 else 0)
        return board[leg_r][leg_c] is None
    if t == "b":
        if ar != 2 or ac != 2:
            return False
        if side == "red" and tr < 5:
            return False
        if side == "black" and tr > 4:
            return False
        return board[fr + dr // 2][fc + dc // 2] is None
    if t == "a":
        return ar == 1 and ac == 1 and palace_ok(side, tr, tc)
    if t == "k":
        return ar + ac == 1 and palace_ok(side, tr, tc)
    if t == "p":
        forward = -1 if side == "red" else 1
        if dr == forward and dc == 0:
            return True
        crossed = fr <= 4 if side == "red" else fr >= 5
        return crossed and dr == 0 and ac == 1
    return False


def apply_raw(board, move: Move):
    piece = board[move.fr][move.fc]
    captured = board[move.tr][move.tc]
    board[move.tr][move.tc] = piece
    board[move.fr][move.fc] = None
    return piece, captured


def undo_raw(board, move: Move, piece: str, captured):
    board[move.fr][move.fc] = piece
    board[move.tr][move.tc] = captured


def flying_generals(board) -> bool:
    red = find_king(board, "red")
    black = find_king(board, "black")
    if not red or not black:
        return False
    if red[1] != black[1]:
        return False
    return count_between(board, red[0], red[1], black[0], black[1]) == 0


def attacks_square(board, color: str, tr: int, tc: int) -> bool:
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if color_of(p) != color:
                continue
            if pseudo_legal(board, r, c, tr, tc):
                # 将帅照面只算直线无阻隔时的“攻击”
                if p.lower() == "k":
                    if c == tc and count_between(board, r, c, tr, tc) == 0:
                        return True
                    continue
                return True
    return False


def in_check(board, color: str) -> bool:
    king = find_king(board, color)
    if not king:
        return True
    if flying_generals(board):
        return True
    enemy = "black" if color == "red" else "red"
    return attacks_square(board, enemy, king[0], king[1])


def is_legal(board, move: Move, turn: str) -> bool:
    piece = board[move.fr][move.fc]
    if color_of(piece) != turn:
        return False
    if not pseudo_legal(board, move.fr, move.fc, move.tr, move.tc):
        return False
    piece, captured = apply_raw(board, move)
    ok = not in_check(board, turn) and not flying_generals(board)
    undo_raw(board, move, piece, captured)
    return ok


def iter_moves(board, turn: str) -> Iterable[Move]:
    for r in range(10):
        for c in range(9):
            if color_of(board[r][c]) != turn:
                continue
            for tr in range(10):
                for tc in range(9):
                    mv = Move(r, c, tr, tc)
                    if is_legal(board, mv, turn):
                        yield mv


def legal_moves(board, turn: str) -> list[Move]:
    return list(iter_moves(board, turn))


def legal_targets(board, turn: str, fr: int, fc: int) -> list[tuple[int, int]]:
    out = []
    for mv in legal_moves(board, turn):
        if mv.fr == fr and mv.fc == fc:
            out.append((mv.tr, mv.tc))
    return out


def move_san(board, move: Move) -> str:
    piece = board[move.fr][move.fc]
    name = PIECE_NAMES.get(piece or "", "?")
    capture = "x" if board[move.tr][move.tc] else "-"
    return f"{name}{chr(97 + move.fc)}{9 - move.fr}{capture}{chr(97 + move.tc)}{9 - move.tr}"


def evaluate_material(board) -> int:
    values = {"k": 10000, "r": 900, "c": 450, "n": 400, "b": 200, "a": 200, "p": 100}
    score = 0
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if not p:
                continue
            v = values.get(p.lower())
            if v is None:
                continue
            score += v if p.isupper() else -v
    return score


def position_key_from_fen(fen: str) -> str:
    """局面键：棋子布局 + 行棋方（忽略半步/手数）。"""
    parts = (fen or "").split()
    if len(parts) < 2:
        return fen
    return f"{parts[0]} {parts[1]}"


class XiangqiGame:
    def __init__(self, fen: str = START_FEN):
        self.reset(fen)

    def reset(self, fen: str = START_FEN):
        self.board, self.turn, self.halfmove, self.fullmove = parse_fen(fen)
        self.history: list[dict] = []
        self.result: str | None = None
        self._refresh_result()

    def fen(self) -> str:
        return board_to_fen(self.board, self.turn, self.halfmove, self.fullmove)

    def position_key(self) -> str:
        return position_key_from_fen(self.fen())

    def snapshot(self) -> dict:
        moves = legal_moves(self.board, self.turn) if not self.result else []
        return {
            "fen": self.fen(),
            "turn": self.turn,
            "in_check": in_check(self.board, self.turn) if not self.result else False,
            "is_game_over": bool(self.result),
            "result": self.result,
            "move_count": len(self.history),
            "moves": deepcopy(self.history),
            "legal_uci": [m.uci for m in moves],
            "board": deepcopy(self.board),
        }

    def play_uci(self, uci: str) -> dict:
        if self.result:
            raise ValueError("对局已结束")
        move = Move.from_uci(uci)
        if not is_legal(self.board, move, self.turn):
            raise ValueError("非法着法")
        san = move_san(self.board, move)
        half_before = self.halfmove
        full_before = self.fullmove
        piece, captured = apply_raw(self.board, move)
        entry = {
            "uci": move.uci,
            "san": san,
            "piece": piece,
            "captured": captured,
            "color": self.turn,
            "from": [move.fr, move.fc],
            "to": [move.tr, move.tc],
            "fen_before": board_to_fen(self.board, self.turn),  # already applied; fix below
        }
        # fen_before was wrong; recompute properly by undoing temporarily
        undo_raw(self.board, move, piece, captured)
        fen_before = self.fen()
        apply_raw(self.board, move)
        entry["fen_before"] = fen_before

        if captured or piece.lower() == "p":
            self.halfmove = 0
        else:
            self.halfmove += 1
        if self.turn == "black":
            self.fullmove += 1
        entry["halfmove_before"] = half_before
        entry["fullmove_before"] = full_before
        self.turn = "black" if self.turn == "red" else "red"
        entry["gave_check"] = in_check(self.board, self.turn)
        entry["fen"] = self.fen()
        self.history.append(entry)
        self._refresh_result()
        return entry

    def undo(self) -> dict | None:
        if not self.history:
            return None
        last = self.history.pop()
        fr, fc = last["from"]
        tr, tc = last["to"]
        self.board[fr][fc] = last["piece"]
        self.board[tr][tc] = last["captured"]
        self.turn = last["color"]
        if "halfmove_before" in last:
            self.halfmove = last["halfmove_before"]
        if "fullmove_before" in last:
            self.fullmove = last["fullmove_before"]
        elif self.turn == "black" and self.fullmove > 1:
            self.fullmove -= 1
        self.result = None
        self._refresh_result()
        return last

    def _refresh_result(self):
        moves = legal_moves(self.board, self.turn)
        if not moves:
            # 中国象棋：无子可动方判负（困毙），并非国际象棋式逼和
            winner = "黑方" if self.turn == "red" else "红方"
            if in_check(self.board, self.turn):
                self.result = f"{winner}胜 · 绝杀"
            else:
                self.result = f"{winner}胜 · 困毙"
            return

        # 长将优先于普通重复，否则循环局面会先被误判为三次重复和棋。
        if self.history:
            last_color = self.history[-1]["color"]
            streak = 0
            for e in reversed(self.history):
                if e.get("color") != last_color:
                    continue
                if e.get("gave_check"):
                    streak += 1
                else:
                    break
            if streak >= 4:
                winner = "黑方" if last_color == "red" else "红方"
                self.result = f"{winner}胜 · 长将"
                return

        # 排除长将后，三次重复局面 → 和棋（MVP）
        key = self.position_key()
        repeats = sum(1 for e in self.history if position_key_from_fen(e.get("fen", "")) == key)
        if repeats >= 3:
            self.result = "和棋 · 重复局面"
            return

        self.result = None

    def targets_for(self, fr: int, fc: int) -> list[str]:
        return [Move(fr, fc, tr, tc).uci[2:] for tr, tc in legal_targets(self.board, self.turn, fr, fc)]
