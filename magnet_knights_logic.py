#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, List, Optional, Tuple

ROWS = 7
COLS = 5
WHITE = "W"
BLACK = "B"
PAWN = "P"
KNIGHT = "N"
VARIANT_STANDARD = "standard"
VARIANT_RESPAWN = "respawn"
STANDARD_HOME_ROW_FROM_SIDE = 5
RESPAWN_HOME_ROW_FROM_SIDE = 6
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
    "easy": DifficultyProfile(name="easy", depth=2, randomness=0.25, top_k=2),
    "medium": DifficultyProfile(name="medium", depth=3, randomness=0.05, top_k=2),
    "hard": DifficultyProfile(name="hard", depth=4, randomness=0.0, top_k=1),
}


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


def threatened_targets(state: State, by_side: str, kind: Optional[str] = None) -> List[Coord]:
    probe = state.clone()
    probe.side_to_move = by_side
    threatened = set()
    for move in get_legal_moves(probe):
        _start, destination = move
        piece = state.board[destination[0]][destination[1]]
        if piece is None:
            continue
        if kind is not None and piece.kind != kind:
            continue
        threatened.add(destination)
    return sorted(threatened)


def evaluate(state: State, side: str) -> float:
    winner = state.winner()
    if winner == side:
        return 1e6
    if winner == state.enemy(side):
        return -1e6

    enemy = state.enemy(side)
    my_home = state.white_knights_home if side == WHITE else state.black_knights_home
    opp_home = state.black_knights_home if side == WHITE else state.white_knights_home
    score = 520 * (my_home - opp_home)

    my_pawns = len(state.locate(side, PAWN))
    my_knights = len(state.locate(side, KNIGHT))
    opp_pawns = len(state.locate(enemy, PAWN))
    opp_knights = len(state.locate(enemy, KNIGHT))
    score += 28 * (my_pawns - opp_pawns)
    score += 280 * (my_knights - opp_knights)

    my_mobility_state = state.clone()
    my_mobility_state.side_to_move = side
    opp_mobility_state = state.clone()
    opp_mobility_state.side_to_move = enemy
    score += 3 * (len(get_legal_moves(my_mobility_state)) - len(get_legal_moves(opp_mobility_state)))

    my_threats = len(immediate_scoring_moves(my_mobility_state))
    opp_threats = len(immediate_scoring_moves(opp_mobility_state))
    score += 120 * my_threats
    score -= 380 * opp_threats

    my_knight_targets = threatened_targets(state, enemy, KNIGHT)
    opp_knight_targets = threatened_targets(state, side, KNIGHT)
    score -= 240 * len(my_knight_targets)
    score += 140 * len(opp_knight_targets)

    my_pawn_targets = threatened_targets(state, enemy, PAWN)
    opp_pawn_targets = threatened_targets(state, side, PAWN)
    score -= 24 * len(my_pawn_targets)
    score += 18 * len(opp_pawn_targets)

    if my_knights == 1:
        score -= 220
    if opp_knights == 1:
        score += 150

    my_target_row = state.target_row(side)
    opp_target_row = state.target_row(enemy)
    for row, col in state.locate(side, KNIGHT):
        score += 14 * (ROWS - abs(my_target_row - row))
        score += 5 * (2 - abs(2 - col))
    for row, col in state.locate(enemy, KNIGHT):
        score -= 14 * (ROWS - abs(opp_target_row - row))
        score -= 5 * (2 - abs(2 - col))

    for row, _col in state.locate(side, PAWN):
        score += 3 * (ROWS - abs(my_target_row - row))
    for row, _col in state.locate(enemy, PAWN):
        score -= 3 * (ROWS - abs(opp_target_row - row))

    return float(score)


def minimax(
    state: State,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: str,
    table: Optional[Dict[Tuple[Tuple[str, ...], str, int, int, int, str], float]] = None,
) -> Tuple[float, Optional[Move]]:
    if table is None:
        table = {}

    winner = state.winner()
    moves = get_legal_moves(state)
    if depth == 0 or winner is not None or not moves:
        return evaluate(state, maximizing_for), None

    cache_key = board_key(state) + (depth, maximizing_for)
    if cache_key in table:
        return table[cache_key], None

    ordered_moves = sorted(
        moves,
        key=lambda move: _move_priority(state, move),
        reverse=True,
    )
    best_move: Optional[Move] = None
    maximizing = state.side_to_move == maximizing_for

    if maximizing:
        value = -math.inf
        for move in ordered_moves:
            child = apply_move(state, move)
            child_value, _unused = minimax(
                child,
                depth - 1,
                alpha,
                beta,
                maximizing_for,
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
        child_value, _unused = minimax(
            child,
            depth - 1,
            alpha,
            beta,
            maximizing_for,
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


def _root_tactical_adjustment(state: State, side: str) -> float:
    enemy = state.enemy(side)
    enemy_probe = state.clone()
    enemy_probe.side_to_move = enemy
    my_probe = state.clone()
    my_probe.side_to_move = side

    enemy_scoring = len(immediate_scoring_moves(enemy_probe))
    my_scoring = len(immediate_scoring_moves(my_probe))
    my_knight_targets = len(threatened_targets(state, enemy, KNIGHT))
    opp_knight_targets = len(threatened_targets(state, side, KNIGHT))

    adjustment = 0.0
    adjustment += 140 * my_scoring
    adjustment -= 520 * enemy_scoring
    adjustment -= 260 * my_knight_targets
    adjustment += 140 * opp_knight_targets

    my_knights = state.live_knights(side)
    opp_knights = state.live_knights(enemy)
    if my_knights == 1 and my_knight_targets:
        adjustment -= 420
    if opp_knights == 1 and opp_knight_targets:
        adjustment += 220
    return adjustment


def _move_priority(state: State, move: Move) -> int:
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


def normalize_difficulty(difficulty: str) -> str:
    normalized = difficulty.strip().lower()
    if normalized not in AI_PROFILES:
        raise ValueError(f"difficulty must be one of: {', '.join(sorted(AI_PROFILES))}")
    return normalized


def difficulty_names() -> Tuple[str, ...]:
    return tuple(AI_PROFILES.keys())


def agent_move(state: State, depth: Optional[int] = None, difficulty: str = "medium") -> Move:
    difficulty = normalize_difficulty(difficulty)
    profile = AI_PROFILES[difficulty]
    search_depth = max(1, depth if depth is not None else profile.depth)

    legal = get_legal_moves(state)
    if not legal:
        raise ValueError("No legal move available")

    table: Dict[Tuple[Tuple[str, ...], str, int, int, int, str], float] = {}
    ranked: List[Tuple[float, Move]] = []
    for move in sorted(legal, key=lambda move: _move_priority(state, move), reverse=True):
        child = apply_move(state, move)
        score, _unused = minimax(
            child,
            search_depth - 1,
            -math.inf,
            math.inf,
            state.side_to_move,
            table,
        )
        score += _root_tactical_adjustment(child, state.side_to_move)
        ranked.append((score, move))

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score = ranked[0][0]
    candidate_pool = [move for score, move in ranked[: profile.top_k] if score >= best_score - 20]
    if not candidate_pool:
        candidate_pool = [ranked[0][1]]

    if profile.randomness > 0.0 and len(candidate_pool) > 1 and random.random() < profile.randomness:
        return random.choice(candidate_pool)
    return ranked[0][1]


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
