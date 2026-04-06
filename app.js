import {
  BLACK,
  COLS,
  DIFFICULTY_PROFILES,
  KNIGHT,
  PAWN,
  ROWS,
  WHITE,
  agentMove,
  applyMove,
  createInitialState,
  getLegalMoves,
  getLegalMovesFrom,
  liveKnights,
  moveToString,
  sideName,
  targetRow,
  winner,
  winningReason,
} from "./logic.js";

const PLAY_MODE_AI = "ai";
const PLAY_MODE_HOTSEAT = "hotseat";
const LOGICAL_CANVAS_WIDTH = 860;
const LOGICAL_CANVAS_HEIGHT = 900;

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");

const metaText = document.getElementById("meta-text");
const statusText = document.getElementById("status-text");
const helpText = document.getElementById("help-text");
const setupOverlay = document.getElementById("setup-overlay");
const setupTitle = document.getElementById("setup-title");
const setupCopy = document.getElementById("setup-copy");
const setupChoices = document.getElementById("setup-choices");
const setupButton = document.getElementById("setup-button");
const winOverlay = document.getElementById("win-overlay");
const winTitle = document.getElementById("win-title");
const winCopy = document.getElementById("win-copy");
const rematchOverlayButton = document.getElementById("rematch-overlay-button");

const restartButton = document.getElementById("restart-button");
const openingButton = document.getElementById("opening-button");
const modeButton = document.getElementById("mode-button");
const difficultyButton = document.getElementById("difficulty-button");
const swapButton = document.getElementById("swap-button");

const settings = {
  tileSize: 110,
  boardLeft: 155,
  boardTop: 116,
  animationMs: 200,
  checkerRed: "#ef8e84",
  checkerYellow: "#f5d773",
  seam: "#fff6ea",
  seamDark: "#d5b08a",
  panelText: "#58301d",
  muted: "#8c624a",
  whitePawn: "#e34436",
  blackPawn: "#f8d237",
  whiteKnight: "#4381ff",
  blackKnight: "#9558dd",
  selection: "#faf69e",
  moveHint: "#55e8c6",
  lastMove: "rgba(255,255,255,0.78)",
  boardShadow: "rgba(164,121,74,0.2)",
  backgroundTop: "#fff7e8",
  backgroundBottom: "#ffecce",
  overlay: "rgba(80, 35, 18, 0.74)",
};

const app = {
  playMode: PLAY_MODE_AI,
  agentSide: BLACK,
  difficulty: "medium",
  whiteGap: 2,
  blackGap: 2,
  setupMode: true,
  setupStage: "playerWhite",
  selected: null,
  lastMove: null,
  state: null,
  animation: null,
  aiDueAt: 0,
  confetti: [],
  celebratedWinner: null,
};

function humanSide() {
  if (app.playMode === PLAY_MODE_HOTSEAT) {
    return null;
  }
  return app.agentSide === BLACK ? WHITE : BLACK;
}

function resizeCanvas() {
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  canvas.width = Math.round(LOGICAL_CANVAS_WIDTH * dpr);
  canvas.height = Math.round(LOGICAL_CANVAS_HEIGHT * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = true;
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value));
}

