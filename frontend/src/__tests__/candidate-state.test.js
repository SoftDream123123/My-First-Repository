/**
 * candidateState 纯函数单测。
 *
 * 为什么这一条值得单独测：它把后端的两字段（`status` + `submitted`）译成
 * 候选人的四态，而**列表页与详情页都用它**。译错一档的表现不是报错，
 * 而是「说了一句不对的话」—— 比如把 HR 已经收口、候选人再也答不了的场次
 * 显示成「待作答」。这类错误在界面上很安静，抽成纯函数后就只是几行断言。
 *
 * ⚠️ 只 import 纯函数。`shell.js` 里的 DOM 构造函数（`candidateStateTag` 等）
 * 需要 `document`，本工程**不引入 jsdom**（module-07 §8.1 的既有决策）。
 */

import { describe, expect, it } from 'vitest';
import { candidateState } from '../components/shell.js';

const item = (over = {}) => ({
  id: 3, position_name: '后端工程师', status: 'ongoing',
  question_count: 8, answered_count: 0, submitted: false, resume_id: null,
  created_at: '2026-09-21T10:00:00', ...over,
});

describe('candidateState —— 候选人看到的四态', () => {
  it('进行中且未交卷 → 待作答', () => {
    expect(candidateState(item())).toBe('await');
  });

  it('已交卷 → 已交卷', () => {
    expect(candidateState(item({ submitted: true }))).toBe('submitted');
  });

  it('已评估 → 有反馈', () => {
    expect(candidateState(item({ status: 'evaluated' }))).toBe('feedback');
  });

  it('已评估优先于已交卷（评估完成就一定有反馈可看）', () => {
    // 反馈接口只认 `status`，与交没交过卷无关。若这里先判 submitted，
    // 一个交过卷又被评估的场次就拿不到「查看反馈」的入口
    expect(candidateState(item({ status: 'evaluated', submitted: true }))).toBe('feedback');
  });

  it('未交卷但面试已被收口 → 已结束，**不是**待作答', () => {
    // HR 可以不等候选人交卷就手工标记完成。那一场当事人已经答不了了，
    // 显示成「待作答」等于让他反复点进去撞一堵墙
    expect(candidateState(item({ status: 'completed' }))).toBe('closed');
    expect(candidateState(item({ status: 'evaluating' }))).toBe('closed');
  });

  it('已交卷但尚未评估 → 已交卷（还没到有反馈那一步）', () => {
    expect(candidateState(item({ status: 'completed', submitted: true }))).toBe('submitted');
    expect(candidateState(item({ status: 'evaluating', submitted: true }))).toBe('submitted');
  });

  it('四态取值封闭在一个已知集合里', () => {
    // 「有反馈」的两条路径（evaluated）与其余三态要能被穷举出来 ——
    // 多出一个未上色的状态值时，`tag--xxx` 会没有对应规则而显示成裸标签
    const all = [
      candidateState(item()),
      candidateState(item({ submitted: true })),
      candidateState(item({ status: 'evaluated' })),
      candidateState(item({ status: 'completed' })),
    ];
    expect(new Set(all)).toEqual(new Set(['await', 'submitted', 'feedback', 'closed']));
  });
});
