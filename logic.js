import { LEARNED_MODEL } from "./magnet_knights_learned_model.js";

export const ROWS = 7;
export const COLS = 5;
export const WHITE = "W";
export const BLACK = "B";
export const PAWN = "P";
export const KNIGHT = "N";
export const VARIANT_STANDARD = "standard";
export const VARIANT_RESPAWN = "respawn";
export const STANDARD_HOME_ROW_FROM_SIDE = 5;
export const RESPAWN_HOME_ROW_FROM_SIDE = 5;
export const RESPAWN_ROW_FROM_SIDE = 2;
export const RESPAWN_ORIGIN_ROW = -1;

export const DIFFICULTY_PROFILES = {
  easy: { name: "easy", depth: 2, randomness: 0.35, topK: 3 },
  medium: { name: "medium", depth: 3, randomness: 0.12, topK: 2 },
  hard: { name: "hard", depth: 4, randomness: 0.0, topK: 1 },
};

export const AI_ENGINE_PROFILES = {
  brute: { key: "brute", title: "Brute", copy: "Baseline alpha-beta search." },
  race: { key: "race", title: "Race", copy: "Race-aware search and evaluation." },
  learned: { key: "learned", title: "Learned", copy: "Experimental learned value model over shared features." },
};

export const LEARNED_FEATURE_SCHEMA_VERSION = "learned_v1";
export const LEARNED_FEATURE_NAMES = [
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
];

export function sideName(side) {
  return side === WHITE ? "Bottom" : "Top";
}

export function enemyOf(side) {
  return side === WHITE ? BLACK : WHITE;
}

export function inBounds(row, col) {
  return row >= 0 && row < ROWS && col >= 0 && col < COLS;
}

export function createPiece(side, kind) {
  return { side, kind };
}

export function clonePiece(piece) {
  return piece ? { side: piece.side, kind: piece.kind } : null;
}

export function cloneState(state) {
  return {
    board: state.board.map((row) => row.map(clonePiece)),
    sideToMove: state.sideToMove,
    whiteKnightsHome: state.whiteKnightsHome,
    blackKnightsHome: state.blackKnightsHome,
    variant: state.variant ?? VARIANT_STANDARD,
  };
}

export function targetRow(side, variant = VARIANT_STANDARD) {
  const homeRowFromSide = variant === VARIANT_RESPAWN ? RESPAWN_HOME_ROW_FROM_SIDE : STANDARD_HOME_ROW_FROM_SIDE;
  return side === WHITE ? homeRowFromSide - 1 : ROWS - homeRowFromSide;
}

export function respawnRow(side) {
  return side === WHITE ? RESPAWN_ROW_FROM_SIDE - 1 : ROWS - RESPAWN_ROW_FROM_SIDE;
}

export function forwardDir(side) {
  return side === WHITE ? 1 : -1;
}

export function locate(state, side, kind = null) {
  const coords = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const piece = state.board[row][col];
      if (!piece) {
        continue;
      }
      if (piece.side === side && (kind === null || piece.kind === kind)) {
        coords.push([row, col]);
      }
    }
  }
  return coords;
}

export function liveKnights(state, side) {
  return locate(state, side, KNIGHT).length;
}

function normalizeEngine(engine) {
  return AI_ENGINE_PROFILES[engine] ? engine : "brute";
}

function isKnightHome(state, coord) {
  const [row, col] = coord;
  const piece = state.board[row][col];
  if (!piece || piece.kind !== KNIGHT) {
    return false;
  }
  const homeRow = targetRow(piece.side, state.variant);
  return piece.side === WHITE ? row >= homeRow : row <= homeRow;
}

function countHomeKnightsOnBoard(state, side) {
  let count = 0;
  for (const coord of locate(state, side, KNIGHT)) {
    if (isKnightHome(state, coord)) {
      count += 1;
    }
  }
  return count;
}

function countUnscoredKnights(state, side) {
  return liveKnights(state, side) - countHomeKnightsOnBoard(state, side);
}

export function createInitialState(whiteGap = 2, blackGap = 2, variant = VARIANT_STANDARD) {
  const board = Array.from({ length: ROWS }, () => Array(COLS).fill(null));
  for (let col = 0; col < COLS; col += 1) {
    if (col === whiteGap) {
      continue;
    }
    board[0][col] = createPiece(WHITE, KNIGHT);
    board[1][col] = createPiece(WHITE, PAWN);
  }
  for (let col = 0; col < COLS; col += 1) {
    if (col === blackGap) {
      continue;
    }
    board[ROWS - 1][col] = createPiece(BLACK, KNIGHT);
    board[ROWS - 2][col] = createPiece(BLACK, PAWN);
  }
  return {
    board,
    sideToMove: WHITE,
    whiteKnightsHome: 0,
    blackKnightsHome: 0,
    variant,
  };
}

function moveKey(move) {
  return `${move.from[0]},${move.from[1]}-${move.to[0]},${move.to[1]}`;
}

export function moveToString(move) {
  return moveKey(move);
}

export function isRespawnMove(move) {
  return move.from[0] === RESPAWN_ORIGIN_ROW;
}

