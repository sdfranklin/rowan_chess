#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Callable, Dict, List, Optional, Tuple

from magnet_knights_learned_model import LEARNED_MODEL

ROWS = 7
COLS = 5
WHITE = "W"
BLACK = "B"
PAWN = "P"
KNIGHT = "N"
VARIANT_STANDARD = "standard"
VARIANT_RESPAWN = "respawn"
STANDARD_HOME_ROW_FROM_SIDE = 5
RESPAWN_HOME_ROW_FROM_SIDE = 5
RESPAWN_ROW_FROM_SIDE = 2
RESPAWN_ORIGIN_ROW = -1

Coord = Tuple[int, int]
Move = Tuple[Coord, Coord]


@dataclass(frozen=True)
class DifficultyProfile:
    name: str
    depth: int
    randomness: float
    top_k: int


AI_PROFILES: Dict[str, DifficultyProfile] = {
    "easy": DifficultyProfile(name="easy", depth=2, randomness=0.35, top_k=3),
    "medium": DifficultyProfile(name="medium", depth=4, randomness=0.12, top_k=2),
    "hard": DifficultyProfile(name="hard", depth=5, randomness=0.0, top_k=1),
}

ENGINE_BRUTE = "brute"
ENGINE_RACE = "race"
ENGINE_LEARNED = "learned"
AI_ENGINES: Dict[str, str] = {
    ENGINE_BRUTE: "Brute",
    ENGINE_RACE: "Race",
    ENGINE_LEARNED: "Learned",
}

LEARNED_FEATURE_SCHEMA_VERSION = "learned_v1"
LEARNED_FEATURE_NAMES: Tuple[str, ...] = (
    "bias",
    "home_diff",
    "home_live_diff",
    "unscored_knight_diff",
    "pawn_diff",
    "immediate_score_diff",
    "my_immediate_scores",
    "opp_immediate_scores",
    "turns_to_score_self",
    "turns_to_score_opp",
    "turns_to_score_diff",
    "threatened_unscored_knight_diff",
    "threatened_home_knight_diff",
    "jump_ready_diff",
    "bridge_pawn_diff",
    "legal_move_diff",
    "unscored_knight_distance_diff",
    "self_last_unscored_knight",
    "opp_last_unscored_knight",
    "variant_is_respawn",
)


def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < ROWS and 0 <= col < COLS


def normalize_gap_column(gap_col: int) -> int:
    if not 0 <= gap_col < COLS:
        raise ValueError(f"gap column must be between 0 and {COLS - 1}")
    return gap_col


@dataclass(frozen=True)
class Piece:
    side: str
    kind: str

    def symbol(self) -> str:
        return self.side + self.kind


@dataclass
class State:
    board: List[List[Optional[Piece]]]
    side_to_move: str = WHITE
    white_knights_home: int = 0
    black_knights_home: int = 0
    variant: str = VARIANT_STANDARD

    def clone(self) -> "State":
        return State(
            board=[[self.board[row][col] for col in range(COLS)] for row in range(ROWS)],
            side_to_move=self.side_to_move,
            white_knights_home=self.white_knights_home,
            black_knights_home=self.black_knights_home,
            variant=self.variant,
        )

    def winner(self) -> Optional[str]:
        if self.white_knights_home >= 2:
            return WHITE
        if self.black_knights_home >= 2:
            return BLACK

        white_live = self.live_knights(WHITE)
        black_live = self.live_knights(BLACK)

        if white_live <= 1 and black_live <= 1:
            if self.white_knights_home >= 1 and self.black_knights_home == 0:
                return WHITE
            if self.black_knights_home >= 1 and self.white_knights_home == 0:
                return BLACK

        if white_live == 0 and black_live > 0:
            return BLACK
        if black_live == 0 and white_live > 0:
            return WHITE
        if not get_legal_moves(self):
            return self.enemy(self.side_to_move)
        return None

    def target_row(self, side: str) -> int:
        home_row_from_side = STANDARD_HOME_ROW_FROM_SIDE
        if self.variant == VARIANT_RESPAWN:
            home_row_from_side = RESPAWN_HOME_ROW_FROM_SIDE
        return home_row_from_side - 1 if side == WHITE else ROWS - home_row_from_side

    def respawn_row(self, side: str) -> int:
        return RESPAWN_ROW_FROM_SIDE - 1 if side == WHITE else ROWS - RESPAWN_ROW_FROM_SIDE

    def forward_dir(self, side: str) -> int:
        return 1 if side == WHITE else -1

    def enemy(self, side: str) -> str:
        return BLACK if side == WHITE else WHITE

    def locate(self, side: str, kind: Optional[str] = None) -> List[Coord]:
        coords: List[Coord] = []
        for row in range(ROWS):
            for col in range(COLS):
                piece = self.board[row][col]
                if piece is None:
                    continue
                if piece.side == side and (kind is None or piece.kind == kind):
                    coords.append((row, col))
        return coords

    def live_knights(self, side: str) -> int:
        return len(self.locate(side, KNIGHT))

    def display(self) -> str:
        lines = ["    " + "  ".join(str(col) for col in range(COLS)), "   " + "---" * COLS]
        for row in range(ROWS - 1, -1, -1):
            cells = []
            for col in range(COLS):
                piece = self.board[row][col]
                cells.append(piece.symbol() if piece else "..")
            lines.append(f"{row} | " + " ".join(cells))
        lines.append("")
        lines.append(
            f"To move: {self.side_to_move} | White home: {self.white_knights_home} | Black home: {self.black_knights_home}"
        )
        return "\n".join(lines)


