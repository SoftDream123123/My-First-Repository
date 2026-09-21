/**
 * components/radar.js —— 多维评分的雷达图（SVG）
 *
 * 不引入图表库：几何简单、完全可控，而 ECharts 之类会给「原生 JS + 无 UI 框架」
 * 的约束带来数百 KB 依赖。
 *
 * 用 SVG 而不是 Canvas：颜色由 CSS 令牌给（分数色带只管评分，见 tokens.css），
 * 打印时跟着浏览器一起走，缩放不糊。
 *
 * **几何是纯函数**（`axisAngle` / `polar` / `radarGeometry`），单测覆盖
 * （`src/__tests__/radar.test.js`）—— 图形画歪了靠肉眼很难发现。
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/** 画布尺寸按「4 个汉字 + 两侧留白」定：常用的 3–6 维都不会把标签挤出画布。 */
export const RADAR_BOX = { width: 320, height: 290, cx: 160, cy: 142, r: 86, labelR: 108 };

export const SCORE_MAX = 10;

/**
 * 分数带的阈值。**6.5 不是拍出来的** —— 它取自 module-04 §4.4 对 `strengths` 的定义，
 * 全站（列表、报告、雷达、图例）共用这一个阈值。
 */
export const PASS_THRESHOLD = 6.5;

export function scoreClass(score) { return score >= PASS_THRESHOLD ? 'is-pass' : 'is-watch'; }

/** 环的比例：四圈网格。 */
const RING_RATIOS = [0.25, 0.5, 0.75, 1];

/** 第 `index` 个维度的角度（弧度）。**从正上方开始、顺时针**。 */
export function axisAngle(index, total) {
  return (-Math.PI / 2) + (index * 2 * Math.PI) / total;
}

export function polar(cx, cy, radius, angle) {
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
}

const round1 = (n) => Number(n.toFixed(1));

/** 分数夹到 0–10：异常值不该把顶点甩到画布外。 */
const clamp = (score) => Math.min(Math.max(Number(score) || 0, 0), SCORE_MAX);

/**
 * 纯函数：算出雷达图该画什么。返回纯数据，不碰 DOM。
 *
 * `scores` 是 `{ 维度名: 分数 }`，**可以只到一部分**（SSE 逐维度推）。
 * 关键规则：**全部维度都有分才封上多边形** —— 少一个顶点就不是同一个形状，
 * 提前封口等于编一个不存在的读数。
 */
export function radarGeometry(dims, scores, box = RADAR_BOX) {
  const { cx, cy, r, labelR } = box;
  const total = dims.length;
  if (!total) {
    return { rings: [], spokes: [], labels: [], area: null, dots: [], complete: false };
  }

  const rings = RING_RATIOS.map((ratio) =>
    dims.map((_, i) => polar(cx, cy, r * ratio, axisAngle(i, total))));

  const spokes = dims.map((_, i) => {
    const [x, y] = polar(cx, cy, r, axisAngle(i, total));
    return { x1: cx, y1: cy, x2: x, y2: y };
  });

  // 维度名绕圈排：左半边的靠右收，免得压出画布
  const labels = dims.map((dim, i) => {
    const angle = axisAngle(i, total);
    const [x, y] = polar(cx, cy, labelR, angle);
    const cos = Math.cos(angle);
    return {
      text: dim,
      x,
      y: y + 4,
      anchor: Math.abs(cos) < 0.2 ? 'middle' : (cos > 0 ? 'start' : 'end'),
    };
  });

  const complete = dims.every((dim) => typeof scores[dim] === 'number');
  const area = complete
    ? dims.map((dim, i) => polar(cx, cy, r * (clamp(scores[dim]) / SCORE_MAX), axisAngle(i, total)))
    : null;

  const dots = dims
    .map((dim, i) => ({ dim, score: scores[dim], i }))
    .filter((item) => typeof item.score === 'number')
    .map(({ dim, score, i }) => {
      const [x, y] = polar(cx, cy, r * (clamp(score) / SCORE_MAX), axisAngle(i, total));
      return { dimension: dim, score, x, y };
    });

  return { rings, spokes, labels, area, dots, complete };
}

/** SVG 必须用 createElementNS 建 —— `dom.js` 的 `el` 建出来的是 HTMLUnknownElement。 */
function svgEl(tag, attrs, children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined) continue;
    node.setAttribute(key, String(value));
  }
  for (const child of (children || []).flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const pointsOf = (points) => points.map(([x, y]) => `${round1(x)},${round1(y)}`).join(' ');

export function radarSvg(dims, scores) {
  const { area, dots, labels, rings, spokes } = radarGeometry(dims, scores);

  const nodes = [];
  for (const ring of rings) nodes.push(svgEl('polygon', { class: 'radar-grid', points: pointsOf(ring) }));
  for (const spoke of spokes) {
    nodes.push(svgEl('line', {
      class: 'radar-spoke',
      x1: spoke.x1, y1: spoke.y1, x2: round1(spoke.x2), y2: round1(spoke.y2),
    }));
  }
  for (const label of labels) {
    nodes.push(svgEl('text', {
      class: 'radar-label', x: round1(label.x), y: round1(label.y), 'text-anchor': label.anchor,
    }, [label.text]));
  }

  if (area) {
    // 多边形的颜色跟着**平均分**走：单看形状看不出整体强弱
    const mean = dims.reduce((sum, dim) => sum + clamp(scores[dim]), 0) / dims.length;
    nodes.push(svgEl('polygon', { class: `radar-area ${scoreClass(mean)}`, points: pointsOf(area) }));
  }

  for (const dot of dots) {
    nodes.push(svgEl('circle', {
      class: `radar-dot ${scoreClass(dot.score)}`,
      cx: round1(dot.x), cy: round1(dot.y), r: 3.5,
    }));
  }

  return svgEl('svg', {
    class: 'radar',
    viewBox: `0 0 ${RADAR_BOX.width} ${RADAR_BOX.height}`,
    role: 'img',
    'aria-label': dims
      .map((dim) => `${dim} ${typeof scores[dim] === 'number' ? scores[dim].toFixed(1) : '待评分'} 分`)
      .join('；'),
  }, nodes);
}
