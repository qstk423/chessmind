import chess

from src.council.review import build_review
from src.xiangqi.review import build_review as build_xq_review
from src.xiangqi.rules import XiangqiGame


def test_chess_key_move_contains_exact_before_after_snapshots():
    board = chess.Board()
    records = []
    for number, uci in enumerate(['e2e4', 'e7e5', 'g1f3'], start=1):
        before = board.fen()
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        board.push(move)
        records.append({'move': {'number': number, 'uci': uci, 'san': san},
                        'fen_before': before, 'fen': board.fen(),
                        'evaluation': {'classification': 'great'}})
    result = build_review(records, game_result=None, pgn='')
    assert len(result['highlights']) == 3
    for h in result['highlights']:
        restored = chess.Board(h['fen_before'])
        restored.push_uci(h['uci'])
        assert restored.fen() == h['fen_after']
    assert records[-1]['fen'] == board.fen()


def test_xiangqi_key_move_snapshot_and_review_do_not_mutate_game():
    game = XiangqiGame()
    game.play_uci('h2h9')  # 炮越过黑炮吃马，产生得子关键着
    current = game.fen()
    history = list(game.history)
    result = build_xq_review(game)
    assert result['highlights']
    h = result['highlights'][0]
    replay = XiangqiGame(h['fen_before'])
    replay.play_uci(h['uci'])
    assert replay.fen() == h['fen_after'] == current
    assert game.fen() == current
    assert game.history == history