function mixHex(a, b, amount) {
  const parse = (hex) => [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  return `rgb(${Math.round(ar + (br - ar) * amount)}, ${Math.round(ag + (bg - ag) * amount)}, ${Math.round(ab + (bb - ab) * amount)})`;
}

function colorForPiece(piece) {
  if (piece.side === WHITE && piece.kind === PAWN) {
    return settings.whitePawn;
  }
  if (piece.side === WHITE && piece.kind === KNIGHT) {
    return settings.whiteKnight;
  }
  if (piece.side === BLACK && piece.kind === PAWN) {
    return settings.blackPawn;
  }
  return settings.blackKnight;
}

function currentWinner() {
  return winner(app.state);
}

function resetGame({ keepMode = true } = {}) {
  if (!keepMode) {
    app.playMode = PLAY_MODE_AI;
    app.agentSide = BLACK;
  }
  app.setupMode = false;
  app.setupStage = "idle";
  app.state = createInitialState(app.whiteGap, app.blackGap);
  app.selected = null;
  app.lastMove = null;
  app.animation = null;
  app.aiDueAt = 0;
  app.confetti = [];
  app.celebratedWinner = null;
  refreshUi();
  scheduleAi();
}

function enterSetupMode() {
  app.setupMode = true;
  if (app.playMode === PLAY_MODE_AI) {
    if (humanSide() === WHITE) {
      app.blackGap = Math.floor(Math.random() * COLS);
      app.setupStage = "playerWhite";
    } else {
      app.whiteGap = Math.floor(Math.random() * COLS);
      app.setupStage = "playerBlack";
    }
  } else {
    app.setupStage = "whitePick";
  }
  app.state = createInitialState(app.whiteGap, app.blackGap);
  app.selected = null;
  app.lastMove = null;
  app.animation = null;
  app.aiDueAt = 0;
  app.confetti = [];
  app.celebratedWinner = null;
  refreshUi();
}

function startMatch() {
  resetGame();
}

function advanceSetup() {
  if (app.setupStage === "whitePick") {
    app.setupStage = "passBlack";
    refreshUi();
    return;
  }
  if (app.setupStage === "passBlack") {
    app.setupStage = "blackPick";
    refreshUi();
    return;
  }
  startMatch();
}

function setupVisibleSide() {
  if (app.setupStage === "whitePick" || app.setupStage === "playerWhite") {
    return WHITE;
  }
  if (app.setupStage === "blackPick" || app.setupStage === "playerBlack") {
    return BLACK;
  }
  return null;
}

function positionToPixel([row, col]) {
  return {
    x: settings.boardLeft + col * settings.tileSize + settings.tileSize / 2,
    y: settings.boardTop + ((ROWS - 1) - row) * settings.tileSize,
  };
}

function pointToCoord(x, y) {
  let bestCoord = null;
  let bestDistance = settings.tileSize * 0.34;
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const point = positionToPixel([row, col]);
      const distance = Math.hypot(x - point.x, y - point.y);
      if (distance <= bestDistance) {
        bestDistance = distance;
        bestCoord = [row, col];
      }
    }
  }
  return bestCoord;
}

function moveEquals(a, b) {
  return a.from[0] === b.from[0] && a.from[1] === b.from[1] && a.to[0] === b.to[0] && a.to[1] === b.to[1];
}

function isHumanTurn() {
  if (app.setupMode) {
    return false;
  }
  if (app.playMode === PLAY_MODE_HOTSEAT) {
    return true;
  }
  return app.state.sideToMove !== app.agentSide;
}

function scheduleAi() {
  if (app.setupMode || app.playMode !== PLAY_MODE_AI || currentWinner() !== null) {
    app.aiDueAt = 0;
    return;
  }
  if (getLegalMoves(app.state).length === 0 || app.state.sideToMove !== app.agentSide) {
    app.aiDueAt = 0;
    return;
  }
  app.aiDueAt = performance.now() + 280;
}

function startMove(move) {
  const piece = app.state.board[move.from[0]][move.from[1]];
  const nextState = applyMove(app.state, move);
  app.selected = null;
  app.aiDueAt = 0;
  app.animation = {
    move,
    piece: { ...piece },
    startAt: performance.now(),
    duration: settings.animationMs,
    nextState,
  };
}

function finishAnimation() {
  if (!app.animation) {
    return;
  }
  app.state = app.animation.nextState;
  app.lastMove = app.animation.move;
  app.animation = null;
  refreshUi();
  scheduleAi();
}

function maybeStartAi(now) {
  if (app.setupMode || app.animation || app.playMode !== PLAY_MODE_AI || currentWinner() !== null) {
    return;
  }
  if (app.aiDueAt && now >= app.aiDueAt && app.state.sideToMove === app.agentSide) {
    const move = agentMove(app.state, app.difficulty);
    startMove(move);
    refreshUi();
  }
}

