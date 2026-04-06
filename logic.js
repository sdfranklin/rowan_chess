export const ROWS = 7;
export const COLS = 5;
export const WHITE = "W";
export const BLACK = "B";
export const PAWN = "P";
export const KNIGHT = "N";
export const HOME_ROW_FROM_SIDE = 5;

export const DIFFICULTY_PROFILES = {
  easy: { name: "easy", depth: 2, randomness: 0.35, topK: 3 },
  medium: { name: "medium", depth: 3, randomness: 0.12, topK: 2 },
  hard: { name: "hard", depth: 4, randomness: 0.0, topK: 1 },
};

export function sideName(side) {
  return side === WHITE ? "White" : "Black";
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
  };
}

export function targetRow(side) {
  return side === WHITE ? HOME_ROW_FROM_SIDE - 1 : ROWS - HOME_ROW_FROM_SIDE;
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

export function createInitialState(whiteGap = 2, blackGap = 2) {
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
  };
}

function moveKey(move) {
  return `${move.from[0]},${move.from[1]}-${move.to[0]},${move.to[1]}`;
}

export function moveToString(move) {
  return moveKey(move);
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

  const homeRow = targetRow(piece.side);
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
  return moves;
}

export function getLegalMovesFrom(state, start) {
  return getLegalMoves(state).filter((move) => move.from[0] === start[0] && move.from[1] === start[1]);
}

export function applyMove(state, move) {
  const [[fromRow, fromCol], [toRow, toCol]] = [move.from, move.to];
  const piece = state.board[fromRow][fromCol];
  if (!piece) {
    throw new Error(`No piece at ${fromRow},${fromCol}`);
  }

  const nextState = cloneState(state);
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
    if (piece.side === WHITE && fromRow < targetRow(WHITE) && knightMoveReachesHome(state, move)) {
      nextState.whiteKnightsHome += 1;
    }
    if (piece.side === BLACK && fromRow > targetRow(BLACK) && knightMoveReachesHome(state, move)) {
      nextState.blackKnightsHome += 1;
    }
  }

  nextState.sideToMove = enemyOf(state.sideToMove);
  return nextState;
}

function immediateScoringMoves(state) {
  return getLegalMoves(state).filter((move) => {
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

  const myTargetRow = targetRow(side);
  const oppTargetRow = targetRow(enemy);

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

function boardKey(state) {
  const flat = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const piece = state.board[row][col];
      flat.push(piece ? `${piece.side}${piece.kind}` : "..");
    }
  }
  return `${flat.join("")}|${state.sideToMove}|${state.whiteKnightsHome}|${state.blackKnightsHome}`;
}

function movePriority(state, move) {
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

export function agentMove(state, difficulty = "medium") {
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
    const result = minimax(child, profile.depth - 1, -Infinity, Infinity, state.sideToMove, table);
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