def default_state(
    white_gap: int = 2,
    black_gap: int = 2,
    variant: str = VARIANT_STANDARD,
) -> State:
    white_gap = normalize_gap_column(white_gap)
    black_gap = normalize_gap_column(black_gap)
    if variant not in {VARIANT_STANDARD, VARIANT_RESPAWN}:
        raise ValueError("variant must be 'standard' or 'respawn'")
    board: List[List[Optional[Piece]]] = [[None for _ in range(COLS)] for _ in range(ROWS)]
    for col in range(COLS):
        if col == white_gap:
            continue
        board[0][col] = Piece(WHITE, KNIGHT)
        board[1][col] = Piece(WHITE, PAWN)
    for col in range(COLS):
        if col == black_gap:
            continue
        board[ROWS - 1][col] = Piece(BLACK, KNIGHT)
        board[ROWS - 2][col] = Piece(BLACK, PAWN)
    return State(board=board, side_to_move=WHITE, variant=variant)


def board_key(state: State) -> Tuple[Tuple[str, ...], str, int, int]:
    flat = []
    for row in range(ROWS):
        for col in range(COLS):
            piece = state.board[row][col]
            flat.append(piece.symbol() if piece is not None else "..")
    return tuple(flat), state.side_to_move, state.white_knights_home, state.black_knights_home, 0 if state.variant == VARIANT_STANDARD else 1


def is_respawn_move(move: Move) -> bool:
    return move[0][0] == RESPAWN_ORIGIN_ROW


def legal_pawn_moves(state: State, pos: Coord) -> List[Move]:
    row, col = pos
    piece = state.board[row][col]
    assert piece is not None and piece.kind == PAWN

    enemy = state.enemy(piece.side)
    forward = state.forward_dir(piece.side)
    moves: List[Move] = []

    for d_row, d_col in ((1, 0), (-1, 0), (0, -1), (0, 1)):
        next_row = row + d_row
        next_col = col + d_col

        while in_bounds(next_row, next_col) and state.board[next_row][next_col] is None:
            moves.append(((row, col), (next_row, next_col)))
            next_row += d_row
            next_col += d_col

        if in_bounds(row + d_row, col + d_col):
            target = state.board[row + d_row][col + d_col]
            if target is not None and target.side == enemy:
                if target.kind == KNIGHT and d_row == -forward:
                    continue
                moves.append(((row, col), (row + d_row, col + d_col)))

    return moves


def legal_knight_destinations_from(state: State, start: Coord) -> List[Coord]:
    start_row, start_col = start
    piece = state.board[start_row][start_col]
    assert piece is not None and piece.kind == KNIGHT

    side = piece.side
    enemy = state.enemy(side)
    d_row = state.forward_dir(side)
    results = set()

    def dfs(board: List[List[Optional[Piece]]], pos: Coord, jumped: bool) -> None:
        row, col = pos
        middle_row = row + d_row
        middle_col = col
        landing_row = row + 2 * d_row
        landing_col = col
        if in_bounds(middle_row, middle_col) and in_bounds(landing_row, landing_col):
            middle = board[middle_row][middle_col]
            landing = board[landing_row][landing_col]
            if middle is not None and middle.kind == PAWN:
                if not (landing is not None and landing.kind == KNIGHT):
                    if not (landing is not None and landing.side == side):
                        next_board = [[board[r][c] for c in range(COLS)] for r in range(ROWS)]
                        knight = next_board[row][col]
                        next_board[row][col] = None
                        if landing is not None and landing.side == enemy and landing.kind == PAWN:
                            next_board[landing_row][landing_col] = None
                        next_board[landing_row][landing_col] = knight
                        dfs(next_board, (landing_row, landing_col), True)

        if jumped:
            results.add(pos)

    dfs(state.board, start, False)
    results.discard(start)
    return sorted(results)


def legal_knight_moves(state: State, pos: Coord) -> List[Move]:
    return [(pos, dest) for dest in legal_knight_destinations_from(state, pos)]


def legal_respawn_moves(state: State) -> List[Move]:
    if state.variant != VARIANT_RESPAWN:
        return []
    side = state.side_to_move
    live_pawns = len(state.locate(side, PAWN))
    if live_pawns >= COLS - 1:
        return []
    row = state.respawn_row(side)
    moves: List[Move] = []
    for col in range(COLS):
        if state.board[row][col] is None:
            moves.append(((RESPAWN_ORIGIN_ROW, col), (row, col)))
    return moves