function triggerCelebration(winnerSide) {
  if (app.celebratedWinner === winnerSide) {
    return;
  }
  app.celebratedWinner = winnerSide;
  app.confetti = [];
  const palette = [
    settings.whitePawn,
    settings.blackPawn,
    settings.whiteKnight,
    settings.blackKnight,
    settings.selection,
    settings.moveHint,
  ];
  for (let i = 0; i < 120; i += 1) {
    app.confetti.push({
      x: settings.boardLeft - 20 + Math.random() * (settings.tileSize * COLS + 40),
      y: -120 + Math.random() * 100,
      vx: -2.6 + Math.random() * 5.2,
      vy: 1 + Math.random() * 3.8,
      size: 6 + Math.floor(Math.random() * 7),
      color: palette[Math.floor(Math.random() * palette.length)],
      ttl: 900 + Math.random() * 900,
    });
  }
}

function updateConfetti(dt) {
  app.confetti = app.confetti.filter((particle) => {
    particle.x += particle.vx;
    particle.y += particle.vy;
    particle.vy += 0.15;
    particle.ttl -= dt;
    return particle.ttl > 0 && particle.y < LOGICAL_CANVAS_HEIGHT + 30;
  });
}

function refreshUi() {
  const won = currentWinner();
  if (won !== null) {
    triggerCelebration(won);
  }

  const modeLabel = app.playMode === PLAY_MODE_AI ? "Human vs AI" : "Hotseat";
  const depthLabel = DIFFICULTY_PROFILES[app.difficulty].depth;
  metaText.textContent = `Mode: ${modeLabel} | Difficulty: ${app.difficulty[0].toUpperCase()}${app.difficulty.slice(1)} (depth ${depthLabel}) | Turn: ${sideName(app.state.sideToMove)} | White home: ${app.state.whiteKnightsHome} | Black home: ${app.state.blackKnightsHome}`;

  modeButton.textContent = app.playMode === PLAY_MODE_AI ? "Mode: AI" : "Mode: 2P";
  difficultyButton.textContent = `AI: ${app.difficulty[0].toUpperCase()}${app.difficulty.slice(1)}`;
  difficultyButton.disabled = app.playMode !== PLAY_MODE_AI;
  swapButton.textContent = app.playMode === PLAY_MODE_AI ? `Computer: ${sideName(app.agentSide)}` : "Swap Side";
  swapButton.disabled = app.playMode !== PLAY_MODE_AI;
  restartButton.textContent = won !== null ? "Rematch" : "Restart";

  if (app.setupMode) {
    statusText.textContent = setupStatusText();
    helpText.textContent = "Setup is hidden. Only the current side chooses its opening gap at a time.";
  } else if (won !== null) {
    statusText.textContent = winningReason(app.state, won);
    helpText.textContent = "Use Restart to play again, or Opening Layout to choose a fresh hidden setup.";
  } else if (app.animation) {
    statusText.textContent = `${sideName(app.animation.piece.side)} piece is gliding along the seam.`;
    helpText.textContent = "Click a seam piece, then a glowing destination. The highlighted seam marks the finish line.";
  } else if (app.playMode === PLAY_MODE_AI && app.state.sideToMove === app.agentSide) {
    statusText.textContent = `${sideName(app.agentSide)} agent is choosing a move.`;
    helpText.textContent = "Click a seam piece, then a glowing destination. Use Opening Layout to reopen hidden setup.";
  } else if (app.selected) {
    const piece = app.state.board[app.selected[0]][app.selected[1]];
    const name = piece.kind === KNIGHT ? "knight" : "pawn";
    statusText.textContent = `Selected ${sideName(piece.side).toLowerCase()} ${name}. Pick a glowing seam position.`;
    helpText.textContent = "Click a seam piece, then a glowing destination. The highlighted seam marks the finish line.";
  } else if (app.playMode === PLAY_MODE_HOTSEAT) {
    statusText.textContent = `${sideName(app.state.sideToMove)} to move.`;
    helpText.textContent = "Click a seam piece, then a glowing destination. The highlighted seam marks the finish line.";
  } else {
    statusText.textContent = `You are ${sideName(humanSide())}. Select a piece on the seam.`;
    helpText.textContent = "Click a seam piece, then a glowing destination. The highlighted seam marks the finish line.";
  }

  if (won !== null && !app.setupMode) {
    winOverlay.classList.remove("hidden");
    winTitle.textContent = `${sideName(won)} Wins!`;
    winCopy.textContent = winningReason(app.state, won);
  } else {
    winOverlay.classList.add("hidden");
  }

  renderSetupOverlay();
}