export function winner(state) {
  if (state.whiteKnightsHome >= 2) {
    return WHITE;
  }
  if (state.blackKnightsHome >= 2) {
    return BLACK;
  }

  const whiteLive = liveKnights(state, WHITE);
  const blackLive = liveKnights(state, BLACK);

  if (whiteLive <= 1 && blackLive <= 1) {
    if (state.whiteKnightsHome >= 1 && state.blackKnightsHome === 0) {
      return WHITE;
    }
    if (state.blackKnightsHome >= 1 && state.whiteKnightsHome === 0) {
      return BLACK;
    }
  }

  if (whiteLive === 0 && blackLive > 0) {
    return BLACK;
  }
  if (blackLive === 0 && whiteLive > 0) {
    return WHITE;
  }

  if (getLegalMoves(state).length === 0) {
    return enemyOf(state.sideToMove);
  }

  return null;
}

export function winningReason(state, winnerSide) {
  if (state.whiteKnightsHome >= 2 || state.blackKnightsHome >= 2) {
    return `${sideName(winnerSide)} wins by bringing home two knights.`;
  }
  const whiteLive = liveKnights(state, WHITE);
  const blackLive = liveKnights(state, BLACK);
  if (whiteLive <= 1 && blackLive <= 1) {
    return `${sideName(winnerSide)} wins on the one-home low-knight rule.`;
  }
  if (getLegalMoves(state).length === 0) {
    return `${sideName(winnerSide)} wins because ${sideName(state.sideToMove)} has no legal moves.`;
  }
  return `${sideName(winnerSide)} wins by keeping the last remaining knight.`;
}

export function legalPawnMoves(state, start) {
  const [row, col] = start;
  const piece = state.board[row][col];
  if (!piece || piece.kind !== PAWN) {
    return [];
  }

  const enemy = enemyOf(piece.side);
  const forward = forwardDir(piece.side);
  const moves = [];

  for (const [dRow, dCol] of [[1, 0], [-1, 0], [0, -1], [0, 1]]) {
    let nextRow = row + dRow;
    let nextCol = col + dCol;

    while (inBounds(nextRow, nextCol) && state.board[nextRow][nextCol] === null) {
      moves.push({ from: [row, col], to: [nextRow, nextCol] });
      nextRow += dRow;
      nextCol += dCol;
    }

    const captureRow = row + dRow;
    const captureCol = col + dCol;
    if (!inBounds(captureRow, captureCol)) {
      continue;
    }
    const target = state.board[captureRow][captureCol];
    if (!target || target.side !== enemy) {
      continue;
    }
    if (target.kind === KNIGHT && dRow === -forward) {
      continue;
    }
    moves.push({ from: [row, col], to: [captureRow, captureCol] });
  }

  return moves;
}

export function legalKnightDestinations(state, start) {
  const [startRow, startCol] = start;
  const piece = state.board[startRow][startCol];
  if (!piece || piece.kind !== KNIGHT) {
    return [];
  }

  const side = piece.side;
  const enemy = enemyOf(side);
  const dRow = forwardDir(side);
  const results = new Set();

  function dfs(board, row, col, jumped) {
    const middleRow = row + dRow;
    const landingRow = row + 2 * dRow;
    if (!inBounds(middleRow, col) || !inBounds(landingRow, col)) {
      if (jumped) {
        results.add(`${row},${col}`);
      }
      return;
    }

    const middle = board[middleRow][col];
    const landing = board[landingRow][col];
    let extended = false;
    if (middle && middle.kind === PAWN && !(landing && landing.kind === KNIGHT) && !(landing && landing.side === side)) {
      const nextBoard = board.map((boardRow) => boardRow.map(clonePiece));
      const knight = nextBoard[row][col];
      nextBoard[row][col] = null;
      if (landing && landing.side === enemy && landing.kind === PAWN) {
        nextBoard[landingRow][col] = null;
      }
      nextBoard[landingRow][col] = knight;
      dfs(nextBoard, landingRow, col, true);
      extended = true;
    }

    if (jumped && !extended) {
      results.add(`${row},${col}`);
    }
  }

  dfs(state.board, startRow, startCol, false);
  return Array.from(results, (value) => value.split(",").map(Number)).sort((a, b) => {
    if (a[0] !== b[0]) {
      return a[0] - b[0];
    }
    return a[1] - b[1];
  });
}

export function legalKnightMoves(state, start) {
  return legalKnightDestinations(state, start).map((to) => ({ from: [...start], to }));
}

function reconstructKnightPath(state, move) {
  const [[fromRow, fromCol], [toRow, toCol]] = [move.from, move.to];
  const piece = state.board[fromRow][fromCol];
  if (!piece || piece.kind !== KNIGHT) {
    return null;
  }

  const side = piece.side;
  const enemy = enemyOf(side);
  const dRow = forwardDir(side);
  const targetKey = `${toRow},${toCol}`;

  function buildPath(board, row, col, path) {
    if (`${row},${col}` === targetKey && path.length > 0) {
      return path;
    }

    const middleRow = row + dRow;
    const landingRow = row + 2 * dRow;
    if (!inBounds(middleRow, col) || !inBounds(landingRow, col)) {
      return null;
    }

    const middle = board[middleRow][col];
    const landing = board[landingRow][col];
    if (!middle || middle.kind !== PAWN || (landing && landing.kind === KNIGHT) || (landing && landing.side === side)) {
      return null;
    }

    const nextBoard = board.map((boardRow) => boardRow.map(clonePiece));
    const knight = nextBoard[row][col];
    nextBoard[row][col] = null;
    if (landing && landing.side === enemy && landing.kind === PAWN) {
      nextBoard[landingRow][col] = null;
    }
    nextBoard[landingRow][col] = knight;

    const childPath = buildPath(nextBoard, landingRow, col, [...path, [landingRow, col]]);
    if (childPath) {
      return childPath;
    }
    if (`${landingRow},${col}` === targetKey) {
      return [...path, [landingRow, col]];
    }
    return null;
  }

  return buildPath(state.board, fromRow, fromCol, []);
}

