/**
 * Canvas 雷达图（module-07 §4.4）。
 *
 * 不引入图表库：几何简单、完全可控，而 ECharts 等会给"原生 JS + 无 UI 框架"
 * 的约束带来数百 KB 的依赖。
 *
 * 颜色从 CSS 变量读取，保证调色板只有一处定义。
 */

const RING_VALUES = [2.5, 5, 7.5, 10];
const MAX_VALUE = 10; // 与后端 0–10 分制对齐（PRD §4.5）
const LABEL_GAP = 26; // 顶点到标签锚点的距离
const LABEL_FONT = '13px "Segoe UI", "Microsoft YaHei", sans-serif';
const SCORE_FONT = '14px Georgia, "Times New Roman", serif';
const MIN_SIZE = 260;
const MAX_SIZE = 400;

/**
 * 纯函数：把分数映射为顶点坐标。
 *
 * 第 i 个维度角度为 -90° + i * 360°/N —— 从正上方开始，顺时针。
 * N < 3 时无法构成多边形，返回空数组（由调用方显示降级文案）。
 */
export function computePoints(values, center, radius, maxValue = MAX_VALUE) {
  const n = values.length;
  if (n < 3) return [];

  return values.map((value, i) => {
    const angle = ((-90 + (i * 360) / n) * Math.PI) / 180;
    // 分数先夹到区间内，避免异常值把顶点甩到画布外
    const ratio = Math.min(Math.max(value, 0), maxValue) / maxValue;
    const r = radius * ratio;
    return {
      x: center.x + r * Math.cos(angle),
      y: center.y + r * Math.sin(angle),
    };
  });
}

/** 顶点角度（弧度），供标签定位复用。 */
function angleAt(index, total) {
  return ((-90 + (index * 360) / total) * Math.PI) / 180;
}

function readPalette() {
  const styles = getComputedStyle(document.documentElement);
  const read = (name) => styles.getPropertyValue(name).trim();
  return {
    line: read('--line') || '#dce1e6',
    faint: read('--faint') || '#8b98a5',
    ink: read('--ink') || '#16202b',
    muted: read('--muted') || '#5e6c7a',
    pass: read('--pass') || '#0e6b5c',
    passWash: read('--pass-wash') || '#e6f1ee',
    watch: read('--watch') || '#9a6b12',
    watchWash: read('--watch-wash') || '#f7efdd',
  };
}

/** 分数走通过绿还是待改进赭 —— 与列表、报告用同一阈值。 */
const isPass = (score) => score >= 6.5;

/**
 * 绘制雷达图。
 *
 * @param {HTMLCanvasElement} canvas
 * @param {{dimension: string, score: number}[]} data
 * @param {{revealed?: number}} options revealed 用于 SSE 的"逐维度生长"，
 *        未到达的维度按 0 处理并灰显。
 */
export function drawRadar(canvas, data, options = {}) {
  const revealed = options.revealed ?? data.length;
  const palette = readPalette();

  const box = canvas.parentElement?.getBoundingClientRect();
  const cssSize = Math.max(MIN_SIZE, Math.min(box?.width || 320, MAX_SIZE));

  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssSize * dpr;
  canvas.height = cssSize * dpr;
  canvas.style.width = `${cssSize}px`;
  canvas.style.height = `${cssSize}px`;

  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssSize, cssSize);

  // N < 3 画不出多边形 —— 交给调用方显示降级文案
  if (data.length < 3) return false;

  // 先量标签宽度再决定留白。固定留白会让左右两侧的标签被裁掉：
  // 它们用 textAlign: right / left 向外延伸，宽度取决于维度名的字数。
  ctx.font = LABEL_FONT;
  const maxLabelWidth = Math.max(
    ...data.map((item) => ctx.measureText(item.dimension).width),
  );
  const padding = LABEL_GAP + maxLabelWidth + 6;

  const center = { x: cssSize / 2, y: cssSize / 2 };
  const radius = Math.max(48, cssSize / 2 - padding);

  drawGrid(ctx, data.length, center, radius, palette);
  drawAxes(ctx, data.length, center, radius, palette);

  // 未到达的维度当作 0 分，于是多边形从这里"长"出来
  const values = data.map((item, i) => (i < revealed ? item.score : 0));
  drawDataPolygon(ctx, values, center, radius, palette);

  drawVertices(ctx, data, center, radius, revealed, palette);
  drawDimensionLabels(ctx, data, center, radius, revealed, palette);

  return true;
}