function setupStatusText() {
  if (app.setupStage === "whitePick") {
    return "White: choose your opening gap without showing Black.";
  }
  if (app.setupStage === "passBlack") {
    return "White is locked in. Pass the device to Black.";
  }
  if (app.setupStage === "blackPick") {
    return "Black: choose your opening gap without seeing White.";
  }
  return "Choose your opening gap. The computer's opening stays hidden until the match starts.";
}

function renderSetupOverlay() {
  if (!app.setupMode) {
    setupOverlay.classList.add("hidden");
    return;
  }
  setupOverlay.classList.remove("hidden");
  setupChoices.replaceChildren();

  setupTitle.textContent = "Choose Opening Layout";
  if (app.setupStage === "whitePick") {
    setupCopy.textContent = `White chooses now. Current gap: column ${app.whiteGap + 1}.`;
  } else if (app.setupStage === "passBlack") {
    setupCopy.textContent = "White is hidden. Hand over to Black, then click Black Turn.";
  } else if (app.setupStage === "blackPick") {
    setupCopy.textContent = `Black chooses now. Current gap: column ${app.blackGap + 1}.`;
  } else if (app.setupStage === "playerWhite") {
    setupCopy.textContent = `Choose your gap as White. The computer's gap is hidden. Current gap: column ${app.whiteGap + 1}.`;
  } else {
    setupCopy.textContent = `Choose your gap as Black. The computer's gap is hidden. Current gap: column ${app.blackGap + 1}.`;
  }

  const visibleSide = setupVisibleSide();
  if (visibleSide) {
    for (let col = 0; col < COLS; col += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "setup-choice";
      const activeGap = visibleSide === WHITE ? app.whiteGap : app.blackGap;
      if (col === activeGap) {
        button.classList.add("active");
      }
      button.addEventListener("click", () => {
        if (visibleSide === WHITE) {
          app.whiteGap = col;
        } else {
          app.blackGap = col;
        }
        app.state = createInitialState(app.whiteGap, app.blackGap);
        app.selected = null;
        app.lastMove = null;
        refreshUi();
      });

      const label = document.createElement("span");
      label.className = "choice-label";
      label.textContent = `Gap ${col + 1}`;
      button.append(label, buildChoicePreview(visibleSide, col));
      setupChoices.append(button);
    }
  }

  setupButton.textContent = app.setupStage === "whitePick" ? "Lock White Choice" : app.setupStage === "passBlack" ? "Black Turn" : "Start Match";
}

function buildChoicePreview(side, gapCol) {
  const preview = document.createElement("div");
  preview.className = "choice-preview";
  const seam = document.createElement("div");
  seam.className = "choice-seam";
  preview.append(seam);

  for (let col = 0; col < COLS; col += 1) {
    const slot = document.createElement("span");
    slot.className = "choice-slot";
    slot.style.left = `${12 + (col * (100 - 24)) / (COLS - 1)}%`;
    preview.append(slot);
    if (col === gapCol) {
      continue;
    }
    const knight = document.createElement("span");
    knight.className = `choice-piece knight ${side === WHITE ? "white" : "black"}`;
    knight.style.left = `${12 + (col * (100 - 24)) / (COLS - 1)}%`;
    const pawn = document.createElement("span");
    pawn.className = `choice-piece pawn ${side === WHITE ? "white" : "black"}`;
    pawn.style.left = `${12 + (col * (100 - 24)) / (COLS - 1)}%`;
    preview.append(knight, pawn);
  }

  return preview;
}