def get_legal_moves(state: State) -> List[Move]:
    moves: List[Move] = []
    for row in range(ROWS):
        for col in range(COLS):
            piece = state.board[row][col]
            if piece is None or piece.side != state.side_to_move:
                continue
            if piece.kind == PAWN:
                moves.extend(legal_pawn_moves(state, (row, col)))
            else:
                moves.extend(legal_knight_moves(state, (row, col)))
    moves.extend(legal_respawn_moves(state))
    return moves


def get_legal_moves_from(state: State, start: Coord) -> List[Move]:
    return [move for move in get_legal_moves(state) if move[0] == start]


def apply_move(state: State, move: Move) -> State:
    (from_row, from_col), (to_row, to_col) = move

    next_state = state.clone()

    if is_respawn_move(move):
        piece = Piece(state.side_to_move, PAWN)
        next_state.board[to_row][to_col] = piece
        next_state.side_to_move = state.enemy(state.side_to_move)
        return next_state

    piece = state.board[from_row][from_col]
    assert piece is not None

    if piece.kind == PAWN:
        next_state.board[from_row][from_col] = None
        next_state.board[to_row][to_col] = piece
    else:
        side = piece.side
        enemy = state.enemy(side)
        d_row = state.forward_dir(side)
        target = (to_row, to_col)

        def build_path(
            board: List[List[Optional[Piece]]],
            pos: Coord,
            path: List[Coord],
        ) -> Optional[List[Coord]]:
            if pos == target and path:
                return path

            row, col = pos
            middle_row = row + d_row
            middle_col = col
            landing_row = row + 2 * d_row
            landing_col = col
            if not in_bounds(middle_row, middle_col) or not in_bounds(landing_row, landing_col):
                return None

            middle = board[middle_row][middle_col]
            landing = board[landing_row][landing_col]
            if middle is None or middle.kind != PAWN:
                return None
            if landing is not None and landing.kind == KNIGHT:
                return None
            if landing is not None and landing.side == side:
                return None

            next_board = [[board[r][c] for c in range(COLS)] for r in range(ROWS)]
            knight = next_board[row][col]
            next_board[row][col] = None
            if landing is not None and landing.side == enemy and landing.kind == PAWN:
                next_board[landing_row][landing_col] = None
            next_board[landing_row][landing_col] = knight

            result = build_path(next_board, (landing_row, landing_col), path + [(landing_row, landing_col)])
            if result is not None:
                return result
            return None

        path = build_path(next_state.board, (from_row, from_col), [])
        if path is None:
            raise ValueError(f"Could not reconstruct knight path for move {move}")

        current_row, current_col = from_row, from_col
        for next_row, next_col in path:
            landing = next_state.board[next_row][next_col]
            next_state.board[current_row][current_col] = None
            if landing is not None and landing.side == enemy and landing.kind == PAWN:
                next_state.board[next_row][next_col] = None
            next_state.board[next_row][next_col] = piece
            current_row, current_col = next_row, next_col

    if piece.kind == KNIGHT:
        if piece.side == WHITE and from_row != next_state.target_row(WHITE) and to_row == next_state.target_row(WHITE):
            next_state.white_knights_home += 1
        if piece.side == BLACK and from_row != next_state.target_row(BLACK) and to_row == next_state.target_row(BLACK):
            next_state.black_knights_home += 1

    next_state.side_to_move = state.enemy(state.side_to_move)
    return next_state


def immediate_scoring_moves(state: State) -> List[Move]:
    scoring: List[Move] = []
    for move in get_legal_moves(state):
        (from_row, from_col), (to_row, _to_col) = move
        piece = state.board[from_row][from_col]
        if piece is not None and piece.kind == KNIGHT and to_row == state.target_row(piece.side):
            scoring.append(move)
    return scoring


def is_knight_home(state: State, coord: Coord) -> bool:
    row, col = coord
    piece = state.board[row][col]
    if piece is None or piece.kind != KNIGHT:
        return False
    home_row = state.target_row(piece.side)
    return row >= home_row if piece.side == WHITE else row <= home_row


def count_home_knights_on_board(state: State, side: str) -> int:
    return sum(1 for coord in state.locate(side, KNIGHT) if is_knight_home(state, coord))


def count_unscored_knights(state: State, side: str) -> int:
    return state.live_knights(side) - count_home_knights_on_board(state, side)


def threatened_targets(state: State, by_side: str, kind: Optional[str] = None) -> List[Coord]:
    probe = state.clone()
    probe.side_to_move = by_side
    threatened: List[Coord] = []
    for move in get_legal_moves(probe):
        _start, destination = move
        piece = state.board[destination[0]][destination[1]]
        if piece is None:
            continue
        if kind is not None and piece.kind != kind:
            continue
        threatened.append(destination)
    return threatened


