"""将杀杀型识别——供结算动画选用。"""
from __future__ import annotations

import chess

# id → 展示文案（前端也可覆盖）
MATE_CATALOG = {
    "ladder": {
        "id": "ladder",
        "title": "双车错",
        "subtitle": "Ladder Mate",
        "blurb": "双车梯次封锁，王退到边线无路。",
    },
    "back_rank": {
        "id": "back_rank",
        "title": "底线杀",
        "subtitle": "Back-Rank Mate",
        "blurb": "底线被车/后切开，退路被己方堵死。",
    },
    "smothered": {
        "id": "smothered",
        "title": "闷杀",
        "subtitle": "Smothered Mate",
        "blurb": "马步将军，王被己方棋子围死。",
    },
    "queen": {
        "id": "queen",
        "title": "后到功成",
        "subtitle": "Queen Mate",
        "blurb": "后完成绝杀。",
    },
    "checkmate": {
        "id": "checkmate",
        "title": "将死！",
        "subtitle": "Checkmate",
        "blurb": "无路可逃，对局结束。",
    },
    "stalemate": {
        "id": "stalemate",
        "title": "逼和",
        "subtitle": "Stalemate",
        "blurb": "无子可动，和棋。",
    },
    "draw": {
        "id": "draw",
        "title": "和棋",
        "subtitle": "Draw",
        "blurb": "对局以和棋结束。",
    },
}


def _square_name(sq: int) -> str:
    return chess.square_name(sq)


def _attackers(board: chess.Board, color: chess.Color, sq: int) -> list[chess.Piece]:
    return [board.piece_at(a) for a in board.attackers(color, sq) if board.piece_at(a)]


def _king_adjacent_occupied_by_own(board: chess.Board, king_sq: int, color: chess.Color) -> int:
    count = 0
    for d in (-1, 0, 1):
        for f in (-1, 0, 1):
            if d == 0 and f == 0:
                continue
            file = chess.square_file(king_sq) + f
            rank = chess.square_rank(king_sq) + d
            if not (0 <= file <= 7 and 0 <= rank <= 7):
                continue
            sq = chess.square(file, rank)
            p = board.piece_at(sq)
            if p and p.color == color:
                count += 1
    return count


def detect_finale(board: chess.Board) -> dict | None:
    """
    若对局已结束，返回结算动画描述；否则 None。
    字段：id/title/subtitle/blurb/winner/highlight_squares
    """
    if not board.is_game_over():
        return None

    if board.is_stalemate():
        info = dict(MATE_CATALOG["stalemate"])
        info["winner"] = None
        info["result"] = "1/2-1/2"
        info["highlight_squares"] = []
        return info

    if not board.is_checkmate():
        info = dict(MATE_CATALOG["draw"])
        info["winner"] = None
        info["result"] = board.result()
        info["highlight_squares"] = []
        return info

    # 将死：当前行棋方是被将死的一方
    mated = board.turn
    winner = not mated
    king_sq = board.king(mated)
    if king_sq is None:
        info = dict(MATE_CATALOG["checkmate"])
        info["winner"] = "white" if winner == chess.WHITE else "black"
        info["highlight_squares"] = []
        return info

    checkers = list(board.checkers())
    checker_pieces = [board.piece_at(sq) for sq in checkers if board.piece_at(sq)]
    winner_rooks = board.pieces(chess.ROOK, winner)
    highlights = [_square_name(king_sq)] + [_square_name(sq) for sq in checkers]

    # 闷杀：唯一将军子为马，且王周围己方子 ≥ 3
    if (
        len(checker_pieces) == 1
        and checker_pieces[0].piece_type == chess.KNIGHT
        and _king_adjacent_occupied_by_own(board, king_sq, mated) >= 3
    ):
        info = dict(MATE_CATALOG["smothered"])
        info["winner"] = "white" if winner == chess.WHITE else "black"
        info["highlight_squares"] = highlights
        info["result"] = "1-0" if winner == chess.WHITE else "0-1"
        return info

    # 底线杀：王在 1/8 行，将军为车或后且同在底线；相邻「逃离行」有己方子挡住
    kr = chess.square_rank(king_sq)
    if kr in (0, 7) and checker_pieces:
        back = kr
        escape_rank = 1 if kr == 0 else 6
        on_back_checker = False
        for sq, piece in zip(checkers, checker_pieces):
            if piece.piece_type in (chess.ROOK, chess.QUEEN) and chess.square_rank(sq) == back:
                on_back_checker = True
                break
        blocked = 0
        for f in range(8):
            # 王前方三格一带
            if abs(f - chess.square_file(king_sq)) > 1:
                continue
            sq = chess.square(f, escape_rank)
            p = board.piece_at(sq)
            if p and p.color == mated:
                blocked += 1
        if on_back_checker and blocked >= 1:
            info = dict(MATE_CATALOG["back_rank"])
            info["winner"] = "white" if winner == chess.WHITE else "black"
            # 高亮整条底线
            rank_sqs = [_square_name(chess.square(f, back)) for f in range(8)]
            info["highlight_squares"] = list(dict.fromkeys(highlights + rank_sqs))
            info["result"] = "1-0" if winner == chess.WHITE else "0-1"
            return info

    # 双车错 / 梯子杀：胜方≥2车，王在边线，两车分居不同行或不同列，且至少一车正在将军
    if len(winner_rooks) >= 2:
        on_edge = (
            chess.square_file(king_sq) in (0, 7)
            or chess.square_rank(king_sq) in (0, 7)
        )
        rook_checkers = [
            sq
            for sq in checkers
            if board.piece_at(sq) and board.piece_at(sq).piece_type == chess.ROOK
        ]
        ranks = {chess.square_rank(sq) for sq in winner_rooks}
        files = {chess.square_file(sq) for sq in winner_rooks}
        ladder_geo = len(ranks) >= 2 or len(files) >= 2
        if on_edge and rook_checkers and ladder_geo:
            info = dict(MATE_CATALOG["ladder"])
            info["winner"] = "white" if winner == chess.WHITE else "black"
            info["highlight_squares"] = list(
                dict.fromkeys(highlights + [_square_name(sq) for sq in winner_rooks])
            )
            info["result"] = "1-0" if winner == chess.WHITE else "0-1"
            return info

    # 后杀
    if checker_pieces and all(p.piece_type == chess.QUEEN for p in checker_pieces):
        info = dict(MATE_CATALOG["queen"])
        info["winner"] = "white" if winner == chess.WHITE else "black"
        info["highlight_squares"] = highlights
        info["result"] = "1-0" if winner == chess.WHITE else "0-1"
        return info

    info = dict(MATE_CATALOG["checkmate"])
    info["winner"] = "white" if winner == chess.WHITE else "black"
    info["highlight_squares"] = highlights
    info["result"] = "1-0" if winner == chess.WHITE else "0-1"
    return info


def detect_finale_from_fen(fen: str) -> dict | None:
    try:
        return detect_finale(chess.Board(fen))
    except ValueError:
        return None
