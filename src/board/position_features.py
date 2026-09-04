"""局面特征提取——把 python-chess 可确定的事实序列化为文本，供 Agent 接地（grounding）使用。

大模型直接读 FEN 极不可靠（行序、清点棋子都常出错），
这里把确定性事实（子力、悬子、兵形、王安全、中心、开放线）
提取为结构化文本，连同引擎评估一起注入 Agent 的提示词，
让 LLM 的分析建立在真实数据之上，而非凭空想象棋盘。
"""
import chess

PIECE_ZH = {
    chess.PAWN: "兵",
    chess.KNIGHT: "马",
    chess.BISHOP: "象",
    chess.ROOK: "车",
    chess.QUEEN: "后",
    chess.KING: "王",
}
PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def _side(color: chess.Color) -> str:
    return "白" if color == chess.WHITE else "黑"


def _material(board: chess.Board) -> str:
    """双方子力清点与价值差"""
    counts = []
    w_total = b_total = 0
    for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        w = len(board.pieces(pt, chess.WHITE))
        b = len(board.pieces(pt, chess.BLACK))
        w_total += w * PIECE_VALUE[pt]
        b_total += b * PIECE_VALUE[pt]
        if w or b:
            counts.append(f"{PIECE_ZH[pt]}白{w}/黑{b}")
    diff = w_total - b_total
    if diff == 0:
        verdict = "子力均等"
    else:
        verdict = f"{'白' if diff > 0 else '黑'}方多{abs(diff)}兵价值"
    return "，".join(counts) + f"（{verdict}）"


def _piece_list(board: chess.Board) -> str:
    """每个棋子的种类和位置清单"""
    lines = []
    for color in (chess.WHITE, chess.BLACK):
        items = [
            f"{PIECE_ZH[p.piece_type]}{chess.square_name(sq)}"
            for sq, p in sorted(board.piece_map().items())
            if p.color == color
        ]
        lines.append(f"{_side(color)}方棋子：{' '.join(items) if items else '无'}")
    return "\n".join(lines)


def _tactical_facts(board: chess.Board) -> list[str]:
    """悬子与将军（不含王，王被攻击即将军，单独报告）"""
    facts = []
    if board.is_check():
        facts.append(f"{_side(board.turn)}方被将军")
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        for sq, piece in sorted(board.piece_map().items()):
            if piece.color != color or piece.piece_type == chess.KING:
                continue
            attackers = board.attackers(enemy, sq)
            if not attackers:
                continue
            defended = bool(board.attackers(color, sq))
            min_attacker_val = min(PIECE_VALUE[board.piece_type_at(s)] for s in attackers)
            name = f"{_side(color)}方{PIECE_ZH[piece.piece_type]}（{chess.square_name(sq)}）"
            if not defended:
                facts.append(f"{name}被攻击且无保护")
            elif min_attacker_val < PIECE_VALUE[piece.piece_type]:
                facts.append(f"{name}被更低价子攻击")
    return facts


def _pawn_facts(board: chess.Board) -> list[str]:
    """叠兵、孤兵、通路兵"""
    facts = []
    for color in (chess.WHITE, chess.BLACK):
        side = _side(color)
        pawns = [
            sq for sq, p in board.piece_map().items()
            if p.piece_type == chess.PAWN and p.color == color
        ]
        files = sorted({chess.square_file(sq) for sq in pawns})

        doubled = [
            chess.FILE_NAMES[f] for f in files
            if sum(1 for sq in pawns if chess.square_file(sq) == f) > 1
        ]
        isolated = [
            chess.FILE_NAMES[f] for f in files
            if (f - 1) not in files and (f + 1) not in files
        ]
        enemy_pawns = [
            (chess.square_file(sq), chess.square_rank(sq))
            for sq, p in board.piece_map().items()
            if p.piece_type == chess.PAWN and p.color != color
        ]
        passed = []
        for sq in pawns:
            f, r = chess.square_file(sq), chess.square_rank(sq)
            blocked = any(
                ef in (f - 1, f, f + 1) and (er > r if color == chess.WHITE else er < r)
                for ef, er in enemy_pawns
            )
            if not blocked:
                passed.append(chess.square_name(sq))

        if doubled:
            facts.append(f"{side}方叠兵：{'/'.join(doubled)}线")
        if isolated:
            facts.append(f"{side}方孤兵：{'/'.join(isolated)}线")
        if passed:
            facts.append(f"{side}方通路兵：{'/'.join(passed)}")
    return facts


