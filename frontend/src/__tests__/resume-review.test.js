/**
 * 简历 AI 评估的纯函数单测。
 *
 * 只测 `scoreBand`：它是这一块里唯一有分支的逻辑（四档边界 + 空值），而边界
 * 写错是很安静的 —— 6.5 落到哪一档不会报错，只会让人看到与后端不一致的说法。
 *
 * DOM 层行为（弹窗、脱敏渲染、错误展示）由 `mock/resume-harness.html` 与
 * `mock/interviews-harness.html` 覆盖。
 */

import { describe, expect, it } from 'vitest';
import { scoreBand } from '../components/resume-review.js';

describe('scoreBand —— 分数档位', () => {
  it('10 与 8 → 最高档（边界 8 含在高档里）', () => {
    expect(scoreBand(10).tone).toBe('is-high');
    expect(scoreBand(8).tone).toBe('is-high');
    expect(scoreBand(8).label).toBe('重合度高');
  });

  it('7.9 → 第二档（8 以下就不是高档了）', () => {
    expect(scoreBand(7.9).tone).toBe('is-mid');
  });

  it('6.5 → 第二档（与后端 PASS_THRESHOLD 同值的边界，含在中间档）', () => {
    expect(scoreBand(6.5).tone).toBe('is-mid');
  });

  it('6.4 → 第三档', () => {
    expect(scoreBand(6.4).tone).toBe('is-low');
  });

  it('4 → 第三档（边界 4 含在第三档里）', () => {
    expect(scoreBand(4).tone).toBe('is-low');
  });

  it('3.9 → 最低档', () => {
    expect(scoreBand(3.9).tone).toBe('is-weak');
  });

  it('0 → 最低档', () => {
    expect(scoreBand(0).tone).toBe('is-weak');
    expect(scoreBand(0).label).toBe('重合较少');
  });

  it('null / undefined → 无档位（候选人默认档拿不到分数，界面应当整块不渲染）', () => {
    expect(scoreBand(null)).toEqual({ label: '', tone: '' });
    expect(scoreBand(undefined)).toEqual({ label: '', tone: '' });
  });

  it('**措辞红线**：四档文案都不含去留判断', () => {
    // 后端已经不说了（module-27 §4.2 的措辞红线），前端不要又贴一个判断标签
    // 把它破掉 —— UI 上的每个字都受 PRD §4.9 约束。
    const forbidden = ['通过', '推荐', '淘汰', '录用', '进入', '不建议'];
    for (const score of [10, 7, 5, 1]) {
      const { label } = scoreBand(score);
      for (const word of forbidden) {
        expect(label).not.toContain(word);
      }
    }
  });
});