def evaluate(state: State, side: str) -> float:
    winner = state.winner()
    if winner == side:
        return 1e6
    if winner == state.enemy(side):
        return -1e6

    enemy = state.enemy(side)
    my_home = state.white_knights_home if side == WHITE else state.black_knights_home
    opp_home = state.black_knights_home if side == WHITE else state.white_knights_home
    score = 460 * (my_home - opp_home)

    my_pawns = len(state.locate(side, PAWN))
    my_knights = len(state.locate(side, KNIGHT))
    opp_pawns = len(state.locate(enemy, PAWN))
    opp_knights = len(state.locate(enemy, KNIGHT))
    score += 24 * (my_pawns - opp_pawns)
    score += 155 * (my_knights - opp_knights)

    my_mobility_state = state.clone()
    my_mobility_state.side_to_move = side
    opp_mobility_state = state.clone()
    opp_mobility_state.side_to_move = enemy
    score += 3 * (len(get_legal_moves(my_mobility_state)) - len(get_legal_moves(opp_mobility_state)))

    my_threats = len(immediate_scoring_moves(my_mobility_state))
    opp_threats = len(immediate_scoring_moves(opp_mobility_state))
    score += 180 * my_threats
    score -= 220 * opp_threats

    my_knight_targets = threatened_targets(state, enemy, KNIGHT)
    opp_knight_targets = threatened_targets(state, side, KNIGHT)
    score -= 85 * len(my_knight_targets)
    score += 70 * len(opp_knight_targets)

    my_pawn_targets = threatened_targets(state, enemy, PAWN)
    opp_pawn_targets = threatened_targets(state, side, PAWN)
    score -= 16 * len(my_pawn_targets)
    score += 12 * len(opp_pawn_targets)

    my_target_row = state.target_row(side)
    opp_target_row = state.target_row(enemy)
    for row, col in state.locate(side, KNIGHT):
        score += 18 * (ROWS - abs(my_target_row - row))
        score += 5 * (2 - abs(2 - col))
    for row, col in state.locate(enemy, KNIGHT):
        score -= 18 * (ROWS - abs(opp_target_row - row))
        score -= 5 * (2 - abs(2 - col))

    for row, _col in state.locate(side, PAWN):
        score += 3 * (ROWS - abs(my_target_row - row))
    for row, _col in state.locate(enemy, PAWN):
        score -= 3 * (ROWS - abs(opp_target_row - row))

    return float(score)


def jump_ready_knights(state: State, side: str) -> int:
    probe = state.clone()
    probe.side_to_move = side
    count = 0
    for coord in state.locate(side, KNIGHT):
        if is_knight_home(state, coord):
            continue
        if get_legal_moves_from(probe, coord):
            count += 1
    return count


def bridge_pawns(state: State, side: str) -> int:
    d_row = state.forward_dir(side)
    count = 0
    for row, col in state.locate(side, KNIGHT):
        if is_knight_home(state, (row, col)):
            continue
        middle_row = row + d_row
        if not in_bounds(middle_row, col):
            continue
        middle = state.board[middle_row][col]
        if middle is not None and middle.kind == PAWN:
            count += 1
    return count


def turns_bonus(turns: float) -> int:
    if turns == 1:
        return 520
    if turns == 2:
        return 210
    if turns == 3:
        return 70
    return 0


def capped_turns_to_score(state: State, side: str, max_turns: int = 3, fallback: int = 4, branch_limit: int = 3) -> int:
    probe = state.clone()
    probe.side_to_move = side
    if immediate_scoring_moves(probe):
        return 1

    legal = sorted(get_legal_moves(probe), key=lambda move: _move_priority(probe, move), reverse=True)[:branch_limit]
    for move in legal:
        child = apply_move(probe, move)
        child.side_to_move = side
        if immediate_scoring_moves(child):
            return 2
        if max_turns <= 2:
            continue
        follow_ups = sorted(get_legal_moves(child), key=lambda candidate: _move_priority(child, candidate), reverse=True)[:branch_limit]
        for follow_up in follow_ups:
            grandchild = apply_move(child, follow_up)
            grandchild.side_to_move = side
            if immediate_scoring_moves(grandchild):
                return 3
    return fallback


def turns_to_score(
    state: State,
    side: str,
    max_turns: int = 3,
    branch_limit: int = 6,
    memo: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str], float]] = None,
) -> float:
    if memo is None:
        memo = {}
    probe = state.clone()
    probe.side_to_move = side
    cache_key = board_key(probe) + (side, max_turns, "solo")
    if cache_key in memo:
        return memo[cache_key]

    if immediate_scoring_moves(probe):
        memo[cache_key] = 1
        return 1
    if max_turns <= 1:
        memo[cache_key] = math.inf
        return math.inf

    legal = get_legal_moves(probe)
    if not legal:
        memo[cache_key] = math.inf
        return math.inf

    ordered = sorted(legal, key=lambda move: _race_move_priority(probe, move), reverse=True)[:branch_limit]
    best = math.inf
    for move in ordered:
        child = apply_move(probe, move)
        child.side_to_move = side
        candidate = turns_to_score(child, side, max_turns - 1, branch_limit, memo)
        if candidate != math.inf:
            best = min(best, 1 + candidate)
    memo[cache_key] = best
    return best