function drawGrid(ctx, n, center, radius, palette) {
  ctx.strokeStyle = palette.line;
  ctx.lineWidth = 1;

  for (const value of RING_VALUES) {
    const points = computePoints(new Array(n).fill(value), center, radius);
    ctx.beginPath();
    points.forEach((point, i) => (i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
    ctx.closePath();
    ctx.stroke();
  }
}

function drawAxes(ctx, n, center, radius, palette) {
  ctx.strokeStyle = palette.line;
  ctx.lineWidth = 1;

  for (let i = 0; i < n; i += 1) {
    const angle = angleAt(i, n);
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(center.x + radius * Math.cos(angle), center.y + radius * Math.sin(angle));
    ctx.stroke();
  }
}

function drawDataPolygon(ctx, values, center, radius, palette) {
  const points = computePoints(values, center, radius);
  if (points.length < 3) return;

  const average = values.reduce((sum, v) => sum + v, 0) / values.length;
  const stroke = isPass(average) ? palette.pass : palette.watch;
  const fill = isPass(average) ? palette.passWash : palette.watchWash;

  ctx.beginPath();
  points.forEach((point, i) => (i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
  ctx.closePath();

  ctx.fillStyle = fill;
  ctx.globalAlpha = 0.85;
  ctx.fill();
  ctx.globalAlpha = 1;

  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.75;
  ctx.lineJoin = 'round';
  ctx.stroke();
}

function drawVertices(ctx, data, center, radius, revealed, palette) {
  data.forEach((item, i) => {
    if (i >= revealed) return;

    const angle = angleAt(i, data.length);
    const r = (Math.min(Math.max(item.score, 0), MAX_VALUE) / MAX_VALUE) * radius;
    const x = center.x + r * Math.cos(angle);
    const y = center.y + r * Math.sin(angle);

    // 顶点实心小圆
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fillStyle = isPass(item.score) ? palette.pass : palette.watch;
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // 分数紧贴顶点外侧
    const lx = center.x + (r + 12) * Math.cos(angle);
    const ly = center.y + (r + 12) * Math.sin(angle);
    ctx.font = SCORE_FONT;
    ctx.fillStyle = isPass(item.score) ? palette.pass : palette.watch;
    ctx.textAlign = cos(Math.cos(angle));
    ctx.textBaseline = sin(Math.sin(angle));
    ctx.fillText(item.score.toFixed(1), lx, ly);
  });
}

function drawDimensionLabels(ctx, data, center, radius, revealed, palette) {
  ctx.font = LABEL_FONT;

  data.forEach((item, i) => {
    const angle = angleAt(i, data.length);
    const lx = center.x + (radius + LABEL_GAP) * Math.cos(angle);
    const ly = center.y + (radius + LABEL_GAP) * Math.sin(angle);

    ctx.fillStyle = i < revealed ? palette.ink : palette.faint;
    ctx.textAlign = cos(Math.cos(angle));
    ctx.textBaseline = sin(Math.sin(angle));
    ctx.fillText(item.dimension, lx, ly);
  });
}

/* 按顶点方位调整对齐方式，保证标签不出界 */
function cos(value) {
  if (value > 0.3) return 'left';
  if (value < -0.3) return 'right';
  return 'center';
}

function sin(value) {
  if (value > 0.3) return 'top';
  if (value < -0.3) return 'bottom';
  return 'middle';
}
