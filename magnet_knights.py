#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Optional

from magnet_knights_logic import (
    AI_PROFILES,
    BLACK,
    ENGINE_BRUTE,
    Move,
    VARIANT_RESPAWN,
    VARIANT_STANDARD,
    agent_move,
    apply_move,
    difficulty_names,
    engine_names,
    default_state,
    get_legal_moves,
    move_to_str,
    parse_move,
    parse_side,
)


def workspace_venv_python() -> Path:
    return Path(__file__).resolve().parent / ".venv" / "bin" / "python"


def ensure_gui_interpreter() -> None:
    try:
        import pygame  # noqa: F401
        return
    except ModuleNotFoundError as exc:
        target_python = workspace_venv_python()
        current_python = Path(sys.executable).resolve()
        if not target_python.exists():
            raise RuntimeError(
                f"pygame is not installed for the selected interpreter, and {target_python} does not exist."
            ) from exc
        if current_python != target_python.resolve():
            os.execv(str(target_python), [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]])
        raise RuntimeError(f"pygame is still missing from the workspace interpreter at {target_python}.") from exc


def play_text_game(
    agent_side: str = BLACK,
    depth: Optional[int] = None,
    difficulty: str = "medium",
    engine: str = ENGINE_BRUTE,
    variant: str = VARIANT_STANDARD,
) -> int:
    state = default_state(variant=variant)

    while state.winner() is None:
        print()
        print(state.display())
        moves = get_legal_moves(state)
        if not moves:
            print(f"No legal moves for {state.side_to_move}.")
            break

        if state.side_to_move == agent_side:
            move = agent_move(state, depth=depth, difficulty=difficulty, engine=engine)
            print(f"Agent plays: {move_to_str(move)}")
            state = apply_move(state, move)
            continue

        print("Legal moves:")
        print(", ".join(move_to_str(move) for move in moves))
        while True:
            try:
                text = input("Your move: ").strip()
            except EOFError:
                print("\nInput closed. Exiting game.")
                return 0
            except KeyboardInterrupt:
                print("\nGame interrupted.")
                return 1

            try:
                move: Move = parse_move(text)
            except Exception:
                print("Bad format. Use r1,c1-r2,c2 or respawn-r,c")
                continue

            if move not in moves:
                print("Illegal move. Try again.")
                continue
            state = apply_move(state, move)
            break

    print()
    print(state.display())
    if state.winner() is not None:
        print(f"Winner: {state.winner()}")
    else:
        print("Game over without a winner.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Play Magnet Knights.")
    parser.add_argument("--text", action="store_true", help="Run the text-mode version instead of the Pygame GUI.")
    parser.add_argument(
        "--mode",
        choices=["ai", "hotseat"],
        default="ai",
        help="Start in human-vs-AI mode or hotseat mode.",
    )
    parser.add_argument("--agent-side", default=BLACK, help="Agent side: W or B.")
    parser.add_argument("--difficulty", choices=difficulty_names(), default="medium", help="AI difficulty level.")
    parser.add_argument("--engine", choices=engine_names(), default=ENGINE_BRUTE, help="AI engine: brute or race.")
    parser.add_argument("--depth", type=int, default=None, help="Optional search-depth override for the agent.")
    parser.add_argument(
        "--variant",
        choices=[VARIANT_STANDARD, VARIANT_RESPAWN],
        default=VARIANT_STANDARD,
        help="Rules variant to launch.",
    )
    args = parser.parse_args(argv)

    try:
        agent_side = parse_side(args.agent_side)
    except ValueError as exc:
        print(exc)
        return 1

    try:
        if args.text:
            return play_text_game(
                agent_side=agent_side,
                depth=args.depth,
                difficulty=args.difficulty,
                engine=args.engine,
                variant=args.variant,
            )
        ensure_gui_interpreter()
        from magnet_knights_gui import play_pygame_gui

        return play_pygame_gui(
            play_mode=args.mode,
            agent_side=agent_side,
            depth=args.depth,
            difficulty=args.difficulty,
            variant=args.variant,
        )
    except KeyboardInterrupt:
        print("\nGame interrupted.")
        return 1
    except RuntimeError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