function knightMoveReachesHome(state, move) {
  const piece = state.board[move.from[0]][move.from[1]];
  if (!piece || piece.kind !== KNIGHT) {
    return false;
  }

  const homeRow = targetRow(piece.side, state.variant);
  const path = reconstructKnightPath(state, move);
  if (!path) {
    return false;
  }

  if (piece.side === WHITE) {
    return path.some(([row]) => row >= homeRow);
  }
  return path.some(([row]) => row <= homeRow);
}

export function getLegalMoves(state) {
  const moves = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const piece = state.board[row][col];
      if (!piece || piece.side !== state.sideToMove) {
        continue;
      }
      if (piece.kind === PAWN) {
        moves.push(...legalPawnMoves(state, [row, col]));
      } else {
        moves.push(...legalKnightMoves(state, [row, col]));
      }
    }
  }
  if (state.variant === VARIANT_RESPAWN) {
    const side = state.sideToMove;
    const livePawns = locate(state, side, PAWN).length;
    if (livePawns < COLS - 1) {
      const row = respawnRow(side);
      for (let col = 0; col < COLS; col += 1) {
        if (state.board[row][col] === null) {
          moves.push({ from: [RESPAWN_ORIGIN_ROW, col], to: [row, col] });
        }
      }
    }
  }
  return moves;
}

export function getLegalMovesFrom(state, start) {
  return getLegalMoves(state).filter((move) => move.from[0] === start[0] && move.from[1] === start[1]);
}

export function applyMove(state, move) {
  const [[fromRow, fromCol], [toRow, toCol]] = [move.from, move.to];
  const nextState = cloneState(state);
  if (isRespawnMove(move)) {
    nextState.board[toRow][toCol] = createPiece(state.sideToMove, PAWN);
    nextState.sideToMove = enemyOf(state.sideToMove);
    return nextState;
  }

  const piece = state.board[fromRow][fromCol];
  if (!piece) {
    throw new Error(`No piece at ${fromRow},${fromCol}`);
  }

  if (piece.kind === PAWN) {
    nextState.board[fromRow][fromCol] = null;
    nextState.board[toRow][toCol] = createPiece(piece.side, piece.kind);
  } else {
    const enemy = enemyOf(piece.side);
    const path = reconstructKnightPath(nextState, move);
    if (!path) {
      throw new Error(`Could not reconstruct knight path for ${moveKey(move)}`);
    }

    let currentRow = fromRow;
    let currentCol = fromCol;
    for (const [nextRow, nextCol] of path) {
      const landing = nextState.board[nextRow][nextCol];
      nextState.board[currentRow][currentCol] = null;
      if (landing && landing.side === enemy && landing.kind === PAWN) {
        nextState.board[nextRow][nextCol] = null;
      }
      nextState.board[nextRow][nextCol] = createPiece(piece.side, piece.kind);
      currentRow = nextRow;
      currentCol = nextCol;
    }
  }

  if (piece.kind === KNIGHT) {
    if (piece.side === WHITE && fromRow < targetRow(WHITE, state.variant) && knightMoveReachesHome(state, move)) {
      nextState.whiteKnightsHome += 1;
    }
    if (piece.side === BLACK && fromRow > targetRow(BLACK, state.variant) && knightMoveReachesHome(state, move)) {
      nextState.blackKnightsHome += 1;
    }
  }

  nextState.sideToMove = enemyOf(state.sideToMove);
  return nextState;
}

function immediateScoringMoves(state) {
  return getLegalMoves(state).filter((move) => {
    if (isRespawnMove(move)) {
      return false;
    }
    const piece = state.board[move.from[0]][move.from[1]];
    return piece && piece.kind === KNIGHT && knightMoveReachesHome(state, move);
  });
}

function threatenedTargets(state, bySide, kind = null) {
  const probe = cloneState(state);
  probe.sideToMove = bySide;
  const threatened = [];
  for (const move of getLegalMoves(probe)) {
    const piece = state.board[move.to[0]][move.to[1]];
    if (!piece) {
      continue;
    }
    if (kind !== null && piece.kind !== kind) {
      continue;
    }
    threatened.push(move.to);
  }
  return threatened;
}

