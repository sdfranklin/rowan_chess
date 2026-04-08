#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from time import perf_counter
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
    think_ms: int
    rollout_depth: int
    exploration: float
    min_iterations: int


AI_PROFILES: Dict[str, DifficultyProfile] = {
    "easy": DifficultyProfile(name="easy", think_ms=70, rollout_depth=6, exploration=1.15, min_iterations=8),
    "medium": DifficultyProfile(name="medium", think_ms=220, rollout_depth=8, exploration=1.25, min_iterations=24),
    "hard": DifficultyProfile(name="hard", think_ms=700, rollout_depth=10, exploration=1.35, min_iterations=60),
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
    scored: bool = False

    def symbol(self) -> str:
        return self.side + self.kind

    def key(self) -> str:
        return self.symbol() + ("H" if self.scored else "_")


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

    def knight_counts(self, side: str) -> Tuple[int, int]:
        scored = 0
        unscored = 0
        for row, col in self.locate(side, KNIGHT):
            if self.board[row][col].scored:
                scored += 1
            else:
                unscored += 1
        return scored, unscored

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
            flat.append(piece.key() if piece is not None else "..")
    return tuple(flat), state.side_to_move, state.white_knights_home, state.black_knights_home, 0 if state.variant == VARIANT_STANDARD else 1


def row_is_home_or_beyond(row: int, side: str, variant: str) -> bool:
    home_row_from_side = STANDARD_HOME_ROW_FROM_SIDE
    if variant == VARIANT_RESPAWN:
        home_row_from_side = RESPAWN_HOME_ROW_FROM_SIDE
    home_row = home_row_from_side - 1 if side == WHITE else ROWS - home_row_from_side
    return row >= home_row if side == WHITE else row <= home_row


def reconstruct_knight_path(state: State, move: Move) -> Optional[List[Coord]]:
    (from_row, from_col), (to_row, to_col) = move
    piece = state.board[from_row][from_col]
    if piece is None or piece.kind != KNIGHT:
        return None

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

    return build_path(state.board, (from_row, from_col), [])


def knight_move_reaches_home(state: State, move: Move) -> bool:
    (from_row, from_col), _destination = move
    piece = state.board[from_row][from_col]
    if piece is None or piece.kind != KNIGHT or piece.scored:
        return False
    path = reconstruct_knight_path(state, move)
    if path is None:
        return False
    return any(row_is_home_or_beyond(row, piece.side, state.variant) for row, _col in path)


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
        path = reconstruct_knight_path(next_state, move)
        if path is None:
            raise ValueError(f"Could not reconstruct knight path for move {move}")

        current_row, current_col = from_row, from_col
        moving_piece = piece
        scored_this_move = False
        for next_row, next_col in path:
            landing = next_state.board[next_row][next_col]
            next_state.board[current_row][current_col] = None
            if landing is not None and landing.side == enemy and landing.kind == PAWN:
                next_state.board[next_row][next_col] = None
            if not moving_piece.scored and row_is_home_or_beyond(next_row, moving_piece.side, state.variant):
                moving_piece = Piece(moving_piece.side, moving_piece.kind, True)
                scored_this_move = True
            next_state.board[next_row][next_col] = moving_piece
            current_row, current_col = next_row, next_col

    if piece.kind == KNIGHT and scored_this_move:
        if piece.side == WHITE:
            next_state.white_knights_home += 1
        if piece.side == BLACK:
            next_state.black_knights_home += 1

    next_state.side_to_move = state.enemy(state.side_to_move)
    return next_state


def immediate_scoring_moves(state: State) -> List[Move]:
    scoring: List[Move] = []
    for move in get_legal_moves(state):
        (from_row, from_col), (_to_row, _to_col) = move
        piece = state.board[from_row][from_col]
        if piece is not None and piece.kind == KNIGHT and not piece.scored and knight_move_reaches_home(state, move):
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
    score = 900 * (my_home - opp_home)

    my_pawns = len(state.locate(side, PAWN))
    opp_pawns = len(state.locate(enemy, PAWN))
    my_scored_knights, my_unscored_knights = state.knight_counts(side)
    opp_scored_knights, opp_unscored_knights = state.knight_counts(enemy)
    score += 70 * (my_pawns - opp_pawns)
    score += 260 * (my_unscored_knights - opp_unscored_knights)
    score += 55 * (my_scored_knights - opp_scored_knights)

    my_mobility_state = state.clone()
    my_mobility_state.side_to_move = side
    opp_mobility_state = state.clone()
    opp_mobility_state.side_to_move = enemy
    score += 3 * (len(get_legal_moves(my_mobility_state)) - len(get_legal_moves(opp_mobility_state)))

    my_threats = len(immediate_scoring_moves(my_mobility_state))
    opp_threats = len(immediate_scoring_moves(opp_mobility_state))
    score += 180 * my_threats
    score -= 520 * opp_threats

    my_knight_targets = threatened_targets(state, enemy, KNIGHT)
    opp_knight_targets = threatened_targets(state, side, KNIGHT)
    my_scored_threats = sum(1 for row, col in my_knight_targets if state.board[row][col].scored)
    my_unscored_threats = len(my_knight_targets) - my_scored_threats
    opp_scored_threats = sum(1 for row, col in opp_knight_targets if state.board[row][col].scored)
    opp_unscored_threats = len(opp_knight_targets) - opp_scored_threats
    score -= 320 * my_unscored_threats
    score -= 60 * my_scored_threats
    score += 190 * opp_unscored_threats
    score += 25 * opp_scored_threats

    my_pawn_targets = threatened_targets(state, enemy, PAWN)
    opp_pawn_targets = threatened_targets(state, side, PAWN)
    score -= 24 * len(my_pawn_targets)
    score += 18 * len(opp_pawn_targets)

    if my_scored_knights + my_unscored_knights == 1:
        score -= 280
    if opp_scored_knights + opp_unscored_knights == 1:
        score += 170

    my_target_row = state.target_row(side)
    opp_target_row = state.target_row(enemy)
    for row, col in state.locate(side, KNIGHT):
        piece = state.board[row][col]
        if not piece.scored:
            score += 28 * (ROWS - abs(my_target_row - row))
            score += 8 * (2 - abs(2 - col))
    for row, col in state.locate(enemy, KNIGHT):
        piece = state.board[row][col]
        if not piece.scored:
            score -= 28 * (ROWS - abs(opp_target_row - row))
            score -= 8 * (2 - abs(2 - col))

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
    my_knight_targets = threatened_targets(state, enemy, KNIGHT)
    opp_knight_targets = threatened_targets(state, side, KNIGHT)

    adjustment = 0.0
    adjustment += 140 * my_scoring
    adjustment -= 520 * enemy_scoring
    for row, col in my_knight_targets:
        adjustment -= 60 if state.board[row][col].scored else 300
    for row, col in opp_knight_targets:
        adjustment += 20 if state.board[row][col].scored else 180

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
    if piece is not None and piece.kind == KNIGHT and knight_move_reaches_home(state, move):
        priority += 1000
    if piece is not None and piece.kind == KNIGHT and not piece.scored:
        priority += 80
    if target is not None:
        priority += 100
        if target.kind == KNIGHT:
            priority += 25 if target.scored else 180
    return priority


def _heuristic_outcome(state: State, root_side: str) -> float:
    winner = state.winner()
    if winner == root_side:
        return 1.0
    if winner == state.enemy(root_side):
        return -1.0
    return math.tanh(evaluate(state, root_side) / 1400.0)


def _rollout_move_score(state: State, move: Move) -> float:
    side = state.side_to_move
    enemy = state.enemy(side)
    from_square, to_square = move
    piece = state.board[from_square[0]][from_square[1]]
    target = None if is_respawn_move(move) else state.board[to_square[0]][to_square[1]]
    child = apply_move(state, move)
    winner = child.winner()
    if winner == side:
        return 100000.0
    if winner == enemy:
        return -100000.0

    score = 0.0
    if piece is not None and piece.kind == KNIGHT and not piece.scored and knight_move_reaches_home(state, move):
        score += 1800.0
    if target is not None:
        if target.kind == KNIGHT:
            score += 25.0 if target.scored else 320.0
        else:
            score += 55.0

    my_probe = child.clone()
    my_probe.side_to_move = side
    enemy_probe = child.clone()
    enemy_probe.side_to_move = enemy
    score += 240.0 * len(immediate_scoring_moves(my_probe))
    score -= 950.0 * len(immediate_scoring_moves(enemy_probe))

    if piece is not None and piece.kind == KNIGHT:
        moved_piece = child.board[to_square[0]][to_square[1]]
        if moved_piece is not None:
            threatened = any(coord == to_square for coord in threatened_targets(child, enemy, KNIGHT))
            if threatened:
                score -= 45.0 if moved_piece.scored else 340.0
            if piece.scored:
                score -= 20.0
    return score


def _pick_rollout_move(state: State) -> Move:
    legal = get_legal_moves(state)
    if len(legal) == 1:
        return legal[0]

    ranked = sorted(
        ((_rollout_move_score(state, move), move) for move in legal),
        key=lambda item: item[0],
        reverse=True,
    )
    top = [move for _score, move in ranked[: min(4, len(ranked))]]
    weights = [1.0, 0.55, 0.28, 0.14][: len(top)]
    return random.choices(top, weights=weights, k=1)[0]


@dataclass
class SearchNode:
    state: State
    parent: Optional["SearchNode"] = None
    move: Optional[Move] = None
    children: List["SearchNode"] = field(default_factory=list)
    unexpanded_moves: Optional[List[Move]] = None
    visits: int = 0
    value_sum: float = 0.0


def _initialize_node_moves(node: SearchNode) -> None:
    if node.unexpanded_moves is not None:
        return
    node.unexpanded_moves = sorted(get_legal_moves(node.state), key=lambda move: _rollout_move_score(node.state, move), reverse=True)


def _expand_node(node: SearchNode) -> SearchNode:
    _initialize_node_moves(node)
    if not node.unexpanded_moves:
        return node
    move = node.unexpanded_moves.pop(0)
    child = SearchNode(state=apply_move(node.state, move), parent=node, move=move)
    node.children.append(child)
    return child


def _select_child(node: SearchNode, root_side: str, exploration: float) -> SearchNode:
    assert node.children
    log_visits = math.log(max(1, node.visits))
    best_child = node.children[0]
    best_score = -math.inf
    for child in node.children:
        if child.visits == 0:
            score = math.inf
        else:
            mean = child.value_sum / child.visits
            perspective_score = mean if node.state.side_to_move == root_side else -mean
            score = perspective_score + exploration * math.sqrt(log_visits / child.visits)
        if score > best_score:
            best_score = score
            best_child = child
    return best_child


def _rollout(state: State, root_side: str, rollout_depth: int) -> float:
    cursor = state
    for _ply in range(rollout_depth):
        winner = cursor.winner()
        if winner is not None:
            return 1.0 if winner == root_side else -1.0
        if not get_legal_moves(cursor):
            break
        cursor = apply_move(cursor, _pick_rollout_move(cursor))
    return _heuristic_outcome(cursor, root_side)


def _winning_moves(state: State) -> List[Move]:
    side = state.side_to_move
    return [move for move in get_legal_moves(state) if apply_move(state, move).winner() == side]


def _mcts_move(state: State, profile: DifficultyProfile, rollout_depth_override: Optional[int] = None) -> Move:
    legal = get_legal_moves(state)
    if not legal:
        raise ValueError("No legal move available")
    if len(legal) == 1:
        return legal[0]

    forced_wins = _winning_moves(state)
    if forced_wins:
        return max(forced_wins, key=lambda move: _rollout_move_score(state, move))

    rollout_depth = max(4, rollout_depth_override if rollout_depth_override is not None else profile.rollout_depth)
    root_side = state.side_to_move
    root = SearchNode(state=state)
    deadline = perf_counter() + (profile.think_ms / 1000.0)
    iterations = 0

    while iterations < profile.min_iterations or perf_counter() < deadline:
        node = root
        while node.state.winner() is None:
            _initialize_node_moves(node)
            if node.unexpanded_moves:
                node = _expand_node(node)
                break
            if not node.children:
                break
            node = _select_child(node, root_side, profile.exploration)

        result = _rollout(node.state, root_side, rollout_depth)
        cursor: Optional[SearchNode] = node
        while cursor is not None:
            cursor.visits += 1
            cursor.value_sum += result
            cursor = cursor.parent
        iterations += 1

    if not root.children:
        return max(legal, key=lambda move: _rollout_move_score(state, move))

    best_child = max(
        root.children,
        key=lambda child: (child.visits, child.value_sum / max(1, child.visits)),
    )
    assert best_child.move is not None
    return best_child.move


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
    return _mcts_move(state, profile, rollout_depth_override=depth)


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