def evaluate_race(state: State, side: str) -> float:
    winner = state.winner()
    if winner == side:
        return 1e6
    if winner == state.enemy(side):
        return -1e6

    enemy = state.enemy(side)
    my_home = state.white_knights_home if side == WHITE else state.black_knights_home
    opp_home = state.black_knights_home if side == WHITE else state.white_knights_home
    my_home_live = count_home_knights_on_board(state, side)
    opp_home_live = count_home_knights_on_board(state, enemy)
    my_unscored_knights = count_unscored_knights(state, side)
    opp_unscored_knights = count_unscored_knights(state, enemy)
    my_pawns = len(state.locate(side, PAWN))
    opp_pawns = len(state.locate(enemy, PAWN))

    score = 980 * (my_home - opp_home)
    score += 280 * (my_unscored_knights - opp_unscored_knights)
    score += 45 * (my_home_live - opp_home_live)
    score += 38 * (my_pawns - opp_pawns)

    my_probe = state.clone()
    my_probe.side_to_move = side
    opp_probe = state.clone()
    opp_probe.side_to_move = enemy
    my_immediate = len(immediate_scoring_moves(my_probe))
    opp_immediate = len(immediate_scoring_moves(opp_probe))
    score += 560 * my_immediate
    score -= 820 * opp_immediate

    score += 26 * (jump_ready_knights(state, side) - jump_ready_knights(state, enemy))
    score += 14 * (bridge_pawns(state, side) - bridge_pawns(state, enemy))

    my_knight_targets = threatened_targets(state, enemy, KNIGHT)
    opp_knight_targets = threatened_targets(state, side, KNIGHT)
    for coord in my_knight_targets:
        score -= 40 if is_knight_home(state, coord) else 240
    for coord in opp_knight_targets:
        score += 12 if is_knight_home(state, coord) else 150

    my_target_row = state.target_row(side)
    opp_target_row = state.target_row(enemy)
    for row, col in state.locate(side, KNIGHT):
        if is_knight_home(state, (row, col)):
            continue
        score += 28 * (ROWS - abs(my_target_row - row))
        score += 7 * (2 - abs(2 - col))
    for row, col in state.locate(enemy, KNIGHT):
        if is_knight_home(state, (row, col)):
            continue
        score -= 28 * (ROWS - abs(opp_target_row - row))
        score -= 7 * (2 - abs(2 - col))

    score += 2 * (len(get_legal_moves(my_probe)) - len(get_legal_moves(opp_probe)))
    return float(score)


def _threatened_knight_counts(state: State, side: str) -> Tuple[int, int]:
    enemy = state.enemy(side)
    threatened_home = 0
    threatened_unscored = 0
    for coord in threatened_targets(state, enemy, KNIGHT):
        if is_knight_home(state, coord):
            threatened_home += 1
        else:
            threatened_unscored += 1
    return threatened_home, threatened_unscored


def _unscored_knight_distance_total(state: State, side: str) -> int:
    home_row = state.target_row(side)
    total = 0
    for row, col in state.locate(side, KNIGHT):
        if is_knight_home(state, (row, col)):
            continue
        if side == WHITE:
            total += max(0, home_row - row)
        else:
            total += max(0, row - home_row)
    return total


def extract_learned_features(state: State, side: str) -> Dict[str, float]:
    enemy = state.enemy(side)
    my_home = state.white_knights_home if side == WHITE else state.black_knights_home
    opp_home = state.black_knights_home if side == WHITE else state.white_knights_home
    my_home_live = count_home_knights_on_board(state, side)
    opp_home_live = count_home_knights_on_board(state, enemy)
    my_unscored_knights = count_unscored_knights(state, side)
    opp_unscored_knights = count_unscored_knights(state, enemy)
    my_pawns = len(state.locate(side, PAWN))
    opp_pawns = len(state.locate(enemy, PAWN))

    my_probe = state.clone()
    my_probe.side_to_move = side
    opp_probe = state.clone()
    opp_probe.side_to_move = enemy
    my_immediate_scores = len(immediate_scoring_moves(my_probe))
    opp_immediate_scores = len(immediate_scoring_moves(opp_probe))
    turns_self = capped_turns_to_score(state, side)
    turns_opp = capped_turns_to_score(state, enemy)
    my_home_threatened, my_unscored_threatened = _threatened_knight_counts(state, side)
    opp_home_threatened, opp_unscored_threatened = _threatened_knight_counts(state, enemy)
    my_legal = len(get_legal_moves(my_probe))
    opp_legal = len(get_legal_moves(opp_probe))
    my_distance_total = _unscored_knight_distance_total(state, side)
    opp_distance_total = _unscored_knight_distance_total(state, enemy)

    return {
        "bias": 1.0,
        "home_diff": float(my_home - opp_home),
        "home_live_diff": float(my_home_live - opp_home_live),
        "unscored_knight_diff": float(my_unscored_knights - opp_unscored_knights),
        "pawn_diff": float(my_pawns - opp_pawns),
        "immediate_score_diff": float(my_immediate_scores - opp_immediate_scores),
        "my_immediate_scores": float(my_immediate_scores),
        "opp_immediate_scores": float(opp_immediate_scores),
        "turns_to_score_self": float(turns_self),
        "turns_to_score_opp": float(turns_opp),
        "turns_to_score_diff": float(turns_opp - turns_self),
        "threatened_unscored_knight_diff": float(opp_unscored_threatened - my_unscored_threatened),
        "threatened_home_knight_diff": float(opp_home_threatened - my_home_threatened),
        "jump_ready_diff": float(jump_ready_knights(state, side) - jump_ready_knights(state, enemy)),
        "bridge_pawn_diff": float(bridge_pawns(state, side) - bridge_pawns(state, enemy)),
        "legal_move_diff": float(my_legal - opp_legal),
        "unscored_knight_distance_diff": float(opp_distance_total - my_distance_total),
        "self_last_unscored_knight": 1.0 if my_unscored_knights == 1 else 0.0,
        "opp_last_unscored_knight": 1.0 if opp_unscored_knights == 1 else 0.0,
        "variant_is_respawn": 1.0 if state.variant == VARIANT_RESPAWN else 0.0,
    }


