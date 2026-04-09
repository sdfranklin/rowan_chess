#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List

from magnet_knights_logic import (
    AI_PROFILES,
    BLACK,
    ENGINE_BRUTE,
    ENGINE_RACE,
    LEARNED_FEATURE_NAMES,
    LEARNED_FEATURE_SCHEMA_VERSION,
    KNIGHT,
    PAWN,
    VARIANT_RESPAWN,
    VARIANT_STANDARD,
    WHITE,
    agent_move,
    apply_move,
    count_home_knights_on_board,
    count_unscored_knights,
    capped_turns_to_score,
    default_state,
    difficulty_names,
    engine_names,
    extract_learned_features,
    get_legal_moves,
    immediate_scoring_moves,
    is_knight_home,
    minimax,
    move_to_str,
    turns_to_score,
    threatened_targets,
)


def outcome_for_side(winner: str | None, side: str) -> int:
    if winner == side:
        return 1
    if winner is None:
        return 0
    return -1


def finite_turns(value: float) -> int:
    return 99 if value == math.inf else int(value)


def outcome_target(row_outcome: int) -> float:
    if row_outcome > 0:
        return 1.0
    if row_outcome < 0:
        return 0.0
    return 0.5


def search_score_to_target(score: float, scale: float = 650.0) -> float:
    return 0.5 * (1.0 + math.tanh(score / scale))


def brute_search_target(child_state, mover: str, difficulty: str) -> tuple[float, float]:
    profile = AI_PROFILES[difficulty]
    search_depth = max(1, min(3, profile.depth - 1))
    score, _best_move = minimax(child_state, search_depth, -math.inf, math.inf, mover, {})
    return score, search_score_to_target(score)


def feature_row(
    game_id: int,
    ply: int,
    state,
    move,
    mover_engine: str,
    mover_difficulty: str,
    white_gap: int,
    black_gap: int,
) -> Dict[str, object]:
    mover = state.side_to_move
    enemy = BLACK if mover == WHITE else WHITE
    child = apply_move(state, move)
    mover_probe = state.clone()
    mover_probe.side_to_move = mover
    enemy_probe = state.clone()
    enemy_probe.side_to_move = enemy
    post_mover_probe = child.clone()
    post_mover_probe.side_to_move = mover
    post_enemy_probe = child.clone()
    post_enemy_probe.side_to_move = enemy
    before_features = extract_learned_features(state, mover)
    learned_features = extract_learned_features(child, mover)
    brute_target_score, brute_target_prob = brute_search_target(child, mover, mover_difficulty)
    self_turns_after = capped_turns_to_score(child, mover)
    opp_turns_after = capped_turns_to_score(child, enemy)

    target = None
    if move[0][0] >= 0:
        target = state.board[move[1][0]][move[1][1]]

    move_is_score = int(
        move[0][0] >= 0
        and state.board[move[0][0]][move[0][1]] is not None
        and state.board[move[0][0]][move[0][1]].kind == KNIGHT
        and len(immediate_scoring_moves(mover_probe)) > 0
        and move in immediate_scoring_moves(mover_probe)
    )

    threatened_self = threatened_targets(state, enemy, KNIGHT)
    threatened_enemy = threatened_targets(state, mover, KNIGHT)
    row = {
        "game_id": game_id,
        "ply": ply,
        "side": mover,
        "engine": mover_engine,
        "difficulty": mover_difficulty,
        "move": move_to_str(move),
        "variant": state.variant,
        "white_gap": white_gap,
        "black_gap": black_gap,
        "home_self": state.white_knights_home if mover == WHITE else state.black_knights_home,
        "home_opp": state.black_knights_home if mover == WHITE else state.white_knights_home,
        "home_live_self": count_home_knights_on_board(state, mover),
        "home_live_opp": count_home_knights_on_board(state, enemy),
        "unscored_self": count_unscored_knights(state, mover),
        "unscored_opp": count_unscored_knights(state, enemy),
        "pawns_self": len(state.locate(mover, PAWN)),
        "pawns_opp": len(state.locate(enemy, PAWN)),
        "immediate_scores_self": len(immediate_scoring_moves(mover_probe)),
        "immediate_scores_opp": len(immediate_scoring_moves(enemy_probe)),
        "turns_to_score_self": finite_turns(turns_to_score(state, mover)),
        "turns_to_score_opp": finite_turns(turns_to_score(state, enemy)),
        "threatened_knights_self": len(threatened_self),
        "threatened_knights_opp": len(threatened_enemy),
        "move_is_score": move_is_score,
        "move_captures_pawn": int(target is not None and target.kind == PAWN),
        "move_captures_knight": int(target is not None and target.kind == KNIGHT),
        "move_captures_home_knight": int(target is not None and target.kind == KNIGHT and is_knight_home(state, move[1])),
        "move_stops_opp_immediate_score": int(
            len(immediate_scoring_moves(enemy_probe)) > 0 and len(immediate_scoring_moves(post_enemy_probe)) == 0
        ),
        "move_creates_self_immediate_score": int(len(immediate_scoring_moves(post_mover_probe)) > 0),
        "self_can_score_in_1_after": int(self_turns_after <= 1),
        "self_can_score_in_2_after": int(self_turns_after <= 2),
        "opp_can_score_in_1_after": int(opp_turns_after <= 1),
        "opp_can_score_in_2_after": int(opp_turns_after <= 2),
        "target_brute_score": brute_target_score,
        "target_brute_prob": brute_target_prob,
        "learned_schema_version": LEARNED_FEATURE_SCHEMA_VERSION,
    }
    for feature_name in LEARNED_FEATURE_NAMES:
        row[f"feat_{feature_name}"] = learned_features[feature_name]
        row[f"delta_{feature_name}"] = learned_features[feature_name] - before_features[feature_name]
    return row