function evaluate(state, side) {
  const won = winner(state);
  if (won === side) {
    return 1e6;
  }
  if (won === enemyOf(side)) {
    return -1e6;
  }

  const enemy = enemyOf(side);
  const myHome = side === WHITE ? state.whiteKnightsHome : state.blackKnightsHome;
  const oppHome = side === WHITE ? state.blackKnightsHome : state.whiteKnightsHome;
  let score = 460 * (myHome - oppHome);

  const myPawns = locate(state, side, PAWN).length;
  const myKnights = locate(state, side, KNIGHT).length;
  const oppPawns = locate(state, enemy, PAWN).length;
  const oppKnights = locate(state, enemy, KNIGHT).length;
  score += 24 * (myPawns - oppPawns);
  score += 155 * (myKnights - oppKnights);

  const myMobilityState = cloneState(state);
  myMobilityState.sideToMove = side;
  const oppMobilityState = cloneState(state);
  oppMobilityState.sideToMove = enemy;
  score += 3 * (getLegalMoves(myMobilityState).length - getLegalMoves(oppMobilityState).length);

  score += 180 * immediateScoringMoves(myMobilityState).length;
  score -= 220 * immediateScoringMoves(oppMobilityState).length;

  score -= 85 * threatenedTargets(state, enemy, KNIGHT).length;
  score += 70 * threatenedTargets(state, side, KNIGHT).length;
  score -= 16 * threatenedTargets(state, enemy, PAWN).length;
  score += 12 * threatenedTargets(state, side, PAWN).length;

  const myTargetRow = targetRow(side, state.variant);
  const oppTargetRow = targetRow(enemy, state.variant);

  for (const [row, col] of locate(state, side, KNIGHT)) {
    score += 18 * (ROWS - Math.abs(myTargetRow - row));
    score += 5 * (2 - Math.abs(2 - col));
  }
  for (const [row, col] of locate(state, enemy, KNIGHT)) {
    score -= 18 * (ROWS - Math.abs(oppTargetRow - row));
    score -= 5 * (2 - Math.abs(2 - col));
  }
  for (const [row] of locate(state, side, PAWN)) {
    score += 3 * (ROWS - Math.abs(myTargetRow - row));
  }
  for (const [row] of locate(state, enemy, PAWN)) {
    score -= 3 * (ROWS - Math.abs(oppTargetRow - row));
  }

  return score;
}

function jumpReadyKnights(state, side) {
  const probe = cloneState(state);
  probe.sideToMove = side;
  let count = 0;
  for (const coord of locate(state, side, KNIGHT)) {
    if (isKnightHome(state, coord)) {
      continue;
    }
    if (getLegalMovesFrom(probe, coord).length > 0) {
      count += 1;
    }
  }
  return count;
}

function bridgePawns(state, side) {
  const dRow = forwardDir(side);
  let count = 0;
  for (const [row, col] of locate(state, side, KNIGHT)) {
    if (isKnightHome(state, [row, col])) {
      continue;
    }
    const middleRow = row + dRow;
    if (!inBounds(middleRow, col)) {
      continue;
    }
    const middle = state.board[middleRow][col];
    if (middle && middle.kind === PAWN) {
      count += 1;
    }
  }
  return count;
}

function turnsBonus(turns) {
  if (turns === 1) {
    return 520;
  }
  if (turns === 2) {
    return 210;
  }
  if (turns === 3) {
    return 70;
  }
  return 0;
}

function cappedTurnsToScore(state, side, maxTurns = 3, fallback = 4, branchLimit = 3) {
  const probe = cloneState(state);
  probe.sideToMove = side;
  if (immediateScoringMoves(probe).length > 0) {
    return 1;
  }

  const legal = [...getLegalMoves(probe)]
    .sort((a, b) => movePriority(probe, b) - movePriority(probe, a))
    .slice(0, branchLimit);
  for (const move of legal) {
    const child = applyMove(probe, move);
    child.sideToMove = side;
    if (immediateScoringMoves(child).length > 0) {
      return 2;
    }
    if (maxTurns <= 2) {
      continue;
    }
    const followUps = [...getLegalMoves(child)]
      .sort((a, b) => movePriority(child, b) - movePriority(child, a))
      .slice(0, branchLimit);
    for (const followUp of followUps) {
      const grandchild = applyMove(child, followUp);
      grandchild.sideToMove = side;
      if (immediateScoringMoves(grandchild).length > 0) {
        return 3;
      }
    }
  }
  return fallback;
}

function turnsToScore(state, side, maxTurns = 3, branchLimit = 6, memo = new Map()) {
  const probe = cloneState(state);
  probe.sideToMove = side;
  const cacheKey = `${boardKey(probe)}|solo|${side}|${maxTurns}`;
  if (memo.has(cacheKey)) {
    return memo.get(cacheKey);
  }
  if (immediateScoringMoves(probe).length > 0) {
    memo.set(cacheKey, 1);
    return 1;
  }
  if (maxTurns <= 1) {
    memo.set(cacheKey, Infinity);
    return Infinity;
  }

  const legal = getLegalMoves(probe);
  if (legal.length === 0) {
    memo.set(cacheKey, Infinity);
    return Infinity;
  }

  const ordered = [...legal]
    .sort((a, b) => raceMovePriority(probe, b) - raceMovePriority(probe, a))
    .slice(0, branchLimit);
  let best = Infinity;
  for (const move of ordered) {
    const child = applyMove(probe, move);
    child.sideToMove = side;
    const candidate = turnsToScore(child, side, maxTurns - 1, branchLimit, memo);
    if (Number.isFinite(candidate)) {
      best = Math.min(best, 1 + candidate);
    }
  }
  memo.set(cacheKey, best);
  return best;
}

