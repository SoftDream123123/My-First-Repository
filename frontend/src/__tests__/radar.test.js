/**
 * 雷达图几何单测（module-07 §8.3）。
 *
 * `computePoints` 是纯函数：不碰 DOM、不碰 Canvas，因此可以在 node 环境直接断言。
 * 几何画错的症状很隐蔽（图形歪一点、标签出界），靠肉眼看报告页很难发现。
 */

import { describe, expect, it } from 'vitest';

import { computePoints } from '../components/radar.js';

const CENTER = { x: 0, y: 0 };
const RADIUS = 100;

/** 顶点到中心的距离。 */
const distance = (point) => Math.hypot(point.x - CENTER.x, point.y - CENTER.y);

/** 顶点相对中心的角度（度）。 */
const angleDeg = (point) =>
  (Math.atan2(point.y - CENTER.y, point.x - CENTER.x) * 180) / Math.PI;

describe('computePoints', () => {
  it('第一个顶点在正上方（角度 -90°）', () => {
    const [first] = computePoints([10, 10, 10, 10], CENTER, RADIUS);

    expect(first.x).toBeCloseTo(CENTER.x, 6);
    expect(first.y).toBeLessThan(CENTER.y);
    expect(angleDeg(first)).toBeCloseTo(-90, 6);
  });

  it('N=4 时相邻顶点间隔 90°', () => {
    const points = computePoints([10, 10, 10, 10], CENTER, RADIUS);
    const angles = points.map(angleDeg);

    for (let i = 1; i < angles.length; i += 1) {
      expect(angles[i] - angles[i - 1]).toBeCloseTo(90, 6);
    }
  });

  it('半径与分数成正比（5 分与 10 分约为 1:2）', () => {
    const [half] = computePoints([5, 5, 5], CENTER, RADIUS);
    const [full] = computePoints([10, 10, 10], CENTER, RADIUS);

    expect(distance(full) / distance(half)).toBeCloseTo(2, 6);
  });

  it('0 分时顶点落在圆心', () => {
    for (const point of computePoints([0, 0, 0], CENTER, RADIUS)) {
      expect(distance(point)).toBeCloseTo(0, 6);
    }
  });

  it('满分 10 恰好落在 radius 上（与后端 0–10 分制对齐）', () => {
    const [point] = computePoints([10, 0, 0], CENTER, RADIUS);

    expect(distance(point)).toBeCloseTo(RADIUS, 6);
  });

  it('维度不足 3 个时返回空数组（由调用方显示降级文案）', () => {
    expect(computePoints([10, 10], CENTER, RADIUS)).toEqual([]);
    expect(computePoints([10], CENTER, RADIUS)).toEqual([]);
    expect(computePoints([], CENTER, RADIUS)).toEqual([]);
  });

  it('超出 0–10 的异常分数被夹到区间内，顶点不会飞出画布', () => {
    const points = computePoints([15, -5, 10], CENTER, RADIUS);

    expect(distance(points[0])).toBeCloseTo(RADIUS, 6); // 15 → 10
    expect(distance(points[1])).toBeCloseTo(0, 6); // -5 → 0
    expect(distance(points[2])).toBeCloseTo(RADIUS, 6);
  });

  it('顶点数量始终等于维度数量', () => {
    expect(computePoints([7, 8, 9, 10, 6], CENTER, RADIUS)).toHaveLength(5);
  });
});