def play_game(
    game_id: int,
    white_engine: str,
    black_engine: str,
    white_difficulty: str,
    black_difficulty: str,
    variant: str,
    max_plies: int,
    random_openings: bool,
) -> List[Dict[str, object]]:
    white_gap = random.randrange(5) if random_openings else 2
    black_gap = random.randrange(5) if random_openings else 2
    state = default_state(white_gap=white_gap, black_gap=black_gap, variant=variant)
    rows: List[Dict[str, object]] = []
    plies = 0

    while state.winner() is None and plies < max_plies:
        legal = get_legal_moves(state)
        if not legal:
            break

        engine = white_engine if state.side_to_move == WHITE else black_engine
        difficulty = white_difficulty if state.side_to_move == WHITE else black_difficulty
        move = agent_move(state, difficulty=difficulty, engine=engine)
        row = feature_row(game_id, plies, state, move, engine, difficulty, white_gap, black_gap)
        rows.append(row)
        state = apply_move(state, move)
        plies += 1

    winner = state.winner()
    for row in rows:
        row["outcome_for_mover"] = outcome_for_side(winner, row["side"])
        row["winner"] = "" if winner is None else winner
        row["target_final_prob"] = outcome_target(int(row["outcome_for_mover"]))
        row["target_training"] = 0.7 * float(row["target_brute_prob"]) + 0.3 * float(row["target_final_prob"])
    return rows


def write_rows(rows: Iterable[Dict[str, object]], output_csv: Path) -> None:
    rows = list(rows)
    if not rows:
        return
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: List[Dict[str, object]]) -> str:
    if not rows:
        return "No rows recorded."
    by_engine: Dict[str, List[int]] = {}
    for row in rows:
        by_engine.setdefault(str(row["engine"]), []).append(int(row["outcome_for_mover"]))

    lines = ["Engine summary:"]
    for engine, outcomes in sorted(by_engine.items()):
        mean = sum(outcomes) / len(outcomes)
        win_rate = sum(1 for value in outcomes if value > 0) / len(outcomes)
        lines.append(f"- {engine}: win rate {win_rate:.3f}, mean outcome {mean:.3f}, rows {len(outcomes)}")

    for feature in ("move_is_score", "move_stops_opp_immediate_score", "move_captures_home_knight"):
        positives = [int(row["outcome_for_mover"]) for row in rows if int(row[feature]) == 1]
        if positives:
            lines.append(
                f"- {feature}=1: win rate {sum(1 for value in positives if value > 0) / len(positives):.3f}, rows {len(positives)}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Magnet Knights self-play and export move-level features.")
    parser.add_argument("--games", type=int, default=20, help="Number of games to simulate.")
    parser.add_argument("--white-engine", choices=engine_names(), default=ENGINE_BRUTE)
    parser.add_argument("--black-engine", choices=engine_names(), default=ENGINE_RACE)
    parser.add_argument("--white-difficulty", choices=difficulty_names(), default="hard")
    parser.add_argument("--black-difficulty", choices=difficulty_names(), default="hard")
    parser.add_argument("--variant", choices=[VARIANT_STANDARD, VARIANT_RESPAWN], default=VARIANT_STANDARD)
    parser.add_argument("--max-plies", type=int, default=160, help="Safety cap for plies per game.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for reproducible self-play.")
    parser.add_argument("--random-openings", action="store_true", help="Randomize hidden opening gap columns for each game.")
    parser.add_argument("--output-csv", type=Path, default=Path("output/selfplay/move_features.csv"))
    args = parser.parse_args()

    random.seed(args.seed)
    all_rows: List[Dict[str, object]] = []
    for game_id in range(args.games):
        all_rows.extend(
            play_game(
                game_id=game_id,
                white_engine=args.white_engine,
                black_engine=args.black_engine,
                white_difficulty=args.white_difficulty,
                black_difficulty=args.black_difficulty,
                variant=args.variant,
                max_plies=args.max_plies,
                random_openings=args.random_openings,
            )
        )

    write_rows(all_rows, args.output_csv)
    print(f"Wrote {len(all_rows)} move rows to {args.output_csv}")
    print(summarize(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