def _validate_learned_model(model: Dict[str, object]) -> None:
    if str(model.get("schema_version")) != LEARNED_FEATURE_SCHEMA_VERSION:
        raise ValueError("learned model schema version does not match runtime")
    feature_names = tuple(str(name) for name in model.get("feature_names", []))
    if feature_names != LEARNED_FEATURE_NAMES:
        raise ValueError("learned model feature names do not match runtime")
    weights = model.get("weights", [])
    means = model.get("means", [])
    scales = model.get("scales", [])
    if len(weights) != len(LEARNED_FEATURE_NAMES) or len(means) != len(LEARNED_FEATURE_NAMES) or len(scales) != len(LEARNED_FEATURE_NAMES):
        raise ValueError("learned model vector lengths do not match runtime features")


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _learned_raw_score(feature_map: Dict[str, float]) -> float:
    _validate_learned_model(LEARNED_MODEL)
    weights = [float(value) for value in LEARNED_MODEL["weights"]]
    means = [float(value) for value in LEARNED_MODEL["means"]]
    scales = [float(value) for value in LEARNED_MODEL["scales"]]
    bias = float(LEARNED_MODEL["bias"])
    total = bias
    for index, name in enumerate(LEARNED_FEATURE_NAMES):
        scale = scales[index] if abs(scales[index]) > 1e-9 else 1.0
        normalized = (float(feature_map[name]) - means[index]) / scale
        total += weights[index] * normalized
    return total


def evaluate_learned(state: State, side: str) -> float:
    winner = state.winner()
    if winner == side:
        return 1e6
    if winner == state.enemy(side):
        return -1e6

    raw_score = _learned_raw_score(extract_learned_features(state, side))
    probability = _sigmoid(raw_score)
    return 2200.0 * (probability - 0.5)


def _finite_turn_bucket(turns: float, fallback: int = 5) -> int:
    if math.isinf(turns):
        return fallback
    return int(turns)


def _minimax_with_policy(
    state: State,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: str,
    evaluate_fn: Callable[[State, str], float],
    priority_fn: Callable[[State, Move], int],
    cache_prefix: str,
    table: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float]] = None,
) -> Tuple[float, Optional[Move]]:
    if table is None:
        table = {}

    winner = state.winner()
    moves = get_legal_moves(state)
    if depth == 0 or winner is not None or not moves:
        return evaluate_fn(state, maximizing_for), None

    cache_key = board_key(state) + (depth, maximizing_for, cache_prefix)
    if cache_key in table:
        return table[cache_key], None

    ordered_moves = sorted(
        moves,
        key=lambda move: priority_fn(state, move),
        reverse=True,
    )
    best_move: Optional[Move] = None
    maximizing = state.side_to_move == maximizing_for

    if maximizing:
        value = -math.inf
        for move in ordered_moves:
            child = apply_move(state, move)
            child_value, _unused = _minimax_with_policy(
                child,
                depth - 1,
                alpha,
                beta,
                maximizing_for,
                evaluate_fn,
                priority_fn,
                cache_prefix,
                table,
            )
            if child_value > value:
                value = child_value
                best_move = move
            alpha = max(alpha, value)
            if beta <= alpha:
                break
        table[cache_key] = value
        return value, best_move

    value = math.inf
    for move in ordered_moves:
        child = apply_move(state, move)
        child_value, _unused = _minimax_with_policy(
            child,
            depth - 1,
            alpha,
            beta,
            maximizing_for,
            evaluate_fn,
            priority_fn,
            cache_prefix,
            table,
        )
        if child_value < value:
            value = child_value
            best_move = move
        beta = min(beta, value)
        if beta <= alpha:
            break
    table[cache_key] = value
    return value, best_move


def minimax(
    state: State,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: str,
    table: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float]] = None,
) -> Tuple[float, Optional[Move]]:
    return _minimax_with_policy(state, depth, alpha, beta, maximizing_for, evaluate, _move_priority, ENGINE_BRUTE, table)


def minimax_race(
    state: State,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: str,
    table: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float]] = None,
) -> Tuple[float, Optional[Move]]:
    return _minimax_with_policy(state, depth, alpha, beta, maximizing_for, evaluate_race, _race_move_priority, ENGINE_RACE, table)