function evaluateRace(state, side) {
  const won = winner(state);
  if (won === side) {
    return 1e6;
  }
  if (won === enemyOf(side)) {
    return -1e6;
  }

  const enemy = enemyOf(side);
  const myHome = side === WHITE ? state.whiteKnightsHome : state.blackKnightsHome;
  const oppHome = side === WHITE ? state.blackKnightsHome : state.whiteKnightsHome;
  const myHomeLive = countHomeKnightsOnBoard(state, side);
  const oppHomeLive = countHomeKnightsOnBoard(state, enemy);
  const myUnscoredKnights = countUnscoredKnights(state, side);
  const oppUnscoredKnights = countUnscoredKnights(state, enemy);
  const myPawns = locate(state, side, PAWN).length;
  const oppPawns = locate(state, enemy, PAWN).length;

  let score = 980 * (myHome - oppHome);
  score += 280 * (myUnscoredKnights - oppUnscoredKnights);
  score += 45 * (myHomeLive - oppHomeLive);
  score += 38 * (myPawns - oppPawns);

  const myProbe = cloneState(state);
  myProbe.sideToMove = side;
  const oppProbe = cloneState(state);
  oppProbe.sideToMove = enemy;

  const myImmediate = immediateScoringMoves(myProbe).length;
  const oppImmediate = immediateScoringMoves(oppProbe).length;
  score += 560 * myImmediate;
  score -= 820 * oppImmediate;

  score += 26 * (jumpReadyKnights(state, side) - jumpReadyKnights(state, enemy));
  score += 14 * (bridgePawns(state, side) - bridgePawns(state, enemy));

  const myKnightTargets = threatenedTargets(state, enemy, KNIGHT);
  const oppKnightTargets = threatenedTargets(state, side, KNIGHT);
  for (const coord of myKnightTargets) {
    score -= isKnightHome(state, coord) ? 40 : 240;
  }
  for (const coord of oppKnightTargets) {
    score += isKnightHome(state, coord) ? 12 : 150;
  }

  const myTargetRow = targetRow(side, state.variant);
  const oppTargetRow = targetRow(enemy, state.variant);
  for (const [row, col] of locate(state, side, KNIGHT)) {
    if (isKnightHome(state, [row, col])) {
      continue;
    }
    score += 28 * (ROWS - Math.abs(myTargetRow - row));
    score += 7 * (2 - Math.abs(2 - col));
  }
  for (const [row, col] of locate(state, enemy, KNIGHT)) {
    if (isKnightHome(state, [row, col])) {
      continue;
    }
    score -= 28 * (ROWS - Math.abs(oppTargetRow - row));
    score -= 7 * (2 - Math.abs(2 - col));
  }

  score += 2 * (getLegalMoves(myProbe).length - getLegalMoves(oppProbe).length);
  return score;
}

function threatenedKnightCounts(state, side) {
  const enemy = enemyOf(side);
  let threatenedHome = 0;
  let threatenedUnscored = 0;
  for (const coord of threatenedTargets(state, enemy, KNIGHT)) {
    if (isKnightHome(state, coord)) {
      threatenedHome += 1;
    } else {
      threatenedUnscored += 1;
    }
  }
  return { threatenedHome, threatenedUnscored };
}

function unscoredKnightDistanceTotal(state, side) {
  const homeRow = targetRow(side, state.variant);
  let total = 0;
  for (const [row, col] of locate(state, side, KNIGHT)) {
    if (isKnightHome(state, [row, col])) {
      continue;
    }
    if (side === WHITE) {
      total += Math.max(0, homeRow - row);
    } else {
      total += Math.max(0, row - homeRow);
    }
  }
  return total;
}

export function extractLearnedFeatures(state, side) {
  const enemy = enemyOf(side);
  const myHome = side === WHITE ? state.whiteKnightsHome : state.blackKnightsHome;
  const oppHome = side === WHITE ? state.blackKnightsHome : state.whiteKnightsHome;
  const myHomeLive = countHomeKnightsOnBoard(state, side);
  const oppHomeLive = countHomeKnightsOnBoard(state, enemy);
  const myUnscoredKnights = countUnscoredKnights(state, side);
  const oppUnscoredKnights = countUnscoredKnights(state, enemy);
  const myPawns = locate(state, side, PAWN).length;
  const oppPawns = locate(state, enemy, PAWN).length;

  const myProbe = cloneState(state);
  myProbe.sideToMove = side;
  const oppProbe = cloneState(state);
  oppProbe.sideToMove = enemy;
  const myImmediateScores = immediateScoringMoves(myProbe).length;
  const oppImmediateScores = immediateScoringMoves(oppProbe).length;
  const turnsSelf = cappedTurnsToScore(state, side);
  const turnsOpp = cappedTurnsToScore(state, enemy);
  const myThreats = threatenedKnightCounts(state, side);
  const oppThreats = threatenedKnightCounts(state, enemy);
  const myLegal = getLegalMoves(myProbe).length;
  const oppLegal = getLegalMoves(oppProbe).length;
  const myDistanceTotal = unscoredKnightDistanceTotal(state, side);
  const oppDistanceTotal = unscoredKnightDistanceTotal(state, enemy);

  return {
    bias: 1,
    home_diff: myHome - oppHome,
    home_live_diff: myHomeLive - oppHomeLive,
    unscored_knight_diff: myUnscoredKnights - oppUnscoredKnights,
    pawn_diff: myPawns - oppPawns,
    immediate_score_diff: myImmediateScores - oppImmediateScores,
    my_immediate_scores: myImmediateScores,
    opp_immediate_scores: oppImmediateScores,
    turns_to_score_self: turnsSelf,
    turns_to_score_opp: turnsOpp,
    turns_to_score_diff: turnsOpp - turnsSelf,
    threatened_unscored_knight_diff: oppThreats.threatenedUnscored - myThreats.threatenedUnscored,
    threatened_home_knight_diff: oppThreats.threatenedHome - myThreats.threatenedHome,
    jump_ready_diff: jumpReadyKnights(state, side) - jumpReadyKnights(state, enemy),
    bridge_pawn_diff: bridgePawns(state, side) - bridgePawns(state, enemy),
    legal_move_diff: myLegal - oppLegal,
    unscored_knight_distance_diff: oppDistanceTotal - myDistanceTotal,
    self_last_unscored_knight: myUnscoredKnights === 1 ? 1 : 0,
    opp_last_unscored_knight: oppUnscoredKnights === 1 ? 1 : 0,
    variant_is_respawn: state.variant === VARIANT_RESPAWN ? 1 : 0,
  };
}

