/**
 * 雷达图几何的纯函数单测。
 *
 * 图形画歪了**靠肉眼几乎发现不了**（少一个顶点、半径比例算错、0 分没落圆心，
 * 看上去都「像那么回事」），但它会让人对分数做出错误判断。所以把几何抽出来
 * 用坐标断言钉住，而不是靠截图看。
 */

import { describe, expect, it } from 'vitest';
import { PASS_THRESHOLD, RADAR_BOX, axisAngle, polar, radarGeometry, scoreClass } from '../components/radar.js';

const DIMS4 = ['沟通能力', '专业能力', '逻辑思维', '文化契合'];
const ALL_10 = { 沟通能力: 10, 专业能力: 10, 逻辑思维: 10, 文化契合: 10 };

const dist = (p, [x, y]) => Math.hypot(p[0] - x, p[1] - y);

describe('axisAngle', () => {
  it('第 0 个维度在正上方（-90°）', () => {
    expect(axisAngle(0, 4)).toBeCloseTo(-Math.PI / 2, 10);
  });

  it('相邻维度均分整圈', () => {
    expect(axisAngle(1, 4) - axisAngle(0, 4)).toBeCloseTo(Math.PI / 2, 10);
    expect(axisAngle(3, 4) - axisAngle(2, 4)).toBeCloseTo(Math.PI / 2, 10);
    // 6 个维度时每一步 60°
    expect(axisAngle(1, 6) - axisAngle(0, 6)).toBeCloseTo(Math.PI / 3, 10);
  });

  it('顺时针（角度递增）', () => {
    expect(axisAngle(1, 4)).toBeGreaterThan(axisAngle(0, 4));
  });
});

describe('polar', () => {
  it('正上方是 (cx, cy - r)', () => {
    const [x, y] = polar(100, 100, 50, -Math.PI / 2);
    expect(x).toBeCloseTo(100, 10);
    expect(y).toBeCloseTo(50, 10);
  });

  it('正右方是 (cx + r, cy)', () => {
    const [x, y] = polar(100, 100, 50, 0);
    expect(x).toBeCloseTo(150, 10);
    expect(y).toBeCloseTo(100, 10);
  });
});

describe('radarGeometry —— 网格与轴', () => {
  const g = radarGeometry(DIMS4, ALL_10);

  it('画 4 圈网格，比例 0.25 / 0.5 / 0.75 / 1', () => {
    expect(g.rings).toHaveLength(4);
    g.rings.forEach((ring, i) => {
      expect(ring).toHaveLength(4);
      const expected = RADAR_BOX.r * [0.25, 0.5, 0.75, 1][i];
      expect(dist(ring[0], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(expected, 6);
    });
  });

  it('每个维度一条轴，从圆心出发、长度等于半径', () => {
    expect(g.spokes).toHaveLength(4);
    for (const spoke of g.spokes) {
      expect(spoke.x1).toBe(RADAR_BOX.cx);
      expect(spoke.y1).toBe(RADAR_BOX.cy);
      expect(dist([spoke.x2, spoke.y2], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(RADAR_BOX.r, 6);
    }
  });

  it('环的第一个顶点在正上方', () => {
    expect(g.rings[3][0][0]).toBeCloseTo(RADAR_BOX.cx, 6);
    expect(g.rings[3][0][1]).toBeCloseTo(RADAR_BOX.cy - RADAR_BOX.r, 6);
  });
});

describe('radarGeometry —— 顶点半径与分数成正比', () => {
  it('满分落在半径圆上', () => {
    const g = radarGeometry(DIMS4, ALL_10);
    for (const point of g.area) {
      expect(dist(point, [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(RADAR_BOX.r, 6);
    }
  });

  it('5 分落在半半径处', () => {
    const g = radarGeometry(DIMS4, { 沟通能力: 5, 专业能力: 5, 逻辑思维: 5, 文化契合: 5 });
    expect(dist(g.area[0], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(RADAR_BOX.r / 2, 6);
  });

  it('0 分落在圆心', () => {
    const g = radarGeometry(DIMS4, { 沟通能力: 0, 专业能力: 0, 逻辑思维: 0, 文化契合: 0 });
    expect(dist(g.area[0], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(0, 6);
  });

  it('越界分数被夹到 0–10（异常值不该把顶点甩出画布）', () => {
    const high = radarGeometry(DIMS4, { 沟通能力: 99, 专业能力: 99, 逻辑思维: 99, 文化契合: 99 });
    expect(dist(high.area[0], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(RADAR_BOX.r, 6);

    const low = radarGeometry(DIMS4, { 沟通能力: -5, 专业能力: -5, 逻辑思维: -5, 文化契合: -5 });
    expect(dist(low.area[0], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(0, 6);
  });

  it('顶点顺序与维度顺序一致（不然形状会拧）', () => {
    const g = radarGeometry(DIMS4, { 沟通能力: 10, 专业能力: 0, 逻辑思维: 0, 文化契合: 0 });
    expect(g.area[0][1]).toBeLessThan(RADAR_BOX.cy);       // 第 1 个维度的顶点在圆心上方
    expect(dist(g.area[1], [RADAR_BOX.cx, RADAR_BOX.cy])).toBeCloseTo(0, 6);
  });
});

describe('radarGeometry —— 分数只到一部分时不封口', () => {
  const partial = { 沟通能力: 7, 专业能力: 6 };

  it('缺维度 → 不画多边形（少一个顶点就不是同一个形状）', () => {
    const g = radarGeometry(DIMS4, partial);
    expect(g.complete).toBe(false);
    expect(g.area).toBeNull();
  });

  it('但已到的维度照常画点', () => {
    const g = radarGeometry(DIMS4, partial);
    expect(g.dots.map((d) => d.dimension)).toEqual(['沟通能力', '专业能力']);
    expect(g.dots[0].score).toBe(7);
  });

  it('全部到齐才封口', () => {
    const g = radarGeometry(DIMS4, { ...partial, 逻辑思维: 5, 文化契合: 5 });
    expect(g.complete).toBe(true);
    expect(g.area).toHaveLength(4);
  });

  it('没到的维度不画点', () => {
    expect(radarGeometry(DIMS4, partial).dots).toHaveLength(2);
    expect(radarGeometry(DIMS4, {}).dots).toHaveLength(0);
  });
});

describe('radarGeometry —— 标签与退化情况', () => {
  it('标签按方位对齐，免得压出画布', () => {
    const g = radarGeometry(DIMS4, ALL_10);
    // 4 个维度：正上 / 正右 / 正下 / 正左 → middle / start / middle / end
    expect(g.labels.map((l) => l.anchor)).toEqual(['middle', 'start', 'middle', 'end']);
    expect(g.labels.map((l) => l.text)).toEqual(DIMS4);
  });

  it('没有维度时全部为空，不抛错', () => {
    const g = radarGeometry([], {});
    expect(g.rings).toEqual([]);
    expect(g.area).toBeNull();
    expect(g.labels).toEqual([]);
    expect(g.complete).toBe(false);
  });
});

describe('scoreClass —— 全站共用的 6.5 阈值', () => {
  it('阈值本身算达标（>= 而不是 >）', () => {
    expect(scoreClass(PASS_THRESHOLD)).toBe('is-pass');
  });

  it('刚好差一点算待改进', () => {
    expect(scoreClass(6.4)).toBe('is-watch');
  });

  it('两端都是闭区间', () => {
    expect(scoreClass(10)).toBe('is-pass');
    expect(scoreClass(0)).toBe('is-watch');
  });
});