def minimax_learned(
    state: State,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: str,
    table: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float]] = None,
) -> Tuple[float, Optional[Move]]:
    return _minimax_with_policy(state, depth, alpha, beta, maximizing_for, evaluate_learned, _move_priority, ENGINE_LEARNED, table)


def _move_priority(state: State, move: Move) -> int:
    if is_respawn_move(move):
        return 35
    (from_row, from_col), (to_row, to_col) = move
    piece = state.board[from_row][from_col]
    target = state.board[to_row][to_col]
    priority = 0
    if piece is not None and piece.kind == KNIGHT and to_row == state.target_row(piece.side):
        priority += 1000
    if piece is not None and piece.kind == KNIGHT:
        priority += 80
    if target is not None:
        priority += 100
        if target.kind == KNIGHT:
            priority += 180
    return priority


def _race_move_priority(state: State, move: Move) -> int:
    priority = _move_priority(state, move)
    side = state.side_to_move
    enemy = state.enemy(side)
    child = apply_move(state, move)
    if child.winner() == side:
        return priority + 5000

    my_probe = child.clone()
    my_probe.side_to_move = side
    opp_probe = child.clone()
    opp_probe.side_to_move = enemy
    priority += 420 * len(immediate_scoring_moves(my_probe))
    priority -= 1000 * len(immediate_scoring_moves(opp_probe))

    if not is_respawn_move(move):
        _start, destination = move
        target = state.board[destination[0]][destination[1]]
        piece = state.board[move[0][0]][move[0][1]]
        if target is not None and target.kind == KNIGHT:
            priority += 30 if is_knight_home(state, destination) else 170
        if piece is not None and piece.kind == KNIGHT:
            threatened = any(coord == destination for coord in threatened_targets(child, enemy, KNIGHT))
            if threatened:
                priority -= 25 if is_knight_home(child, destination) else 220
    return priority


def normalize_difficulty(difficulty: str) -> str:
    normalized = difficulty.strip().lower()
    if normalized not in AI_PROFILES:
        raise ValueError(f"difficulty must be one of: {', '.join(sorted(AI_PROFILES))}")
    return normalized


def difficulty_names() -> Tuple[str, ...]:
    return tuple(AI_PROFILES.keys())


def normalize_engine(engine: str) -> str:
    normalized = engine.strip().lower()
    if normalized not in AI_ENGINES:
        raise ValueError(f"engine must be one of: {', '.join(sorted(AI_ENGINES))}")
    return normalized


def engine_names() -> Tuple[str, ...]:
    return tuple(AI_ENGINES.keys())


def _race_root_adjustment(state: State, side: str) -> float:
    enemy = state.enemy(side)
    my_probe = state.clone()
    my_probe.side_to_move = side
    opp_probe = state.clone()
    opp_probe.side_to_move = enemy

    score = 260.0 * len(immediate_scoring_moves(my_probe))
    score -= 980.0 * len(immediate_scoring_moves(opp_probe))
    for coord in threatened_targets(state, enemy, KNIGHT):
        score -= 40.0 if is_knight_home(state, coord) else 260.0
    for coord in threatened_targets(state, side, KNIGHT):
        score += 10.0 if is_knight_home(state, coord) else 140.0
    return score


def _race_move_adjustment(state: State, child: State, move: Move, side: str) -> float:
    enemy = state.enemy(side)

    pre_my_probe = state.clone()
    pre_my_probe.side_to_move = side
    pre_opp_probe = state.clone()
    pre_opp_probe.side_to_move = enemy
    post_my_probe = child.clone()
    post_my_probe.side_to_move = side
    post_opp_probe = child.clone()
    post_opp_probe.side_to_move = enemy

    pre_my_immediate = len(immediate_scoring_moves(pre_my_probe))
    pre_opp_immediate = len(immediate_scoring_moves(pre_opp_probe))
    post_my_immediate = len(immediate_scoring_moves(post_my_probe))
    post_opp_immediate = len(immediate_scoring_moves(post_opp_probe))

    score = 0.0
    if pre_opp_immediate > 0 and post_opp_immediate == 0:
        score += 1250.0
    score -= 900.0 * max(0, post_opp_immediate - pre_opp_immediate)
    score -= 520.0 * post_opp_immediate

    if post_my_immediate > pre_my_immediate:
        score += 280.0 * (post_my_immediate - pre_my_immediate)
    score += 140.0 * post_my_immediate

    pre_my_turns = _finite_turn_bucket(turns_to_score(state, side, max_turns=4), fallback=6)
    pre_opp_turns = _finite_turn_bucket(turns_to_score(state, enemy, max_turns=4), fallback=6)
    post_my_turns = _finite_turn_bucket(turns_to_score(child, side, max_turns=4), fallback=6)
    post_opp_turns = _finite_turn_bucket(turns_to_score(child, enemy, max_turns=4), fallback=6)
    score += 180.0 * (pre_my_turns - post_my_turns)
    score += 220.0 * (post_opp_turns - pre_opp_turns)

    if not is_respawn_move(move):
        _start, destination = move
        target = state.board[destination[0]][destination[1]]
        if target is not None and target.kind == KNIGHT and is_knight_home(state, destination):
            if not (pre_opp_immediate > 0 and post_opp_immediate == 0):
                score -= 220.0
    return score