function validateLearnedModel(model) {
  if (model.schema_version !== LEARNED_FEATURE_SCHEMA_VERSION) {
    throw new Error("learned model schema version does not match runtime");
  }
  if (JSON.stringify(model.feature_names) !== JSON.stringify(LEARNED_FEATURE_NAMES)) {
    throw new Error("learned model feature names do not match runtime");
  }
  if (model.weights.length !== LEARNED_FEATURE_NAMES.length || model.means.length !== LEARNED_FEATURE_NAMES.length || model.scales.length !== LEARNED_FEATURE_NAMES.length) {
    throw new Error("learned model vector lengths do not match runtime features");
  }
}

function sigmoid(value) {
  if (value >= 0) {
    const z = Math.exp(-value);
    return 1 / (1 + z);
  }
  const z = Math.exp(value);
  return z / (1 + z);
}

function learnedRawScore(featureMap) {
  validateLearnedModel(LEARNED_MODEL);
  let total = LEARNED_MODEL.bias;
  for (let index = 0; index < LEARNED_FEATURE_NAMES.length; index += 1) {
    const name = LEARNED_FEATURE_NAMES[index];
    const scale = Math.abs(LEARNED_MODEL.scales[index]) > 1e-9 ? LEARNED_MODEL.scales[index] : 1;
    const normalized = (featureMap[name] - LEARNED_MODEL.means[index]) / scale;
    total += LEARNED_MODEL.weights[index] * normalized;
  }
  return total;
}

export function evaluateLearned(state, side) {
  const won = winner(state);
  if (won === side) {
    return 1e6;
  }
  if (won === enemyOf(side)) {
    return -1e6;
  }

  const rawScore = learnedRawScore(extractLearnedFeatures(state, side));
  const probability = sigmoid(rawScore);
  return 2200 * (probability - 0.5);
}

function finiteTurnBucket(turns, fallback = 5) {
  return Number.isFinite(turns) ? turns : fallback;
}

function sideImmediateScores(state, side) {
  const probe = cloneState(state);
  probe.sideToMove = side;
  return immediateScoringMoves(probe).length;
}

function hasTacticalRaceState(state) {
  if (sideImmediateScores(state, WHITE) > 0 || sideImmediateScores(state, BLACK) > 0) {
    return true;
  }
  for (const side of [WHITE, BLACK]) {
    const enemy = enemyOf(side);
    for (const coord of threatenedTargets(state, enemy, KNIGHT)) {
      if (!isKnightHome(state, coord)) {
        return true;
      }
    }
  }
  return false;
}

function boardKey(state) {
  const flat = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const piece = state.board[row][col];
      flat.push(piece ? `${piece.side}${piece.kind}` : "..");
    }
  }
  return `${flat.join("")}|${state.sideToMove}|${state.whiteKnightsHome}|${state.blackKnightsHome}|${state.variant ?? VARIANT_STANDARD}`;
}

function movePriority(state, move) {
  if (isRespawnMove(move)) {
    return 35;
  }
  const piece = state.board[move.from[0]][move.from[1]];
  const target = state.board[move.to[0]][move.to[1]];
  let priority = 0;
  if (piece && piece.kind === KNIGHT && knightMoveReachesHome(state, move)) {
    priority += 1000;
  }
  if (piece && piece.kind === KNIGHT) {
    priority += 80;
  }
  if (target) {
    priority += 100;
    if (target.kind === KNIGHT) {
      priority += 180;
    }
  }
  return priority;
}

function raceMovePriority(state, move) {
  let priority = movePriority(state, move);
  const side = state.sideToMove;
  const enemy = enemyOf(side);
  const child = applyMove(state, move);
  if (winner(child) === side) {
    return priority + 5000;
  }

  const myProbe = cloneState(child);
  myProbe.sideToMove = side;
  const oppProbe = cloneState(child);
  oppProbe.sideToMove = enemy;
  priority += 420 * immediateScoringMoves(myProbe).length;
  priority -= 1000 * immediateScoringMoves(oppProbe).length;

  if (!isRespawnMove(move)) {
    const piece = state.board[move.from[0]][move.from[1]];
    const target = state.board[move.to[0]][move.to[1]];
    if (target && target.kind === KNIGHT) {
      priority += isKnightHome(state, move.to) ? 30 : 170;
    }
    if (piece && piece.kind === KNIGHT) {
      const threatened = threatenedTargets(child, enemy, KNIGHT).some(
        ([row, col]) => row === move.to[0] && col === move.to[1],
      );
      if (threatened) {
        priority -= isKnightHome(child, move.to) ? 25 : 220;
      }
    }
  }
  return priority;
}