def _king_facts(board: chess.Board) -> list[str]:
    """王的位置、易位状态"""
    facts = []
    for color in (chess.WHITE, chess.BLACK):
        side = _side(color)
        k = board.king(color)
        if k is None:
            facts.append(f"{side}方王不在棋盘上")
            continue
        ksq = chess.square_name(k)
        home_rank = 0 if color == chess.WHITE else 7
        castled = (
            chess.square_file(k) in (2, 6)
            and chess.square_rank(k) == home_rank
        )
        rights = []
        if board.has_kingside_castling_rights(color):
            rights.append("王翼")
        if board.has_queenside_castling_rights(color):
            rights.append("后翼")
        if castled:
            facts.append(f"{side}方王已易位（{ksq}）")
        elif rights:
            facts.append(f"{side}方王未易位（{ksq}），保留{'/'.join(rights)}易位权")
        else:
            facts.append(f"{side}方王未易位（{ksq}），已无易位权")
    return facts


def _center_facts(board: chess.Board) -> list[str]:
    """d4/d5/e4/e5 中心格控制"""
    facts = []
    for name, sq in (("d4", chess.D4), ("d5", chess.D5), ("e4", chess.E4), ("e5", chess.E5)):
        w = board.is_attacked_by(chess.WHITE, sq)
        b = board.is_attacked_by(chess.BLACK, sq)
        if w and not b:
            facts.append(f"{name}格白方控制")
        elif b and not w:
            facts.append(f"{name}格黑方控制")
        elif w and b:
            facts.append(f"{name}格双方争夺")
    return facts


def _file_facts(board: chess.Board) -> list[str]:
    """开放线与半开放线"""
    facts = []
    for f in range(8):
        name = chess.FILE_NAMES[f]
        wp = any(
            p.piece_type == chess.PAWN and p.color == chess.WHITE and chess.square_file(sq) == f
            for sq, p in board.piece_map().items()
        )
        bp = any(
            p.piece_type == chess.PAWN and p.color == chess.BLACK and chess.square_file(sq) == f
            for sq, p in board.piece_map().items()
        )
        if not wp and not bp:
            facts.append(f"{name}线开放")
        elif not wp:
            facts.append(f"{name}线对白方半开放")
        elif not bp:
            facts.append(f"{name}线对黑方半开放")
    return facts


def describe_position(board: chess.Board, engine_eval: dict | None = None) -> str:
    """生成局面结构化描述（全部为程序计算的确定性事实，非 LLM 推测）"""
    turn = _side(board.turn)
    sections = []

    status = f"轮到{turn}方走棋"
    if board.is_check():
        status += f"，{turn}方被将军"
    sections.append(status)

    sections.append("【子力】" + _material(board))
    sections.append("【棋子位置】\n" + _piece_list(board))

    tactical = _tactical_facts(board)
    sections.append("【战术要点】" + ("；".join(tactical) if tactical else "无悬子/直接威胁"))

    pawns = _pawn_facts(board)
    sections.append("【兵形】" + ("；".join(pawns) if pawns else "双方兵形正常"))

    sections.append("【王安全】" + "；".join(_king_facts(board)))

    center = _center_facts(board)
    sections.append("【中心控制】" + ("；".join(center) if center else "中心暂无人控制"))

    files = _file_facts(board)
    sections.append("【线路】" + ("；".join(files) if files else "暂无开放/半开放线"))

    if engine_eval:
        score = engine_eval["score_cp"]
        if engine_eval.get("is_mate"):
            who = "白" if score > 0 else "黑"
            eval_text = f"{who}方将杀已不可阻挡（还差 {engine_eval.get('mate_in')} 步）"
        else:
            eval_text = (
                f"白方视角 {score:+d}cp，"
                f"白方胜率 {engine_eval['win_prob_white'] * 100:.0f}%"
            )
        line = f"【Stockfish 引擎】{eval_text}"
        pv = " ".join(engine_eval.get("pv", []))
        if pv:
            line += f"；引擎最佳续着：{pv}"
        sections.append(line)

    return "\n".join(sections)
