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
  easy: { name: "easy", depth: 2, randomness: 0.25, topK: 2 },
  medium: { name: "medium", depth: 3, randomness: 0.05, topK: 2 },
  hard: { name: "hard", depth: 4, randomness: 0.0, topK: 1 },
};

export function sideName(side) {
  return side === WHITE ? "Bottom" : "Top";
}

export function enemyOf(side) {
  return side === WHITE ? BLACK : WHITE;
}

export function inBounds(row, col) {
  return row >= 0 && row < ROWS && col >= 0 && col < COLS;
}

export function createPiece(side, kind, scored = false) {
  return { side, kind, scored };
}

export function clonePiece(piece) {
  return piece ? { side: piece.side, kind: piece.kind, scored: piece.scored === true } : null;
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

function knightCounts(state, side) {
  let scored = 0;
  let unscored = 0;
  for (const [row, col] of locate(state, side, KNIGHT)) {
    if (state.board[row][col].scored) {
      scored += 1;
    } else {
      unscored += 1;
    }
  }
  return { scored, unscored, total: scored + unscored };
}

function rowIsHomeOrBeyond(row, side, variant) {
  const homeRow = targetRow(side, variant);
  return side === WHITE ? row >= homeRow : row <= homeRow;
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

function pieceKey(piece) {
  return `${piece.side}${piece.kind}${piece.scored ? "H" : "_"}`;
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
  if (!piece || piece.kind !== KNIGHT || piece.scored) {
    return false;
  }
  const path = reconstructKnightPath(state, move);
  if (!path) {
    return false;
  }
  return path.some(([row]) => rowIsHomeOrBeyond(row, piece.side, state.variant));
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
    nextState.board[toRow][toCol] = createPiece(piece.side, piece.kind, piece.scored === true);
  } else {
    const enemy = enemyOf(piece.side);
    const path = reconstructKnightPath(nextState, move);
    if (!path) {
      throw new Error(`Could not reconstruct knight path for ${moveKey(move)}`);
    }

    let currentRow = fromRow;
    let currentCol = fromCol;
    let movingPiece = createPiece(piece.side, piece.kind, piece.scored === true);
    let scoredThisMove = false;
    for (const [nextRow, nextCol] of path) {
      const landing = nextState.board[nextRow][nextCol];
      nextState.board[currentRow][currentCol] = null;
      if (landing && landing.side === enemy && landing.kind === PAWN) {
        nextState.board[nextRow][nextCol] = null;
      }
      if (!movingPiece.scored && rowIsHomeOrBeyond(nextRow, movingPiece.side, state.variant)) {
        movingPiece = createPiece(movingPiece.side, movingPiece.kind, true);
        scoredThisMove = true;
      }
      nextState.board[nextRow][nextCol] = clonePiece(movingPiece);
      currentRow = nextRow;
      currentCol = nextCol;
    }
    if (scoredThisMove && piece.side === WHITE) {
      nextState.whiteKnightsHome += 1;
    }
    if (scoredThisMove && piece.side === BLACK) {
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
    return piece && piece.kind === KNIGHT && !piece.scored && knightMoveReachesHome(state, move);
  });
}

function threatenedTargets(state, bySide, kind = null) {
  const probe = cloneState(state);
  probe.sideToMove = bySide;
  const threatened = new Map();
  for (const move of getLegalMoves(probe)) {
    const piece = state.board[move.to[0]][move.to[1]];
    if (!piece) {
      continue;
    }
    if (kind !== null && piece.kind !== kind) {
      continue;
    }
    threatened.set(move.to.join(","), move.to);
  }
  return [...threatened.values()];
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
  let score = 900 * (myHome - oppHome);

  const myPawns = locate(state, side, PAWN).length;
  const oppPawns = locate(state, enemy, PAWN).length;
  const myKnightData = knightCounts(state, side);
  const oppKnightData = knightCounts(state, enemy);
  score += 70 * (myPawns - oppPawns);
  score += 260 * (myKnightData.unscored - oppKnightData.unscored);
  score += 55 * (myKnightData.scored - oppKnightData.scored);

  const myMobilityState = cloneState(state);
  myMobilityState.sideToMove = side;
  const oppMobilityState = cloneState(state);
  oppMobilityState.sideToMove = enemy;
  score += 3 * (getLegalMoves(myMobilityState).length - getLegalMoves(oppMobilityState).length);

  score += 180 * immediateScoringMoves(myMobilityState).length;
  score -= 520 * immediateScoringMoves(oppMobilityState).length;

  const myKnightThreats = threatenedTargets(state, enemy, KNIGHT);
  const oppKnightThreats = threatenedTargets(state, side, KNIGHT);
  let myScoredThreats = 0;
  let myUnscoredThreats = 0;
  for (const [row, col] of myKnightThreats) {
    if (state.board[row][col].scored) {
      myScoredThreats += 1;
    } else {
      myUnscoredThreats += 1;
    }
  }
  let oppScoredThreats = 0;
  let oppUnscoredThreats = 0;
  for (const [row, col] of oppKnightThreats) {
    if (state.board[row][col].scored) {
      oppScoredThreats += 1;
    } else {
      oppUnscoredThreats += 1;
    }
  }
  score -= 320 * myUnscoredThreats;
  score -= 60 * myScoredThreats;
  score += 190 * oppUnscoredThreats;
  score += 25 * oppScoredThreats;
  score -= 24 * threatenedTargets(state, enemy, PAWN).length;
  score += 18 * threatenedTargets(state, side, PAWN).length;

  if (myKnightData.total === 1) {
    score -= 280;
  }
  if (oppKnightData.total === 1) {
    score += 170;
  }

  const myTargetRow = targetRow(side, state.variant);
  const oppTargetRow = targetRow(enemy, state.variant);

  for (const [row, col] of locate(state, side, KNIGHT)) {
    const piece = state.board[row][col];
    if (!piece.scored) {
      score += 28 * (ROWS - Math.abs(myTargetRow - row));
      score += 8 * (2 - Math.abs(2 - col));
    }
  }
  for (const [row, col] of locate(state, enemy, KNIGHT)) {
    const piece = state.board[row][col];
    if (!piece.scored) {
      score -= 28 * (ROWS - Math.abs(oppTargetRow - row));
      score -= 8 * (2 - Math.abs(2 - col));
    }
  }
  for (const [row] of locate(state, side, PAWN)) {
    score += 3 * (ROWS - Math.abs(myTargetRow - row));
  }
  for (const [row] of locate(state, enemy, PAWN)) {
    score -= 3 * (ROWS - Math.abs(oppTargetRow - row));
  }

  return score;
}

function boardKey(state) {
  const flat = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const piece = state.board[row][col];
      flat.push(piece ? pieceKey(piece) : "..");
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
  if (piece && piece.kind === KNIGHT && !piece.scored) {
    priority += 80;
  }
  if (target) {
    priority += 100;
    if (target.kind === KNIGHT) {
      priority += target.scored ? 25 : 180;
    }
  }
  return priority;
}

function minimax(state, depth, alpha, beta, maximizingFor, table = new Map()) {
  const won = winner(state);
  const moves = getLegalMoves(state);
  if (depth === 0 || won !== null || moves.length === 0) {
    return { score: evaluate(state, maximizingFor), move: null };
  }

  const cacheKey = `${boardKey(state)}|${depth}|${maximizingFor}`;
  if (table.has(cacheKey)) {
    return { score: table.get(cacheKey), move: null };
  }

  const orderedMoves = [...moves].sort((a, b) => movePriority(state, b) - movePriority(state, a));
  const maximizing = state.sideToMove === maximizingFor;
  let bestMove = null;

  if (maximizing) {
    let value = -Infinity;
    for (const move of orderedMoves) {
      const child = applyMove(state, move);
      const childScore = minimax(child, depth - 1, alpha, beta, maximizingFor, table).score;
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
    const childScore = minimax(child, depth - 1, alpha, beta, maximizingFor, table).score;
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

function rootTacticalAdjustment(state, side) {
  const enemy = enemyOf(side);
  const enemyProbe = cloneState(state);
  enemyProbe.sideToMove = enemy;
  const myProbe = cloneState(state);
  myProbe.sideToMove = side;

  const enemyScoring = immediateScoringMoves(enemyProbe).length;
  const myScoring = immediateScoringMoves(myProbe).length;
  const myKnightTargets = threatenedTargets(state, enemy, KNIGHT);
  const oppKnightTargets = threatenedTargets(state, side, KNIGHT);

  let adjustment = 0;
  adjustment += 140 * myScoring;
  adjustment -= 520 * enemyScoring;
  for (const [row, col] of myKnightTargets) {
    adjustment -= state.board[row][col].scored ? 60 : 300;
  }
  for (const [row, col] of oppKnightTargets) {
    adjustment += state.board[row][col].scored ? 20 : 180;
  }

  const myKnightData = knightCounts(state, side);
  const oppKnightData = knightCounts(state, enemy);
  if (myKnightData.total === 1 && myKnightTargets.length > 0) {
    adjustment -= 420;
  }
  if (oppKnightData.total === 1 && oppKnightTargets.length > 0) {
    adjustment += 220;
  }
  return adjustment;
}

export function agentMove(state, difficulty = "medium") {
  const profile = DIFFICULTY_PROFILES[difficulty] || DIFFICULTY_PROFILES.medium;
  const searchDepth = Math.max(1, profile.depth);

  const legal = getLegalMoves(state);
  if (legal.length === 0) {
    throw new Error("No legal move available");
  }

  const table = new Map();
  const ranked = [...legal]
    .sort((a, b) => movePriority(state, b) - movePriority(state, a))
    .map((move) => {
      const child = applyMove(state, move);
      const result = minimax(child, searchDepth - 1, -Infinity, Infinity, state.sideToMove, table);
      return { score: result.score + rootTacticalAdjustment(child, state.sideToMove), move };
    });

  ranked.sort((a, b) => b.score - a.score);
  const bestScore = ranked[0].score;
  let candidatePool = ranked
    .slice(0, profile.topK)
    .filter(({ score }) => score >= bestScore - 20)
    .map(({ move }) => move);
  if (candidatePool.length === 0) {
    candidatePool = [ranked[0].move];
  }
  if (profile.randomness > 0 && candidatePool.length > 1 && Math.random() < profile.randomness) {
    return candidatePool[Math.floor(Math.random() * candidatePool.length)];
  }
  return ranked[0].move;
}