function minimaxWithPolicy(state, depth, alpha, beta, maximizingFor, evaluateFn, priorityFn, cachePrefix, tacticalExtensions = 0, table = new Map()) {
  const won = winner(state);
  const moves = getLegalMoves(state);
  if (depth === 0 && won === null && moves.length > 0 && tacticalExtensions > 0 && hasTacticalRaceState(state)) {
    depth = 1;
    tacticalExtensions -= 1;
  }
  if (depth === 0 || won !== null || moves.length === 0) {
    return { score: evaluateFn(state, maximizingFor), move: null };
  }

  const cacheKey = `${cachePrefix}|${boardKey(state)}|${depth}|${maximizingFor}`;
  if (table.has(cacheKey)) {
    return { score: table.get(cacheKey), move: null };
  }

  const orderedMoves = [...moves].sort((a, b) => priorityFn(state, b) - priorityFn(state, a));
  const maximizing = state.sideToMove === maximizingFor;
  let bestMove = null;

  if (maximizing) {
    let value = -Infinity;
    for (const move of orderedMoves) {
      const child = applyMove(state, move);
      const childScore = minimaxWithPolicy(
        child,
        depth - 1,
        alpha,
        beta,
        maximizingFor,
        evaluateFn,
        priorityFn,
        cachePrefix,
        tacticalExtensions,
        table,
      ).score;
      if (childScore > value) {
        value = childScore;
        bestMove = move;
      }
      alpha = Math.max(alpha, value);
      if (beta <= alpha) {
        break;
      }
    }
    table.set(cacheKey, value);
    return { score: value, move: bestMove };
  }

  let value = Infinity;
  for (const move of orderedMoves) {
    const child = applyMove(state, move);
    const childScore = minimaxWithPolicy(
      child,
      depth - 1,
      alpha,
      beta,
      maximizingFor,
      evaluateFn,
      priorityFn,
      cachePrefix,
      tacticalExtensions,
      table,
    ).score;
    if (childScore < value) {
      value = childScore;
      bestMove = move;
    }
    beta = Math.min(beta, value);
    if (beta <= alpha) {
      break;
    }
  }
  table.set(cacheKey, value);
  return { score: value, move: bestMove };
}

function minimax(state, depth, alpha, beta, maximizingFor, tacticalExtensions = 0, table = new Map()) {
  return minimaxWithPolicy(state, depth, alpha, beta, maximizingFor, evaluate, movePriority, "brute", tacticalExtensions, table);
}

function minimaxRace(state, depth, alpha, beta, maximizingFor, table = new Map()) {
  return minimaxWithPolicy(state, depth, alpha, beta, maximizingFor, evaluateRace, raceMovePriority, "race", 0, table);
}

function minimaxLearned(state, depth, alpha, beta, maximizingFor, table = new Map()) {
  return minimaxWithPolicy(state, depth, alpha, beta, maximizingFor, evaluateLearned, movePriority, "learned", 0, table);
}

function raceRootAdjustment(state, side) {
  const enemy = enemyOf(side);
  const myProbe = cloneState(state);
  myProbe.sideToMove = side;
  const oppProbe = cloneState(state);
  oppProbe.sideToMove = enemy;
  let score = 260 * immediateScoringMoves(myProbe).length;
  score -= 980 * immediateScoringMoves(oppProbe).length;
  for (const coord of threatenedTargets(state, enemy, KNIGHT)) {
    score -= isKnightHome(state, coord) ? 40 : 260;
  }
  for (const coord of threatenedTargets(state, side, KNIGHT)) {
    score += isKnightHome(state, coord) ? 10 : 140;
  }
  return score;
}

function raceMoveAdjustment(state, child, move, side) {
  const enemy = enemyOf(side);
  const preMyProbe = cloneState(state);
  preMyProbe.sideToMove = side;
  const preOppProbe = cloneState(state);
  preOppProbe.sideToMove = enemy;
  const postMyProbe = cloneState(child);
  postMyProbe.sideToMove = side;
  const postOppProbe = cloneState(child);
  postOppProbe.sideToMove = enemy;

  const preMyImmediate = immediateScoringMoves(preMyProbe).length;
  const preOppImmediate = immediateScoringMoves(preOppProbe).length;
  const postMyImmediate = immediateScoringMoves(postMyProbe).length;
  const postOppImmediate = immediateScoringMoves(postOppProbe).length;

  let score = 0;
  if (preOppImmediate > 0 && postOppImmediate === 0) {
    score += 1250;
  }
  score -= 900 * Math.max(0, postOppImmediate - preOppImmediate);
  score -= 520 * postOppImmediate;

  if (postMyImmediate > preMyImmediate) {
    score += 280 * (postMyImmediate - preMyImmediate);
  }
  score += 140 * postMyImmediate;

  const preMyTurns = finiteTurnBucket(turnsToScore(state, side, 4), 6);
  const preOppTurns = finiteTurnBucket(turnsToScore(state, enemy, 4), 6);
  const postMyTurns = finiteTurnBucket(turnsToScore(child, side, 4), 6);
  const postOppTurns = finiteTurnBucket(turnsToScore(child, enemy, 4), 6);
  score += 180 * (preMyTurns - postMyTurns);
  score += 220 * (postOppTurns - preOppTurns);

  if (!isRespawnMove(move)) {
    const target = state.board[move.to[0]][move.to[1]];
    if (target && target.kind === KNIGHT && isKnightHome(state, move.to)) {
      if (!(preOppImmediate > 0 && postOppImmediate === 0)) {
        score -= 220;
      }
    }
  }

  return score;
}

