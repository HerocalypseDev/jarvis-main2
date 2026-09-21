const CELL = 20;
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const COLS = canvas.width / CELL;
const ROWS = canvas.height / CELL;
const scoreEl = document.getElementById("score");

let snake, dir, pending, food, score, alive;

function reset() {
  snake = [{ x: COLS >> 1, y: ROWS >> 1 }, { x: (COLS >> 1) - 1, y: ROWS >> 1 }];
  dir = pending = { x: 1, y: 0 };
  score = 0;
  alive = true;
  scoreEl.textContent = score;
  placeFood();
}

function placeFood() {
  const free = [];
  for (let x = 0; x < COLS; x++)
    for (let y = 0; y < ROWS; y++)
      if (!snake.some(s => s.x === x && s.y === y)) free.push({ x, y });
  food = free.length ? free[Math.floor(Math.random() * free.length)] : null;
}

const KEYS = {
  ArrowUp: [0, -1], w: [0, -1], ArrowDown: [0, 1], s: [0, 1],
  ArrowLeft: [-1, 0], a: [-1, 0], ArrowRight: [1, 0], d: [1, 0],
};

document.addEventListener("keydown", e => {
  if (e.key === "r" || e.key === "R") return reset();
  const k = KEYS[e.key];
  if (!k) return;
  e.preventDefault();
  if (k[0] + dir.x !== 0 || k[1] + dir.y !== 0) pending = { x: k[0], y: k[1] };
});

function step() {
  dir = pending;
  const head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };
  const eating = food && head.x === food.x && head.y === food.y;
  const body = eating ? snake : snake.slice(0, -1);
  if (head.x < 0 || head.x >= COLS || head.y < 0 || head.y >= ROWS ||
      body.some(s => s.x === head.x && s.y === head.y)) {
    alive = false;
    return;
  }
  snake.unshift(head);
  if (eating) {
    scoreEl.textContent = ++score;
    placeFood();
  } else {
    snake.pop();
  }
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (food) {
    ctx.fillStyle = "#e33";
    ctx.fillRect(food.x * CELL + 2, food.y * CELL + 2, CELL - 4, CELL - 4);
  }
  snake.forEach((s, i) => {
    ctx.fillStyle = i === 0 ? "#6f6" : "#3a3";
    ctx.fillRect(s.x * CELL + 1, s.y * CELL + 1, CELL - 2, CELL - 2);
  });
  if (!alive) {
    ctx.fillStyle = "#fff";
    ctx.font = "20px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Game over - press R to restart", canvas.width / 2, canvas.height / 2);
  }
}

reset();
setInterval(() => { if (alive) step(); draw(); }, 110);
