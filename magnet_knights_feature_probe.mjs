import fs from "node:fs";

import { applyMove, createInitialState, evaluateLearned, extractLearnedFeatures } from "./logic.js";

function parseMove(text) {
  if (text.startsWith("respawn-") || text.startsWith("spawn-")) {
    const [, right] = text.split("-", 2);
    const [toRow, toCol] = right.split(",").map(Number);
    return { from: [-1, toCol], to: [toRow, toCol] };
  }
  const [left, right] = text.split("-");
  const [fromRow, fromCol] = left.split(",").map(Number);
  const [toRow, toCol] = right.split(",").map(Number);
  return { from: [fromRow, fromCol], to: [toRow, toCol] };
}

const fixturePath = process.argv[2] || "magnet_knights_feature_fixtures.json";
const fixtures = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const results = fixtures.map((fixture) => {
  let state = createInitialState(2, 2, fixture.variant);
  for (const moveText of fixture.moves) {
    state = applyMove(state, parseMove(moveText));
  }
  return {
    name: fixture.name,
    features: extractLearnedFeatures(state, fixture.side),
    learned_eval: evaluateLearned(state, fixture.side),
  };
});
process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
