#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from magnet_knights_logic import (
    ENGINE_LEARNED,
    VARIANT_RESPAWN,
    VARIANT_STANDARD,
    agent_move,
    apply_move,
    default_state,
    evaluate_learned,
    extract_learned_features,
    get_legal_moves,
    parse_move,
)


ROOT = Path(__file__).resolve().parent
FIXTURES_PATH = ROOT / "magnet_knights_feature_fixtures.json"
NODE_PROBE = ROOT / "magnet_knights_feature_probe.mjs"


def load_fixture_states() -> list[tuple[str, object, str]]:
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    states = []
    for fixture in fixtures:
        state = default_state(variant=fixture["variant"])
        for move_text in fixture["moves"]:
            state = apply_move(state, parse_move(move_text))
        states.append((fixture["name"], state, fixture["side"]))
    return states


def compare_python_and_js() -> None:
    python_results = {}
    for name, state, side in load_fixture_states():
        python_results[name] = {
            "features": extract_learned_features(state, side),
            "learned_eval": evaluate_learned(state, side),
        }

    completed = subprocess.run(
        ["node", str(NODE_PROBE), str(FIXTURES_PATH)],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    js_results = {entry["name"]: entry for entry in json.loads(completed.stdout)}

    for name, py_result in python_results.items():
        js_result = js_results[name]
        for feature_name, py_value in py_result["features"].items():
            js_value = js_result["features"][feature_name]
            if abs(py_value - js_value) > 1e-9:
                raise AssertionError(f"{name} feature mismatch for {feature_name}: py={py_value} js={js_value}")
        if abs(py_result["learned_eval"] - js_result["learned_eval"]) > 1e-6:
            raise AssertionError(
                f"{name} learned evaluation mismatch: py={py_result['learned_eval']} js={js_result['learned_eval']}"
            )


def check_legal_move_smoke() -> None:
    for variant in (VARIANT_STANDARD, VARIANT_RESPAWN):
        state = default_state(variant=variant)
        legal = get_legal_moves(state)
        move = agent_move(state, difficulty="easy", engine=ENGINE_LEARNED)
        if move not in legal:
            raise AssertionError(f"learned engine produced illegal move in {variant}: {move}")


def main() -> int:
    compare_python_and_js()
    check_legal_move_smoke()
    print("Validation passed: feature parity, learned evaluation parity, and legal-move smoke checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