function roundedRectPath(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function drawRoundedRect(x, y, width, height, radius, fill, stroke = null, lineWidth = 1) {
  roundedRectPath(x, y, width, height, radius);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
}

function drawBoardBackground() {
  const gradient = ctx.createLinearGradient(0, 0, 0, LOGICAL_CANVAS_HEIGHT);
  gradient.addColorStop(0, settings.backgroundTop);
  gradient.addColorStop(1, settings.backgroundBottom);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, LOGICAL_CANVAS_WIDTH, LOGICAL_CANVAS_HEIGHT);

  ctx.save();
  ctx.shadowColor = settings.boardShadow;
  ctx.shadowBlur = 26;
  ctx.shadowOffsetY = 12;
  drawRoundedRect(
    settings.boardLeft - 18,
    settings.boardTop - 18,
    settings.tileSize * COLS + 36,
    settings.tileSize * (ROWS - 1) + 36,
    36,
    "rgba(249, 252, 251, 0.98)",
  );
  ctx.restore();
  drawRoundedRect(
    settings.boardLeft - 18,
    settings.boardTop - 18,
    settings.tileSize * COLS + 36,
    settings.tileSize * (ROWS - 1) + 36,
    36,
    "rgba(249, 252, 251, 0.98)",
    "rgba(229, 200, 166, 0.9)",
    1.5,
  );

  for (let row = 0; row < ROWS - 1; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const x = settings.boardLeft + col * settings.tileSize + 8;
      const y = settings.boardTop + row * settings.tileSize + 8;
      const size = settings.tileSize - 16;
      const color = (row + col) % 2 === 0 ? settings.checkerRed : settings.checkerYellow;
      const tileGradient = ctx.createLinearGradient(x, y, x + size, y + size);
      tileGradient.addColorStop(0, mixHex(color, "#ffffff", 0.24));
      tileGradient.addColorStop(1, mixHex(color, "#f6efe7", 0.12));

      ctx.save();
      ctx.shadowColor = "rgba(164,121,74,0.12)";
      ctx.shadowBlur = 12;
      ctx.shadowOffsetY = 5;
      roundedRectPath(x, y, size, size, 22);
      ctx.fillStyle = tileGradient;
      ctx.fill();
      ctx.restore();

      drawRoundedRect(x, y, size, size, 22, "rgba(255,255,255,0.06)", "rgba(255,255,255,0.7)", 1.5);
      drawRoundedRect(x + 12, y + 10, size - 24, size - 44, 16, "rgba(255,255,255,0.22)");
      drawRoundedRect(x + 12, y + 12, size - 24, size - 24, 18, null, "rgba(255,255,255,0.18)", 1.5);
    }
  }

  for (let seamIndex = 0; seamIndex < ROWS; seamIndex += 1) {
    const y = settings.boardTop + seamIndex * settings.tileSize;
    ctx.strokeStyle = "rgba(255, 250, 241, 0.92)";
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.moveTo(settings.boardLeft + 8, y);
    ctx.lineTo(settings.boardLeft + settings.tileSize * COLS - 8, y);
    ctx.stroke();
  }
  for (let seamIndex = 1; seamIndex < COLS; seamIndex += 1) {
    const x = settings.boardLeft + seamIndex * settings.tileSize;
    ctx.strokeStyle = "rgba(213, 176, 138, 0.72)";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(x, settings.boardTop + 8);
    ctx.lineTo(x, settings.boardTop + settings.tileSize * (ROWS - 1) - 8);
    ctx.stroke();
  }

  drawTargetGlow(WHITE);
  drawTargetGlow(BLACK);
}