def _brute_agent_move(state: State, depth: Optional[int], difficulty: str) -> Move:
    profile = AI_PROFILES[difficulty]
    search_depth = depth if depth is not None else profile.depth

    winners = immediate_scoring_moves(state)
    if winners:
        return random.choice(winners)

    legal = get_legal_moves(state)
    if not legal:
        raise ValueError("No legal move available")

    table: Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float] = {}
    ranked: List[Tuple[float, Move]] = []
    for move in legal:
        child = apply_move(state, move)
        score, _unused = minimax(child, search_depth - 1, -math.inf, math.inf, state.side_to_move, table)
        ranked.append((score, move))

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score = ranked[0][0]
    candidate_pool = [move for score, move in ranked[: profile.top_k] if score >= best_score - 45]
    if not candidate_pool:
        candidate_pool = [ranked[0][1]]

    if profile.randomness > 0.0 and len(candidate_pool) > 1 and random.random() < profile.randomness:
        return random.choice(candidate_pool)
    return ranked[0][1]


def _race_agent_move(state: State, depth: Optional[int], difficulty: str) -> Move:
    profile = AI_PROFILES[difficulty]
    search_depth = depth if depth is not None else profile.depth

    legal = get_legal_moves(state)
    if not legal:
        raise ValueError("No legal move available")

    winning_moves = [move for move in legal if apply_move(state, move).winner() == state.side_to_move]
    if winning_moves:
        return max(winning_moves, key=lambda move: _race_move_priority(state, move))

    table: Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float] = {}
    ranked: List[Tuple[float, Move]] = []
    for move in sorted(legal, key=lambda candidate: _race_move_priority(state, candidate), reverse=True):
        child = apply_move(state, move)
        score, _unused = minimax_race(child, search_depth - 1, -math.inf, math.inf, state.side_to_move, table)
        score += _race_root_adjustment(child, state.side_to_move)
        score += _race_move_adjustment(state, child, move, state.side_to_move)
        ranked.append((score, move))

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score = ranked[0][0]
    candidate_pool = [move for score, move in ranked[: profile.top_k] if score >= best_score - 35]
    if not candidate_pool:
        candidate_pool = [ranked[0][1]]

    if profile.randomness > 0.0 and len(candidate_pool) > 1 and random.random() < profile.randomness:
        return random.choice(candidate_pool)
    return ranked[0][1]


def _learned_agent_move(state: State, depth: Optional[int], difficulty: str) -> Move:
    profile = AI_PROFILES[difficulty]
    search_depth = depth if depth is not None else profile.depth

    winners = immediate_scoring_moves(state)
    if winners:
        return random.choice(winners)

    legal = get_legal_moves(state)
    if not legal:
        raise ValueError("No legal move available")

    table: Dict[Tuple[Tuple[str, ...], str, int, int, int, str, str], float] = {}
    ranked: List[Tuple[float, Move]] = []
    for move in legal:
        child = apply_move(state, move)
        score, _unused = minimax_learned(child, search_depth - 1, -math.inf, math.inf, state.side_to_move, table)
        ranked.append((score, move))

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score = ranked[0][0]
    candidate_pool = [move for score, move in ranked[: profile.top_k] if score >= best_score - 45]
    if not candidate_pool:
        candidate_pool = [ranked[0][1]]

    if profile.randomness > 0.0 and len(candidate_pool) > 1 and random.random() < profile.randomness:
        return random.choice(candidate_pool)
    return ranked[0][1]


def agent_move(state: State, depth: Optional[int] = None, difficulty: str = "medium", engine: str = ENGINE_BRUTE) -> Move:
    difficulty = normalize_difficulty(difficulty)
    engine = normalize_engine(engine)
    if engine == ENGINE_RACE:
        return _race_agent_move(state, depth, difficulty)
    if engine == ENGINE_LEARNED:
        return _learned_agent_move(state, depth, difficulty)
    return _brute_agent_move(state, depth, difficulty)


def parse_move(text: str) -> Move:
    normalized = text.strip().lower()
    if normalized.startswith("respawn-") or normalized.startswith("spawn-"):
        _, right = normalized.split("-", 1)
        to_row, to_col = map(int, right.split(","))
        return (RESPAWN_ORIGIN_ROW, to_col), (to_row, to_col)
    left, right = text.strip().split("-")
    from_row, from_col = map(int, left.split(","))
    to_row, to_col = map(int, right.split(","))
    return (from_row, from_col), (to_row, to_col)


def move_to_str(move: Move) -> str:
    if is_respawn_move(move):
        to_row, to_col = move[1]
        return f"respawn-{to_row},{to_col}"
    (from_row, from_col), (to_row, to_col) = move
    return f"{from_row},{from_col}-{to_row},{to_col}"


def side_name(side: str) -> str:
    return "White" if side == WHITE else "Black"


def parse_side(text: str) -> str:
    side = text.strip().upper()
    if side not in {WHITE, BLACK}:
        raise ValueError("side must be W or B")
    return side


legal_moves = get_legal_moves
legal_moves_from = get_legal_moves_from
