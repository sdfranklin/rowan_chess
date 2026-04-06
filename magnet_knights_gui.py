#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import os
import random
from typing import Optional, Tuple

import pygame

from magnet_knights_logic import (
    AI_PROFILES,
    BLACK,
    COLS,
    KNIGHT,
    Move,
    PAWN,
    Piece,
    RESPAWN_ROW_FROM_SIDE,
    ROWS,
    State,
    VARIANT_RESPAWN,
    VARIANT_STANDARD,
    WHITE,
    agent_move,
    apply_move,
    difficulty_names,
    default_state,
    get_legal_moves,
    get_legal_moves_from,
    is_respawn_move,
    move_to_str,
    side_name,
)

Coord = Tuple[int, int]

PLAY_MODE_AI = "ai"
PLAY_MODE_HOTSEAT = "hotseat"


def clamp(value: float, lower: float, upper: float) -> int:
    return int(max(lower, min(upper, value)))


def with_alpha(color: Tuple[int, int, int], alpha: int) -> Tuple[int, int, int, int]:
    return color[0], color[1], color[2], alpha


def mix(a: Tuple[int, int, int], b: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    return (
        clamp(a[0] + (b[0] - a[0]) * amount, 0, 255),
        clamp(a[1] + (b[1] - a[1]) * amount, 0, 255),
        clamp(a[2] + (b[2] - a[2]) * amount, 0, 255),
    )


def font(name: str, size: int, bold: bool = False) -> "pygame.font.Font":
    return pygame.font.SysFont(name, size, bold=bold)


@dataclass
class Animation:
    move: Move
    piece: Piece
    start_ms: int
    duration_ms: int
    next_state: State

    def progress(self, now_ms: int) -> float:
        return max(0.0, min(1.0, (now_ms - self.start_ms) / self.duration_ms))


@dataclass
class ConfettiParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    color: Tuple[int, int, int]
    ttl_ms: int

    def advance(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15
        self.ttl_ms -= 16


@dataclass
class UIButton:
    key: str
    label: str
    rect: pygame.Rect
    enabled: bool = True


@dataclass
class SetupChoice:
    side: str
    gap_col: int
    rect: pygame.Rect


@dataclass(frozen=True)
class GUISettings:
    window_size: Tuple[int, int] = (980, 920)
    tile_size: int = 94
    board_top: int = 112
    animation_ms: int = 200
    background_top: Tuple[int, int, int] = (255, 247, 232)
    background_bottom: Tuple[int, int, int] = (255, 236, 205)
    checker_red: Tuple[int, int, int] = (243, 100, 87)
    checker_yellow: Tuple[int, int, int] = (255, 209, 77)
    seam: Tuple[int, int, int] = (255, 249, 231)
    seam_dark: Tuple[int, int, int] = (205, 141, 84)
    board_shadow: Tuple[int, int, int] = (164, 121, 74)
    panel: Tuple[int, int, int] = (255, 253, 248)
    panel_border: Tuple[int, int, int] = (235, 194, 145)
    panel_text: Tuple[int, int, int] = (88, 48, 29)
    muted: Tuple[int, int, int] = (140, 98, 74)
    white_pawn: Tuple[int, int, int] = (227, 68, 54)
    black_pawn: Tuple[int, int, int] = (248, 210, 55)
    white_knight: Tuple[int, int, int] = (67, 129, 255)
    black_knight: Tuple[int, int, int] = (149, 88, 221)
    selection: Tuple[int, int, int] = (250, 246, 158)
    move_hint: Tuple[int, int, int] = (85, 232, 198)
    last_move: Tuple[int, int, int] = (255, 255, 255)
    tile_outline: Tuple[int, int, int] = (255, 255, 255)
    overlay: Tuple[int, int, int] = (80, 35, 18)
    button_fill: Tuple[int, int, int] = (255, 241, 214)
    button_fill_active: Tuple[int, int, int] = (255, 226, 169)
    button_border: Tuple[int, int, int] = (210, 154, 86)
    button_text: Tuple[int, int, int] = (102, 56, 31)
    button_disabled: Tuple[int, int, int] = (223, 204, 190)


class MagnetKnightsGUI:
    def __init__(
        self,
        play_mode: str = PLAY_MODE_AI,
        agent_side: str = BLACK,
        depth: Optional[int] = None,
        difficulty: str = "medium",
        variant: str = VARIANT_STANDARD,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("Magnet Knights")

        self.settings = GUISettings()
        self.depth = depth
        self.difficulty_cycle = difficulty_names()
        self.difficulty = difficulty if difficulty in AI_PROFILES else "medium"
        self.play_mode = play_mode
        self.agent_side = agent_side
        self.variant = variant if variant in {VARIANT_STANDARD, VARIANT_RESPAWN} else VARIANT_STANDARD
        self.animation: Optional[Animation] = None
        self.ai_due_ms = 0
        self.selected: Optional[Coord] = None
        self.last_move: Optional[Move] = None
        self.status_message = ""
        self.confetti: list[ConfettiParticle] = []
        self.celebrated_winner: Optional[str] = None
        self.buttons: list[UIButton] = []
        self.setup_choices: list[SetupChoice] = []
        self.setup_option_buttons: list[UIButton] = []
        self.setup_start_button: Optional[UIButton] = None
        self.white_gap = 2
        self.black_gap = 2
        self.setup_mode = False
        self.setup_stage = "idle"

        self.window_size = self.settings.window_size
        self.screen = pygame.display.set_mode(self.window_size)
        self.clock = pygame.time.Clock()

        self.tile_size = self.settings.tile_size
        self.board_width = self.tile_size * COLS
        self.board_height = self.tile_size * (ROWS - 1)
        self.board_left = (self.window_size[0] - self.board_width) // 2
        self.board_top = self.settings.board_top
        self.board_rect = pygame.Rect(self.board_left, self.board_top, self.board_width, self.board_height)
        self.status_rect = pygame.Rect(56, 34, self.window_size[0] - 112, 60)
        self.footer_rect = pygame.Rect(72, self.board_rect.bottom + 22, self.window_size[0] - 144, 124)

        self.title_font = font("Avenir Next", 38, bold=True)
        self.body_font = font("Avenir Next", 20)
        self.small_font = font("Avenir Next", 16)
        self.row_font = font("Avenir Next", 18, bold=True)
        self.button_font = font("Avenir Next", 18, bold=True)

        self.colors = {
            "bg_top": self.settings.background_top,
            "bg_bottom": self.settings.background_bottom,
            "board_shadow": self.settings.board_shadow,
            "panel": self.settings.panel,
            "panel_border": self.settings.panel_border,
            "panel_text": self.settings.panel_text,
            "muted": self.settings.muted,
            "selection": self.settings.selection,
            "move_hint": self.settings.move_hint,
            "last_move": self.settings.last_move,
            "seam": self.settings.seam,
            "seam_dark": self.settings.seam_dark,
            "tile_outline": self.settings.tile_outline,
        }

        self.state = default_state(self.white_gap, self.black_gap, variant=self.variant)
        self.reset_game()
        self.enter_setup_mode()

        auto_quit_ms = int(os.environ.get("MAGNET_KNIGHTS_AUTOCLOSE_MS", "0") or "0")
        if auto_quit_ms > 0:
            pygame.time.set_timer(pygame.QUIT, auto_quit_ms, loops=1)

    def winning_reason(self, winner: str) -> str:
        if self.state.white_knights_home >= 2 or self.state.black_knights_home >= 2:
            return f"{side_name(winner)} wins by bringing home two knights."

        white_live = self.state.live_knights(WHITE)
        black_live = self.state.live_knights(BLACK)
        if white_live <= 1 and black_live <= 1:
            return f"{side_name(winner)} wins on the one-home low-knight rule."
        if not get_legal_moves(self.state):
            loser = side_name(self.state.side_to_move)
            return f"{side_name(winner)} wins because {loser} has no legal moves."
        return f"{side_name(winner)} wins by keeping the last remaining knight."

    def current_winner(self) -> Optional[str]:
        winner = self.state.winner()
        if winner is not None:
            return winner
        if not get_legal_moves(self.state):
            return WHITE if self.state.side_to_move == BLACK else BLACK
        return None

    def setup_visible_side(self) -> Optional[str]:
        if self.setup_stage in {"white_pick", "player_white"}:
            return WHITE
        if self.setup_stage in {"black_pick", "player_black"}:
            return BLACK
        return None

    def setup_button_label(self) -> str:
        if self.setup_stage == "white_pick":
            return "Lock White Choice"
        if self.setup_stage == "pass_black":
            return "Black Turn"
        return "Start Match"

    def reset_game(self, keep_mode: bool = True) -> None:
        if not keep_mode:
            self.play_mode = PLAY_MODE_AI
            self.agent_side = BLACK
        self.setup_mode = False
        self.setup_stage = "idle"
        self.state = default_state(self.white_gap, self.black_gap, variant=self.variant)
        self.animation = None
        self.ai_due_ms = 0
        self.selected = None
        self.last_move = None
        self.confetti = []
        self.celebrated_winner = None
        self.refresh_status()
        self.schedule_ai()

    def enter_setup_mode(self) -> None:
        self.setup_mode = True
        if self.play_mode == PLAY_MODE_AI:
            if self.human_side() == WHITE:
                self.black_gap = random.randrange(COLS)
                self.setup_stage = "player_white"
            else:
                self.white_gap = random.randrange(COLS)
                self.setup_stage = "player_black"
        else:
            self.setup_stage = "white_pick"
        self.state = default_state(self.white_gap, self.black_gap, variant=self.variant)
        self.animation = None
        self.ai_due_ms = 0
        self.selected = None
        self.last_move = None
        self.confetti = []
        self.celebrated_winner = None
        self.refresh_status()

    def start_match(self) -> None:
        self.reset_game()

    def advance_setup(self) -> None:
        if self.setup_stage == "white_pick":
            self.setup_stage = "pass_black"
            self.refresh_status()
        elif self.setup_stage == "pass_black":
            self.setup_stage = "black_pick"
            self.refresh_status()
        else:
            self.start_match()

    def human_side(self) -> Optional[str]:
        if self.play_mode == PLAY_MODE_HOTSEAT:
            return None
        return WHITE if self.agent_side == BLACK else BLACK

    def current_input_side(self) -> str:
        return self.state.side_to_move

    def is_human_turn(self) -> bool:
        if self.setup_mode:
            return False
        if self.play_mode == PLAY_MODE_HOTSEAT:
            return True
        return self.state.side_to_move != self.agent_side

    def schedule_ai(self) -> None:
        if self.setup_mode:
            self.ai_due_ms = 0
            return
        if self.play_mode != PLAY_MODE_AI or self.current_winner() is not None:
            self.ai_due_ms = 0
            return
        if not get_legal_moves(self.state) or self.state.side_to_move != self.agent_side:
            self.ai_due_ms = 0
            return
        self.ai_due_ms = pygame.time.get_ticks() + 320

    def cycle_difficulty(self) -> None:
        current_index = self.difficulty_cycle.index(self.difficulty)
        self.difficulty = self.difficulty_cycle[(current_index + 1) % len(self.difficulty_cycle)]
        self.refresh_status()

    def trigger_celebration(self, winner: str) -> None:
        if self.celebrated_winner == winner:
            return
        self.celebrated_winner = winner
        palette = [
            self.settings.white_pawn,
            self.settings.black_pawn,
            self.settings.white_knight,
            self.settings.black_knight,
            self.settings.selection,
            self.settings.move_hint,
        ]
        self.confetti = []
        for _ in range(120):
            self.confetti.append(
                ConfettiParticle(
                    x=random.uniform(self.board_left - 20, self.board_left + self.board_width + 20),
                    y=random.uniform(-120, -20),
                    vx=random.uniform(-2.6, 2.6),
                    vy=random.uniform(1.0, 4.8),
                    size=random.randint(6, 12),
                    color=random.choice(palette),
                    ttl_ms=random.randint(900, 1800),
                )
            )

    def refresh_status(self) -> None:
        if self.setup_mode:
            if self.setup_stage == "white_pick":
                self.status_message = "White: choose your opening gap without showing Black."
            elif self.setup_stage == "pass_black":
                self.status_message = "White is locked in. Pass the device to Black."
            elif self.setup_stage == "black_pick":
                self.status_message = "Black: choose your opening gap without seeing White."
            else:
                self.status_message = "Choose your opening gap. The other side stays hidden until the match starts."
            return
        winner = self.current_winner()
        if winner is not None:
            self.trigger_celebration(winner)
            self.status_message = self.winning_reason(winner)
            return
        if not get_legal_moves(self.state):
            self.status_message = f"No legal moves for {side_name(self.state.side_to_move)}."
            return
        if self.animation is not None:
            self.status_message = f"{side_name(self.animation.piece.side)} piece is gliding along the seam."
            return
        if self.play_mode == PLAY_MODE_AI and self.state.side_to_move == self.agent_side:
            self.status_message = f"{side_name(self.agent_side)} agent is choosing a move."
            return
        if self.selected is not None:
            row, col = self.selected
            piece = self.state.board[row][col]
            if piece is not None:
                name = "knight" if piece.kind == KNIGHT else "pawn"
                self.status_message = f"Selected {side_name(piece.side).lower()} {name}. Pick a glowing seam position."
                return
        respawn_moves = self.respawn_moves_by_destination()
        if self.variant == VARIANT_RESPAWN and respawn_moves:
            row_label = RESPAWN_ROW_FROM_SIDE
            self.status_message = f"{side_name(self.state.side_to_move)} can respawn a pawn on row {row_label}. Click a glowing row {row_label} seam."
            return
        if self.play_mode == PLAY_MODE_HOTSEAT:
            self.status_message = f"{side_name(self.state.side_to_move)} to move."
        else:
            self.status_message = (
                f"You are {side_name(self.human_side() or WHITE)}. "
                f"Difficulty: {self.difficulty.capitalize()}. Select a piece on the seam."
            )

    def position_to_pixel(self, coord: Coord) -> Tuple[float, float]:
        row, col = coord
        x = self.board_left + col * self.tile_size + self.tile_size / 2
        y = self.board_top + ((ROWS - 1) - row) * self.tile_size
        return x, y

    def point_to_coord(self, point: Tuple[int, int]) -> Optional[Coord]:
        best_coord: Optional[Coord] = None
        best_distance = self.tile_size * 0.34
        for row in range(ROWS):
            for col in range(COLS):
                x, y = self.position_to_pixel((row, col))
                distance = ((point[0] - x) ** 2 + (point[1] - y) ** 2) ** 0.5
                if distance <= best_distance:
                    best_coord = (row, col)
                    best_distance = distance
        return best_coord

    def respawn_moves_by_destination(self) -> dict[Coord, Move]:
        return {
            move[1]: move
            for move in get_legal_moves(self.state)
            if is_respawn_move(move)
        }

    def start_move(self, move: Move) -> None:
        if is_respawn_move(move):
            self.state = apply_move(self.state, move)
            self.last_move = move
            self.selected = None
            self.ai_due_ms = 0
            self.refresh_status()
            self.schedule_ai()
            return
        from_row, from_col = move[0]
        piece = self.state.board[from_row][from_col]
        assert piece is not None

        duration_ms = self.settings.animation_ms
        next_state = apply_move(self.state, move)
        self.animation = Animation(
            move=move,
            piece=piece,
            start_ms=pygame.time.get_ticks(),
            duration_ms=duration_ms,
            next_state=next_state,
        )
        self.selected = None
        self.ai_due_ms = 0
        self.refresh_status()

    def animate_move(self, now_ms: int) -> None:
        if self.animation is None:
            return
        if self.animation.progress(now_ms) < 1.0:
            return
        self.state = self.animation.next_state
        self.last_move = self.animation.move
        self.animation = None
        self.refresh_status()
        self.schedule_ai()

    def maybe_start_ai(self, now_ms: int) -> None:
        if self.setup_mode:
            return
        if self.animation is not None:
            return
        if self.play_mode != PLAY_MODE_AI or self.current_winner() is not None:
            return
        if self.ai_due_ms and now_ms >= self.ai_due_ms and self.state.side_to_move == self.agent_side:
            move = agent_move(self.state, depth=self.depth, difficulty=self.difficulty)
            self.start_move(move)

    def toggle_mode(self) -> None:
        reopen_setup = self.setup_mode
        self.play_mode = PLAY_MODE_HOTSEAT if self.play_mode == PLAY_MODE_AI else PLAY_MODE_AI
        self.reset_game()
        if reopen_setup:
            self.enter_setup_mode()

    def swap_agent_side(self) -> None:
        if self.play_mode != PLAY_MODE_AI:
            return
        reopen_setup = self.setup_mode
        self.agent_side = WHITE if self.agent_side == BLACK else BLACK
        self.reset_game()
        if reopen_setup:
            self.enter_setup_mode()

    def build_buttons(self) -> list[UIButton]:
        items = [
            ("restart", "Rematch (R)" if self.current_winner() is not None else "Restart (R)", True),
            ("opening", "Opening Layout (O)", True),
        ]

        buttons: list[UIButton] = []
        x = self.footer_rect.x + 22
        y = self.footer_rect.y + 76
        gap = 12
        for key, label, enabled in items:
            width = max(118, self.button_font.size(label)[0] + 24)
            rect = pygame.Rect(x, y, width, 38)
            buttons.append(UIButton(key=key, label=label, rect=rect, enabled=enabled))
            x += width + gap
        return buttons

    def handle_button_click(self, point: Tuple[int, int]) -> bool:
        for button in self.buttons:
            if not button.enabled or not button.rect.collidepoint(point):
                continue
            if button.key == "restart":
                self.reset_game()
            elif button.key == "opening":
                self.enter_setup_mode()
            return True
        return False

    def handle_click(self, point: Tuple[int, int]) -> None:
        if self.setup_mode:
            if self.handle_setup_click(point):
                return
            self.handle_button_click(point)
            return
        if self.handle_button_click(point):
            return
        if self.animation is not None or self.current_winner() is not None or not self.is_human_turn():
            return

        clicked = self.point_to_coord(point)
        if clicked is None:
            self.selected = None
            self.refresh_status()
            return

        if self.selected is None:
            respawn_moves = self.respawn_moves_by_destination()
            if clicked in respawn_moves:
                self.start_move(respawn_moves[clicked])
                return

        if self.selected is not None:
            candidate_moves = {move[1]: move for move in get_legal_moves_from(self.state, self.selected)}
            if clicked in candidate_moves:
                self.start_move(candidate_moves[clicked])
                return

        row, col = clicked
        piece = self.state.board[row][col]
        if piece is not None and piece.side == self.current_input_side():
            if get_legal_moves_from(self.state, clicked):
                self.selected = clicked
            else:
                self.selected = None
        else:
            self.selected = None
        self.refresh_status()

    def draw_gradient_background(self) -> None:
        width, height = self.window_size
        for y in range(height):
            amount = y / max(1, height - 1)
            color = mix(self.colors["bg_top"], self.colors["bg_bottom"], amount)
            pygame.draw.line(self.screen, color, (0, y), (width, y))

    def update_confetti(self) -> None:
        updated: list[ConfettiParticle] = []
        for particle in self.confetti:
            particle.advance()
            if particle.ttl_ms > 0 and particle.y < self.window_size[1] + 30:
                updated.append(particle)
        self.confetti = updated

    def draw_panel(self, rect: pygame.Rect) -> None:
        shadow = pygame.Surface((rect.width + 24, rect.height + 24), pygame.SRCALPHA)
        pygame.draw.rect(
            shadow,
            with_alpha(self.colors["board_shadow"], 40),
            shadow.get_rect(),
            border_radius=24,
        )
        self.screen.blit(shadow, (rect.x - 12, rect.y + 10))
        pygame.draw.rect(self.screen, self.colors["panel"], rect, border_radius=20)
        pygame.draw.rect(self.screen, self.colors["panel_border"], rect, 2, border_radius=20)

    def draw_buttons(self) -> None:
        self.buttons = self.build_buttons()
        for button in self.buttons:
            fill = self.settings.button_fill_active if button.enabled else self.settings.button_disabled
            border = self.settings.button_border if button.enabled else self.colors["panel_border"]
            text_color = self.settings.button_text if button.enabled else self.colors["muted"]
            pygame.draw.rect(self.screen, fill, button.rect, border_radius=14)
            pygame.draw.rect(self.screen, border, button.rect, 2, border_radius=14)
            label = self.button_font.render(button.label, True, text_color)
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def setup_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self.board_left - 30, self.board_top + 84, self.board_width + 60, 390)

    def build_setup_widgets(self) -> tuple[list[SetupChoice], list[UIButton], UIButton]:
        panel = self.setup_panel_rect()
        card_width = 96
        card_height = 84
        gap = 12
        total_width = card_width * COLS + gap * (COLS - 1)
        start_x = panel.centerx - total_width // 2
        card_y = panel.y + 202

        choices: list[SetupChoice] = []
        visible_side = self.setup_visible_side()
        if visible_side is not None:
            for col in range(COLS):
                x = start_x + col * (card_width + gap)
                choices.append(SetupChoice(side=visible_side, gap_col=col, rect=pygame.Rect(x, card_y, card_width, card_height)))

        option_buttons: list[UIButton] = []
        option_buttons.extend(
            [
                UIButton("setup_mode_ai", "Human vs AI", pygame.Rect(panel.x + 28, panel.y + 92, 146, 34), True),
                UIButton("setup_mode_hotseat", "Hotseat", pygame.Rect(panel.x + 184, panel.y + 92, 104, 34), True),
                UIButton(
                    "setup_difficulty",
                    f"AI: {self.difficulty.capitalize()}" if self.play_mode == PLAY_MODE_AI else "AI only",
                    pygame.Rect(panel.x + 308, panel.y + 92, 134, 34),
                    self.play_mode == PLAY_MODE_AI,
                ),
                UIButton(
                    "setup_side",
                    (
                        "You: White"
                        if self.human_side() == WHITE
                        else "You: Black"
                        if self.play_mode == PLAY_MODE_AI
                        else "AI side"
                    ),
                    pygame.Rect(panel.x + 454, panel.y + 92, 126, 34),
                    self.play_mode == PLAY_MODE_AI,
                ),
            ]
        )

        start_rect = pygame.Rect(panel.centerx - 92, panel.bottom - 58, 184, 38)
        return choices, option_buttons, UIButton(key="start_match", label=self.setup_button_label(), rect=start_rect, enabled=True)

    def handle_setup_click(self, point: Tuple[int, int]) -> bool:
        self.setup_choices, option_buttons, start_button = self.build_setup_widgets()
        self.setup_option_buttons = option_buttons
        self.setup_start_button = start_button

        for button in self.setup_option_buttons:
            if not button.enabled or not button.rect.collidepoint(point):
                continue
            if button.key == "setup_mode_ai":
                self.play_mode = PLAY_MODE_AI
                self.enter_setup_mode()
            elif button.key == "setup_mode_hotseat":
                self.play_mode = PLAY_MODE_HOTSEAT
                self.enter_setup_mode()
            elif button.key == "setup_difficulty":
                self.cycle_difficulty()
            elif button.key == "setup_side":
                self.swap_agent_side()
            return True

        if self.setup_start_button.rect.collidepoint(point):
            self.advance_setup()
            return True

        for choice in self.setup_choices:
            if not choice.rect.collidepoint(point):
                continue
            if choice.side == WHITE:
                self.white_gap = choice.gap_col
            else:
                self.black_gap = choice.gap_col
            self.state = default_state(self.white_gap, self.black_gap, variant=self.variant)
            self.selected = None
            self.last_move = None
            self.refresh_status()
            return True
        return False

    def draw_setup_option_button(self, button: UIButton, active: bool = False) -> None:
        fill = self.settings.button_fill_active if active and button.enabled else self.settings.button_fill
        border = self.settings.move_hint if active and button.enabled else self.settings.button_border
        if not button.enabled:
            fill = self.settings.button_disabled
            border = self.colors["panel_border"]
        pygame.draw.rect(self.screen, fill, button.rect, border_radius=14)
        pygame.draw.rect(self.screen, border, button.rect, 2, border_radius=14)
        text_color = self.settings.button_text if button.enabled else self.colors["muted"]
        label = self.small_font.render(button.label, True, text_color)
        self.screen.blit(label, label.get_rect(center=button.rect.center))

    def draw_setup_choice(self, choice: SetupChoice) -> None:
        selected_gap = self.white_gap if choice.side == WHITE else self.black_gap
        selected = selected_gap == choice.gap_col
        fill = self.settings.button_fill_active if selected else self.settings.button_fill
        border = self.settings.move_hint if selected else self.settings.button_border
        pygame.draw.rect(self.screen, fill, choice.rect, border_radius=16)
        pygame.draw.rect(self.screen, border, choice.rect, 2, border_radius=16)

        label = self.small_font.render(f"Gap {choice.gap_col + 1}", True, self.colors["panel_text"])
        self.screen.blit(label, label.get_rect(center=(choice.rect.centerx, choice.rect.y + 17)))

        seam_y = choice.rect.bottom - 22
        left = choice.rect.x + 14
        step = (choice.rect.width - 28) / max(1, COLS - 1)
        pawn_color = self.settings.white_pawn if choice.side == WHITE else self.settings.black_pawn
        knight_color = self.settings.white_knight if choice.side == WHITE else self.settings.black_knight

        pygame.draw.line(
            self.screen,
            self.colors["seam_dark"],
            (left, seam_y),
            (choice.rect.right - 14, seam_y),
            3,
        )

        for col in range(COLS):
            x = left + col * step
            pygame.draw.circle(self.screen, self.colors["seam"], (int(x), seam_y), 5)
            pygame.draw.circle(self.screen, self.colors["seam_dark"], (int(x), seam_y), 5, 1)
            if col == choice.gap_col:
                continue

            if choice.side == WHITE:
                knight_points = [(x, seam_y - 30), (x - 10, seam_y - 6), (x + 10, seam_y - 6)]
                pawn_points = [(x, seam_y - 15), (x - 7, seam_y + 2), (x + 7, seam_y + 2)]
            else:
                knight_points = [(x - 10, seam_y + 6), (x + 10, seam_y + 6), (x, seam_y + 30)]
                pawn_points = [(x - 7, seam_y - 2), (x + 7, seam_y - 2), (x, seam_y + 15)]

            pygame.draw.polygon(self.screen, knight_color, knight_points)
            pygame.draw.polygon(self.screen, mix(knight_color, (40, 45, 56), 0.45), knight_points, 2)
            pygame.draw.polygon(self.screen, pawn_color, pawn_points)
            pygame.draw.polygon(self.screen, mix(pawn_color, (40, 45, 56), 0.45), pawn_points, 2)

    def draw_setup_overlay(self) -> None:
        overlay = pygame.Surface(self.window_size, pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 44))
        self.screen.blit(overlay, (0, 0))

        panel = self.setup_panel_rect()
        self.draw_panel(panel)
        self.setup_choices, self.setup_option_buttons, self.setup_start_button = self.build_setup_widgets()

        title = self.title_font.render("Choose Opening Layout", True, self.colors["panel_text"])
        subtitle = self.body_font.render(
            "Set the game first, then choose hidden opening layouts.",
            True,
            self.colors["muted"],
        )
        self.screen.blit(title, (panel.x + 26, panel.y + 20))
        self.screen.blit(subtitle, (panel.x + 26, panel.y + 62))

        settings_label = self.small_font.render(
            "Pregame settings",
            True,
            self.colors["muted"],
        )
        self.screen.blit(settings_label, (panel.x + 28, panel.y + 72))

        for button in self.setup_option_buttons:
            is_active = False
            if button.key == "setup_mode_ai":
                is_active = self.play_mode == PLAY_MODE_AI
            elif button.key == "setup_mode_hotseat":
                is_active = self.play_mode == PLAY_MODE_HOTSEAT
            elif button.key == "setup_difficulty":
                is_active = button.enabled
            elif button.key == "setup_side":
                is_active = button.enabled
            self.draw_setup_option_button(button, active=is_active)

        if self.setup_stage == "white_pick":
            stage_text = f"White chooses now. Current gap: column {self.white_gap + 1}."
        elif self.setup_stage == "pass_black":
            stage_text = "White is hidden. Hand over to Black, then click Black Turn."
        elif self.setup_stage == "black_pick":
            stage_text = f"Black chooses now. Current gap: column {self.black_gap + 1}."
        elif self.setup_stage == "player_white":
            stage_text = f"Choose your gap as White. Current gap: column {self.white_gap + 1}."
        else:
            stage_text = f"Choose your gap as Black. Current gap: column {self.black_gap + 1}."

        stage_label = self.body_font.render(stage_text, True, self.colors["panel_text"])
        self.screen.blit(stage_label, (panel.x + 26, panel.y + 152))

        help_text = self.small_font.render(
            "Each card shows which column starts empty. Only the current side's choices are shown.",
            True,
            self.colors["muted"],
        )
        self.screen.blit(help_text, (panel.x + 26, panel.bottom - 88))

        for choice in self.setup_choices:
            self.draw_setup_choice(choice)

        assert self.setup_start_button is not None
        pygame.draw.rect(self.screen, self.settings.button_fill_active, self.setup_start_button.rect, border_radius=14)
        pygame.draw.rect(self.screen, self.settings.button_border, self.setup_start_button.rect, 2, border_radius=14)
        start_label = self.button_font.render(self.setup_start_button.label, True, self.settings.button_text)
        self.screen.blit(start_label, start_label.get_rect(center=self.setup_start_button.rect.center))

    def draw_tiles(self) -> None:
        shadow = pygame.Surface((self.board_width + 36, self.board_height + 52), pygame.SRCALPHA)
        pygame.draw.rect(
            shadow,
            with_alpha(self.colors["board_shadow"], 60),
            shadow.get_rect(),
            border_radius=42,
        )
        self.screen.blit(shadow, (self.board_left - 18, self.board_top + 16))

        board_back = pygame.Rect(self.board_left - 18, self.board_top - 18, self.board_width + 36, self.board_height + 36)
        pygame.draw.rect(self.screen, (248, 253, 254), board_back, border_radius=36)
        pygame.draw.rect(self.screen, self.colors["panel_border"], board_back, 2, border_radius=36)

        inset = 8
        for row in range(ROWS - 1):
            for col in range(COLS):
                tile_rect = pygame.Rect(
                    self.board_left + col * self.tile_size + inset,
                    self.board_top + row * self.tile_size + inset,
                    self.tile_size - inset * 2,
                    self.tile_size - inset * 2,
                )
                color = self.settings.checker_red if (row + col) % 2 == 0 else self.settings.checker_yellow

                tile_shadow = pygame.Surface((tile_rect.width + 12, tile_rect.height + 14), pygame.SRCALPHA)
                pygame.draw.rect(
                    tile_shadow,
                    with_alpha(self.colors["board_shadow"], 35),
                    tile_shadow.get_rect(),
                    border_radius=24,
                )
                self.screen.blit(tile_shadow, (tile_rect.x - 6, tile_rect.y + 5))

                tile_surface = pygame.Surface(tile_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(tile_surface, with_alpha(color, 190), tile_surface.get_rect(), border_radius=22)
                pygame.draw.rect(tile_surface, with_alpha(self.colors["tile_outline"], 220), tile_surface.get_rect(), 2, border_radius=22)
                highlight_rect = tile_surface.get_rect().inflate(-14, -54)
                highlight_surface = pygame.Surface(highlight_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    highlight_surface,
                    with_alpha((255, 255, 255), 65),
                    highlight_surface.get_rect(),
                    border_radius=16,
                )
                tile_surface.blit(highlight_surface, highlight_rect.topleft)
                self.screen.blit(tile_surface, tile_rect.topleft)

                inner_frame = tile_rect.inflate(-24, -24)
                pygame.draw.rect(
                    self.screen,
                    with_alpha((255, 255, 255), 42),
                    inner_frame,
                    2,
                    border_radius=18,
                )

        for seam_index in range(ROWS):
            seam_y = self.board_top + seam_index * self.tile_size
            pygame.draw.line(
                self.screen,
                mix(self.colors["seam"], (255, 255, 255), 0.25),
                (self.board_left + 8, seam_y),
                (self.board_left + self.board_width - 8, seam_y),
                4,
            )
        for seam_index in range(1, COLS):
            seam_x = self.board_left + seam_index * self.tile_size
            pygame.draw.line(
                self.screen,
                with_alpha(self.colors["seam_dark"], 140)[:3],
                (seam_x, self.board_top + 8),
                (seam_x, self.board_top + self.board_height - 8),
                3,
            )

        self.draw_target_row_glow(WHITE)
        self.draw_target_row_glow(BLACK)

    def draw_target_row_glow(self, side: str) -> None:
        seam_row = self.state.target_row(side)
        seam_color = self.settings.white_pawn if side == WHITE else self.settings.black_pawn
        seam_y = self.position_to_pixel((seam_row, 0))[1]
        glow_surface = pygame.Surface((self.board_width + 80, 40), pygame.SRCALPHA)
        pygame.draw.ellipse(
            glow_surface,
            with_alpha(seam_color, 56),
            glow_surface.get_rect(),
        )
        self.screen.blit(glow_surface, (self.board_left - 40, seam_y - 20))
        pygame.draw.line(
            self.screen,
            mix(seam_color, (255, 255, 255), 0.2),
            (self.board_left + 6, seam_y),
            (self.board_left + self.board_width - 6, seam_y),
            5,
        )

    def draw_edge_positions(self) -> None:
        for row in range(ROWS):
            for col in range(COLS):
                x, y = self.position_to_pixel((row, col))
                pygame.draw.circle(self.screen, (238, 247, 252), (int(x), int(y)), 10)
                pygame.draw.circle(self.screen, self.colors["seam_dark"], (int(x), int(y)), 10, 2)

        for row in range(ROWS):
            _x, y = self.position_to_pixel((row, 0))
            label = self.row_font.render(str(row + 1), True, self.colors["panel_text"])
            self.screen.blit(label, (self.board_left - 38, y - label.get_height() // 2))

        if self.last_move is not None:
            for coord in self.last_move:
                if not (0 <= coord[0] < ROWS and 0 <= coord[1] < COLS):
                    continue
                x, y = self.position_to_pixel(coord)
                halo = pygame.Surface((68, 68), pygame.SRCALPHA)
                pygame.draw.circle(halo, with_alpha(self.colors["last_move"], 100), (34, 34), 26)
                self.screen.blit(halo, (x - 34, y - 34))

        if self.selected is not None:
            x, y = self.position_to_pixel(self.selected)
            glow = pygame.Surface((88, 88), pygame.SRCALPHA)
            pygame.draw.circle(glow, with_alpha(self.colors["selection"], 132), (44, 44), 30)
            self.screen.blit(glow, (x - 44, y - 44))
            for _start, destination in get_legal_moves_from(self.state, self.selected):
                dest_x, dest_y = self.position_to_pixel(destination)
                marker = pygame.Surface((56, 56), pygame.SRCALPHA)
                pygame.draw.circle(marker, with_alpha(self.colors["move_hint"], 115), (28, 28), 18)
                pygame.draw.circle(marker, with_alpha((255, 255, 255), 235), (28, 28), 8)
                self.screen.blit(marker, (dest_x - 28, dest_y - 28))
        elif self.variant == VARIANT_RESPAWN:
            for destination in self.respawn_moves_by_destination():
                dest_x, dest_y = self.position_to_pixel(destination)
                marker = pygame.Surface((56, 56), pygame.SRCALPHA)
                pygame.draw.circle(marker, with_alpha(self.colors["move_hint"], 85), (28, 28), 16, 3)
                pygame.draw.circle(marker, with_alpha((255, 255, 255), 210), (28, 28), 5)
                self.screen.blit(marker, (dest_x - 28, dest_y - 28))

    def piece_color(self, piece: Piece) -> Tuple[int, int, int]:
        if piece.side == WHITE and piece.kind == PAWN:
            return self.settings.white_pawn
        if piece.side == WHITE and piece.kind == KNIGHT:
            return self.settings.white_knight
        if piece.side == BLACK and piece.kind == PAWN:
            return self.settings.black_pawn
        return self.settings.black_knight

    def draw_triangle_piece(
        self,
        piece: Piece,
        center: Tuple[float, float],
        selected: bool = False,
        offset_y: float = 0.0,
    ) -> None:
        x, y = center[0], center[1] + offset_y
        base_color = self.piece_color(piece)
        light_color = mix(base_color, (255, 255, 255), 0.38)
        outline_color = mix(base_color, (32, 48, 54), 0.42)
        if piece.kind == PAWN:
            width = 48
            height = 34
            seam_lift = 6
        else:
            width = 62
            height = 74
            seam_lift = 14

        if piece.side == WHITE:
            points = [
                (x, y - height + seam_lift),
                (x - width / 2, y + seam_lift),
                (x + width / 2, y + seam_lift),
            ]
            shine_points = [
                (x, y - height + seam_lift + 10),
                (x - width / 4, y + seam_lift - 10),
                (x + width / 10, y + seam_lift - 4),
            ]
        else:
            points = [
                (x - width / 2, y - seam_lift),
                (x + width / 2, y - seam_lift),
                (x, y + height - seam_lift),
            ]
            shine_points = [
                (x - width / 10, y - seam_lift + 4),
                (x + width / 4, y - seam_lift + 10),
                (x, y + height - seam_lift - 10),
            ]

        shadow_points = [(px + 3, py + 7) for px, py in points]
        pygame.draw.polygon(self.screen, with_alpha(self.colors["board_shadow"], 72), shadow_points)

        if selected:
            glow_surface = pygame.Surface((110, 110), pygame.SRCALPHA)
            pygame.draw.circle(glow_surface, with_alpha(self.colors["selection"], 110), (55, 55), 34)
            self.screen.blit(glow_surface, (x - 55, y - 55))

        pygame.draw.polygon(self.screen, base_color, points)
        pygame.draw.polygon(self.screen, outline_color, points, 3)
        pygame.draw.polygon(self.screen, with_alpha(light_color, 180), shine_points)

    def draw_pieces(self, now_ms: int) -> None:
        if self.setup_mode:
            return
        hidden_origin: Optional[Coord] = self.animation.move[0] if self.animation is not None else None

        for row in range(ROWS):
            for col in range(COLS):
                coord = (row, col)
                piece = self.state.board[row][col]
                if piece is None or coord == hidden_origin:
                    continue
                self.draw_triangle_piece(piece, self.position_to_pixel(coord), selected=(coord == self.selected))

        if self.animation is not None:
            start = self.position_to_pixel(self.animation.move[0])
            end = self.position_to_pixel(self.animation.move[1])
            progress = self.animation.progress(now_ms)
            eased = 1 - (1 - progress) * (1 - progress)
            x = start[0] + (end[0] - start[0]) * eased
            y = start[1] + (end[1] - start[1]) * eased - 10 * (1 - abs(0.5 - eased) * 2)
            self.draw_triangle_piece(self.animation.piece, (x, y), selected=False)

    def draw_overlay_text(self) -> None:
        self.draw_panel(self.status_rect)
        title = self.title_font.render("Magnet Knights", True, self.colors["panel_text"])
        self.screen.blit(title, (self.status_rect.x + 22, self.status_rect.y + 8))

        mode_label = "Mode: Human vs AI" if self.play_mode == PLAY_MODE_AI else "Mode: Hotseat"
        ai_label = f"AI: {self.difficulty.capitalize()}" if self.play_mode == PLAY_MODE_AI else "2 players"
        meta = (
            f"{mode_label}   |   {ai_label}   |   Turn: {side_name(self.state.side_to_move)}   |   "
            f"White home: {self.state.white_knights_home}   |   Black home: {self.state.black_knights_home}"
        )
        meta_text = self.small_font.render(meta, True, self.colors["muted"])
        self.screen.blit(meta_text, (self.status_rect.x + 292, self.status_rect.y + 18))

        self.draw_panel(self.footer_rect)
        message = self.body_font.render(self.status_message, True, self.colors["panel_text"])
        self.screen.blit(message, (self.footer_rect.x + 24, self.footer_rect.y + 18))

        if self.setup_mode:
            controls_primary = "Setup is hidden. Only the current side chooses its opening gap at a time."
            controls_secondary = "Mode, AI difficulty, and side are set here before the match starts. Esc quits."
        else:
            controls_primary = "Mouse: click a seam piece, then click one of the glowing legal destinations."
            controls_secondary = "In-game controls are limited to restart, opening layout, and Esc to quit."

        controls_text = self.small_font.render(controls_primary, True, self.colors["muted"])
        self.screen.blit(controls_text, (self.footer_rect.x + 24, self.footer_rect.y + 46))
        controls_text_2 = self.small_font.render(controls_secondary, True, self.colors["muted"])
        self.screen.blit(controls_text_2, (self.footer_rect.x + 24, self.footer_rect.y + 64))

        if self.last_move is not None and not self.setup_mode:
            last_move_text = self.small_font.render(
                f"Last move: {move_to_str(self.last_move)}",
                True,
                self.colors["muted"],
            )
            self.screen.blit(last_move_text, (self.footer_rect.right - 212, self.footer_rect.y + 18))

        self.draw_buttons()

    def draw_frame(self, now_ms: int) -> None:
        self.draw_gradient_background()
        self.draw_tiles()
        self.draw_edge_positions()
        self.draw_pieces(now_ms)
        self.draw_confetti()
        self.draw_overlay_text()
        if self.setup_mode:
            self.draw_setup_overlay()
        else:
            self.draw_win_overlay()

    def draw_confetti(self) -> None:
        for particle in self.confetti:
            pygame.draw.rect(
                self.screen,
                particle.color,
                pygame.Rect(int(particle.x), int(particle.y), particle.size, particle.size),
                border_radius=3,
            )

    def draw_win_overlay(self) -> None:
        winner = self.current_winner()
        if winner is None:
            return

        overlay = pygame.Surface(self.window_size, pygame.SRCALPHA)
        overlay.fill((self.settings.overlay[0], self.settings.overlay[1], self.settings.overlay[2], 74))
        self.screen.blit(overlay, (0, 0))

        banner = pygame.Rect(self.board_left + 36, self.board_top + 170, self.board_width - 72, 180)
        self.draw_panel(banner)
        winner_color = self.settings.white_knight if winner == WHITE else self.settings.black_knight
        headline = self.title_font.render(f"{side_name(winner)} Wins!", True, winner_color)
        subline = self.body_font.render(self.winning_reason(winner), True, self.colors["panel_text"])
        hint = self.small_font.render("Press R to play again.", True, self.colors["muted"])
        self.screen.blit(headline, headline.get_rect(center=(banner.centerx, banner.y + 56)))
        self.screen.blit(subline, subline.get_rect(center=(banner.centerx, banner.y + 108)))
        self.screen.blit(hint, hint.get_rect(center=(banner.centerx, banner.y + 146)))

    def run(self) -> int:
        running = True
        while running:
            now_ms = pygame.time.get_ticks()
            self.update_confetti()
            self.animate_move(now_ms)
            self.maybe_start_ai(now_ms)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.reset_game()
                    elif event.key == pygame.K_o:
                        self.enter_setup_mode()
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.setup_mode:
                        self.advance_setup()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)

            self.draw_frame(now_ms)
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        return 0


def play_pygame_gui(
    play_mode: str = PLAY_MODE_AI,
    agent_side: str = BLACK,
    depth: Optional[int] = None,
    difficulty: str = "medium",
    variant: str = VARIANT_STANDARD,
) -> int:
    app = MagnetKnightsGUI(
        play_mode=play_mode,
        agent_side=agent_side,
        depth=depth,
        difficulty=difficulty,
        variant=variant,
    )
    return app.run()