function drawTargetGlow(side) {
  const seamRow = targetRow(side);
  const { y } = positionToPixel([seamRow, 0]);
  const glow = ctx.createRadialGradient(LOGICAL_CANVAS_WIDTH / 2, y, 10, LOGICAL_CANVAS_WIDTH / 2, y, settings.tileSize * 2.7);
  glow.addColorStop(0, `${side === WHITE ? "rgba(227, 68, 54, 0.34)" : "rgba(248, 210, 55, 0.34)"}`);
  glow.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.ellipse(LOGICAL_CANVAS_WIDTH / 2, y, settings.tileSize * 2.9, 24, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = side === WHITE ? "rgba(227, 68, 54, 0.72)" : "rgba(248, 210, 55, 0.72)";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(settings.boardLeft + 6, y);
  ctx.lineTo(settings.boardLeft + settings.tileSize * COLS - 6, y);
  ctx.stroke();
}

function drawEdgePositions() {
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const { x, y } = positionToPixel([row, col]);
      ctx.fillStyle = "rgba(243, 248, 250, 0.96)";
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(213, 176, 138, 0.85)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  for (let row = 0; row < ROWS; row += 1) {
    const { y } = positionToPixel([row, 0]);
    ctx.fillStyle = settings.panelText;
    ctx.font = "700 20px 'Avenir Next', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(row + 1), settings.boardLeft - 34, y);
  }

  if (app.lastMove) {
    for (const coord of [app.lastMove.from, app.lastMove.to]) {
      const { x, y } = positionToPixel(coord);
      ctx.fillStyle = settings.lastMove;
      ctx.beginPath();
      ctx.arc(x, y, 26, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (app.selected) {
    const { x, y } = positionToPixel(app.selected);
    ctx.fillStyle = "rgba(250, 246, 158, 0.6)";
    ctx.beginPath();
    ctx.arc(x, y, 30, 0, Math.PI * 2);
    ctx.fill();
    for (const move of getLegalMovesFrom(app.state, app.selected)) {
      const point = positionToPixel(move.to);
      drawMoveMarker(point.x, point.y);
    }
  }
}

function drawMoveMarker(x, y) {
  ctx.fillStyle = "rgba(85, 232, 198, 0.5)";
  ctx.beginPath();
  ctx.arc(x, y, 18, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.95)";
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.fill();
}

function drawTrianglePiece(piece, x, y, selected = false) {
  const baseColor = colorForPiece(piece);
  const outline = mixHex(baseColor, "#6c5547", 0.18);
  const isPawn = piece.kind === PAWN;
  const width = isPawn ? 48 : 62;
  const height = isPawn ? 34 : 74;
  const seamLift = isPawn ? 6 : 14;

  let points;
  let shine;
  if (piece.side === WHITE) {
    points = [
      [x, y - height + seamLift],
      [x - width / 2, y + seamLift],
      [x + width / 2, y + seamLift],
    ];
    shine = [
      [x, y - height + seamLift + 10],
      [x - width / 4, y + seamLift - 10],
      [x + width / 10, y + seamLift - 4],
    ];
  } else {
    points = [
      [x - width / 2, y - seamLift],
      [x + width / 2, y - seamLift],
      [x, y + height - seamLift],
    ];
    shine = [
      [x - width / 10, y - seamLift + 4],
      [x + width / 4, y - seamLift + 10],
      [x, y + height - seamLift - 10],
    ];
  }

  ctx.save();
  if (selected) {
    ctx.fillStyle = "rgba(250, 246, 158, 0.42)";
    ctx.beginPath();
    ctx.arc(x, y, 34, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = "rgba(164,121,74,0.18)";
  ctx.beginPath();
  points.forEach(([px, py], index) => {
    const sx = px + 3;
    const sy = py + 7;
    if (index === 0) {
      ctx.moveTo(sx, sy);
    } else {
      ctx.lineTo(sx, sy);
    }
  });
  ctx.closePath();
  ctx.fill();

  const topY = Math.min(...points.map(([, py]) => py));
  const bottomY = Math.max(...points.map(([, py]) => py));
  const pieceGradient = ctx.createLinearGradient(x, topY, x, bottomY);
  pieceGradient.addColorStop(0, mixHex(baseColor, "#ffffff", 0.18));
  pieceGradient.addColorStop(0.45, baseColor);
  pieceGradient.addColorStop(1, mixHex(baseColor, "#684d40", 0.08));

  ctx.beginPath();
  points.forEach(([px, py], index) => {
    if (index === 0) {
      ctx.moveTo(px, py);
    } else {
      ctx.lineTo(px, py);
    }
  });
  ctx.closePath();
  ctx.fillStyle = pieceGradient;
  ctx.fill();

  ctx.strokeStyle = outline;
  ctx.lineWidth = 1.75;
  ctx.stroke();

  const shineGradient = ctx.createLinearGradient(x, topY, x, bottomY);
  shineGradient.addColorStop(0, "rgba(255,255,255,0.72)");
  shineGradient.addColorStop(1, "rgba(255,255,255,0.08)");
  ctx.fillStyle = shineGradient;
  ctx.beginPath();
  shine.forEach(([px, py], index) => {
    if (index === 0) {
      ctx.moveTo(px, py);
    } else {
      ctx.lineTo(px, py);
    }
  });
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawPieces(now) {
  if (app.setupMode) {
    return;
  }

  const hiddenOrigin = app.animation ? app.animation.move.from : null;
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      if (hiddenOrigin && hiddenOrigin[0] === row && hiddenOrigin[1] === col) {
        continue;
      }
      const piece = app.state.board[row][col];
      if (!piece) {
        continue;
      }
      const point = positionToPixel([row, col]);
      drawTrianglePiece(piece, point.x, point.y, !!app.selected && app.selected[0] === row && app.selected[1] === col);
    }
  }

  if (app.animation) {
    const start = positionToPixel(app.animation.move.from);
    const end = positionToPixel(app.animation.move.to);
    const progress = clamp((now - app.animation.startAt) / app.animation.duration, 0, 1);
    const eased = 1 - (1 - progress) * (1 - progress);
    const x = start.x + (end.x - start.x) * eased;
    const y = start.y + (end.y - start.y) * eased - 10 * (1 - Math.abs(0.5 - eased) * 2);
    drawTrianglePiece(app.animation.piece, x, y, false);
    if (progress >= 1) {
      finishAnimation();
    }
  }
}

function drawConfetti() {
  for (const particle of app.confetti) {
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.roundRect(particle.x, particle.y, particle.size, particle.size, 3);
    ctx.fill();
  }
}

function draw(now) {
  drawBoardBackground();
  drawEdgePositions();
  drawPieces(now);
  drawConfetti();
}

function tick(now) {
  updateConfetti(16);
  maybeStartAi(now);
  draw(now);
  requestAnimationFrame(tick);
}

function onCanvasClick(event) {
  if (app.setupMode || app.animation || currentWinner() !== null || !isHumanTurn()) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const scaleX = LOGICAL_CANVAS_WIDTH / rect.width;
  const scaleY = LOGICAL_CANVAS_HEIGHT / rect.height;
  const x = (event.clientX - rect.left) * scaleX;
  const y = (event.clientY - rect.top) * scaleY;
  const clicked = pointToCoord(x, y);
  if (!clicked) {
    app.selected = null;
    refreshUi();
    return;
  }

  if (app.selected) {
    const moves = getLegalMovesFrom(app.state, app.selected);
    const chosen = moves.find((move) => move.to[0] === clicked[0] && move.to[1] === clicked[1]);
    if (chosen) {
      startMove(chosen);
      refreshUi();
      return;
    }
  }

  const piece = app.state.board[clicked[0]][clicked[1]];
  if (piece && piece.side === app.state.sideToMove && getLegalMovesFrom(app.state, clicked).length > 0) {
    app.selected = clicked;
  } else {
    app.selected = null;
  }
  refreshUi();
}

function cycleDifficulty() {
  const keys = Object.keys(DIFFICULTY_PROFILES);
  const index = keys.indexOf(app.difficulty);
  app.difficulty = keys[(index + 1) % keys.length];
  refreshUi();
}

function toggleMode() {
  app.playMode = app.playMode === PLAY_MODE_AI ? PLAY_MODE_HOTSEAT : PLAY_MODE_AI;
  enterSetupMode();
}

function swapAgentSide() {
  if (app.playMode !== PLAY_MODE_AI) {
    return;
  }
  app.agentSide = app.agentSide === WHITE ? BLACK : WHITE;
  enterSetupMode();
}

restartButton.addEventListener("click", () => resetGame());
openingButton.addEventListener("click", () => enterSetupMode());
modeButton.addEventListener("click", toggleMode);
difficultyButton.addEventListener("click", cycleDifficulty);
swapButton.addEventListener("click", swapAgentSide);
setupButton.addEventListener("click", advanceSetup);
rematchOverlayButton.addEventListener("click", () => resetGame());
canvas.addEventListener("click", onCanvasClick);
window.addEventListener("resize", resizeCanvas);

window.addEventListener("keydown", (event) => {
  if (event.key === "r" || event.key === "R") {
    resetGame();
  } else if (event.key === "o" || event.key === "O") {
    enterSetupMode();
  } else if (event.key === "m" || event.key === "M") {
    toggleMode();
  } else if (event.key === "d" || event.key === "D") {
    cycleDifficulty();
  } else if ((event.key === "s" || event.key === "S") && app.playMode === PLAY_MODE_AI) {
    swapAgentSide();
  } else if (app.setupMode && event.key === "Enter") {
    advanceSetup();
  }
});

resizeCanvas();
enterSetupMode();
refreshUi();
requestAnimationFrame(tick);
