#!/usr/bin/env python3

from __future__ import annotations

import argparse
import random
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from magnet_knights_logic import (
    BLACK,
    ENGINE_BRUTE,
    WHITE,
    agent_move,
    apply_move,
    default_state,
    difficulty_names,
    engine_names,
    get_legal_moves,
)
from magnet_knights_selfplay import feature_row


def run_single_game(
    game_id: int,
    white_engine: str,
    black_engine: str,
    white_difficulty: str,
    black_difficulty: str,
    variant: str,
    max_plies: int,
) -> Tuple[str | None, List[Dict[str, object]], Dict[str, List[float]]]:
    white_gap = 2
    black_gap = 2
    state = default_state(white_gap=white_gap, black_gap=black_gap, variant=variant)
    rows: List[Dict[str, object]] = []
    timings: Dict[str, List[float]] = defaultdict(list)
    ply = 0

    while state.winner() is None and ply < max_plies:
        legal = get_legal_moves(state)
        if not legal:
            break

        engine = white_engine if state.side_to_move == WHITE else black_engine
        difficulty = white_difficulty if state.side_to_move == WHITE else black_difficulty
        start = time.perf_counter()
        move = agent_move(state, difficulty=difficulty, engine=engine)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timings[engine].append(elapsed_ms)
        rows.append(feature_row(game_id, ply, state, move, engine, difficulty, white_gap, black_gap))
        state = apply_move(state, move)
        ply += 1

    winner = state.winner()
    for row in rows:
        row["winner"] = "" if winner is None else winner
        row["outcome_for_mover"] = 1 if winner == row["side"] else (-1 if winner else 0)
    return winner, rows, timings


def engine_for_winner(winner: str | None, white_engine: str, black_engine: str) -> str:
    if winner == WHITE:
        return white_engine
    if winner == BLACK:
        return black_engine
    return "draw"


def summarize_matchup(
    white_engine: str,
    black_engine: str,
    white_difficulty: str,
    black_difficulty: str,
    variant: str,
    games: int,
    max_plies: int,
) -> None:
    win_counts: Dict[str, int] = defaultdict(int)
    color_wins: Dict[Tuple[str, str], int] = defaultdict(int)
    feature_rows: List[Dict[str, object]] = []
    timings: Dict[str, List[float]] = defaultdict(list)

    for game_id in range(games):
        winner, rows, game_timings = run_single_game(
            game_id=game_id,
            white_engine=white_engine,
            black_engine=black_engine,
            white_difficulty=white_difficulty,
            black_difficulty=black_difficulty,
            variant=variant,
            max_plies=max_plies,
        )
        feature_rows.extend(rows)
        winning_engine = engine_for_winner(winner, white_engine, black_engine)
        win_counts[winning_engine] += 1
        if winner == WHITE:
            color_wins[(white_engine, "white")] += 1
        elif winner == BLACK:
            color_wins[(black_engine, "black")] += 1
        for engine, values in game_timings.items():
            timings[engine].extend(values)

    print(f"Matchup: white={white_engine}/{white_difficulty} black={black_engine}/{black_difficulty} variant={variant} games={games}")
    print("Game wins:")
    for engine in sorted({white_engine, black_engine, "draw"}):
        print(f"- {engine}: {win_counts.get(engine, 0)}")
    print("Wins by engine/color:")
    for key in sorted(color_wins):
        engine, color = key
        print(f"- {engine} as {color}: {color_wins[key]}")
    print("Move feature rates:")
    for engine in sorted({white_engine, black_engine}):
        rows = [row for row in feature_rows if row["engine"] == engine]
        if not rows:
            continue
        print(f"- {engine}: rows={len(rows)}")
        for feature in ("move_is_score", "move_stops_opp_immediate_score", "move_captures_home_knight"):
            positives = [row for row in rows if int(row[feature]) == 1]
            rate = len(positives) / len(rows)
            print(f"  {feature} rate={rate:.3f} count={len(positives)}")
    print("Latency:")
    for engine in sorted(timings):
        values = timings[engine]
        mean_ms = sum(values) / len(values)
        print(f"- {engine}: mean={mean_ms:.2f}ms moves={len(values)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Magnet Knights engines head to head.")
    parser.add_argument("--engine-a", choices=engine_names(), default=ENGINE_BRUTE)
    parser.add_argument("--engine-b", choices=engine_names(), required=True)
    parser.add_argument("--difficulty-a", choices=difficulty_names(), default="hard")
    parser.add_argument("--difficulty-b", choices=difficulty_names(), default="hard")
    parser.add_argument("--variant", choices=["standard", "respawn"], default="standard")
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    random.seed(args.seed)
    summarize_matchup(
        white_engine=args.engine_a,
        black_engine=args.engine_b,
        white_difficulty=args.difficulty_a,
        black_difficulty=args.difficulty_b,
        variant=args.variant,
        games=args.games,
        max_plies=args.max_plies,
    )
    summarize_matchup(
        white_engine=args.engine_b,
        black_engine=args.engine_a,
        white_difficulty=args.difficulty_b,
        black_difficulty=args.difficulty_a,
        variant=args.variant,
        games=args.games,
        max_plies=args.max_plies,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