function bruteMoveAdjustment(state, child, move, side) {
  const enemy = enemyOf(side);
  const preMyImmediate = sideImmediateScores(state, side);
  const preOppImmediate = sideImmediateScores(state, enemy);
  const postMyImmediate = sideImmediateScores(child, side);
  const postOppImmediate = sideImmediateScores(child, enemy);

  let score = 0;
  if (preOppImmediate > 0 && postOppImmediate === 0) {
    score += 900;
  }
  if (postOppImmediate > preOppImmediate) {
    score -= 1250 * (postOppImmediate - preOppImmediate);
  }
  score -= 420 * postOppImmediate;
  score += 180 * postMyImmediate;

  if (!isRespawnMove(move)) {
    const destination = move.to;
    const piece = state.board[move.from[0]][move.from[1]];
    const target = state.board[destination[0]][destination[1]];
    if (piece && piece.kind === KNIGHT) {
      const threatened = threatenedTargets(child, enemy, KNIGHT).some(([row, col]) => row === destination[0] && col === destination[1]);
      if (threatened) {
        score -= isKnightHome(child, destination) ? 40 : 260;
      }
    }
    if (target && target.kind === KNIGHT && isKnightHome(state, destination)) {
      if (postMyImmediate === 0 && postOppImmediate > 0) {
        score -= 180;
      }
    }
  }

  return score;
}

function bruteAgentMove(state, difficulty) {
  const profile = DIFFICULTY_PROFILES[difficulty] || DIFFICULTY_PROFILES.medium;
  const legal = getLegalMoves(state);
  if (legal.length === 0) {
    throw new Error("No legal move available");
  }

  const table = new Map();
  const tacticalExtensions = profile.depth >= 4 ? 1 : 0;
  const ranked = [...legal].sort((a, b) => movePriority(state, b) - movePriority(state, a)).map((move) => {
    const child = applyMove(state, move);
    const result = minimax(child, profile.depth - 1, -Infinity, Infinity, state.sideToMove, tacticalExtensions, table);
    return { score: result.score + bruteMoveAdjustment(state, child, move, state.sideToMove), move };
  });

  ranked.sort((a, b) => b.score - a.score);
  const bestScore = ranked[0].score;
  let candidatePool = ranked
    .slice(0, profile.topK)
    .filter(({ score }) => score >= bestScore - 45)
    .map(({ move }) => move);
  if (candidatePool.length === 0) {
    candidatePool = [ranked[0].move];
  }
  if (profile.randomness > 0 && candidatePool.length > 1 && Math.random() < profile.randomness) {
    return candidatePool[Math.floor(Math.random() * candidatePool.length)];
  }
  return ranked[0].move;
}

function raceAgentMove(state, difficulty) {
  const profile = DIFFICULTY_PROFILES[difficulty] || DIFFICULTY_PROFILES.medium;
  const searchDepth = profile.depth;
  const legal = getLegalMoves(state);
  if (legal.length === 0) {
    throw new Error("No legal move available");
  }

  const winningMoves = legal.filter((move) => winner(applyMove(state, move)) === state.sideToMove);
  if (winningMoves.length > 0) {
    return winningMoves.sort((a, b) => raceMovePriority(state, b) - raceMovePriority(state, a))[0];
  }

  const table = new Map();
  const ranked = [...legal]
    .sort((a, b) => raceMovePriority(state, b) - raceMovePriority(state, a))
    .map((move) => {
      const child = applyMove(state, move);
      const result = minimaxRace(child, searchDepth - 1, -Infinity, Infinity, state.sideToMove, table);
      return { score: result.score + raceRootAdjustment(child, state.sideToMove) + raceMoveAdjustment(state, child, move, state.sideToMove), move };
    });

  ranked.sort((a, b) => b.score - a.score);
  const bestScore = ranked[0].score;
  let candidatePool = ranked
    .slice(0, profile.topK)
    .filter(({ score }) => score >= bestScore - 35)
    .map(({ move }) => move);
  if (candidatePool.length === 0) {
    candidatePool = [ranked[0].move];
  }
  if (profile.randomness > 0 && candidatePool.length > 1 && Math.random() < profile.randomness) {
    return candidatePool[Math.floor(Math.random() * candidatePool.length)];
  }
  return ranked[0].move;
}

function learnedAgentMove(state, difficulty) {
  const profile = DIFFICULTY_PROFILES[difficulty] || DIFFICULTY_PROFILES.medium;
  const instant = immediateScoringMoves(state);
  if (instant.length > 0) {
    return instant[Math.floor(Math.random() * instant.length)];
  }

  const legal = getLegalMoves(state);
  if (legal.length === 0) {
    throw new Error("No legal move available");
  }

  const table = new Map();
  const ranked = legal.map((move) => {
    const child = applyMove(state, move);
    const result = minimaxLearned(child, profile.depth - 1, -Infinity, Infinity, state.sideToMove, table);
    return { score: result.score, move };
  });

  ranked.sort((a, b) => b.score - a.score);
  const bestScore = ranked[0].score;
  let candidatePool = ranked
    .slice(0, profile.topK)
    .filter(({ score }) => score >= bestScore - 45)
    .map(({ move }) => move);
  if (candidatePool.length === 0) {
    candidatePool = [ranked[0].move];
  }
  if (profile.randomness > 0 && candidatePool.length > 1 && Math.random() < profile.randomness) {
    return candidatePool[Math.floor(Math.random() * candidatePool.length)];
  }
  return ranked[0].move;
}

export function agentMove(state, difficulty = "medium", engine = "brute") {
  const normalizedEngine = normalizeEngine(engine);
  if (normalizedEngine === "race") {
    return raceAgentMove(state, difficulty);
  }
  if (normalizedEngine === "learned") {
    return learnedAgentMove(state, difficulty);
  }
  return bruteAgentMove(state, difficulty);
}
