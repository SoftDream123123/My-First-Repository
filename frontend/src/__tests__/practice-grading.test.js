/**
 * 判分结果的读取与显示 —— 纯函数单测。
 *
 * 两个函数都有一处**出错也不会报错**的地方，所以各值得一条断言：
 *
 * - `referenceAnswerOf`：参考答案按题型二选一（单选 `correct_answer` /
 *   简答 `reference_answer`）。取错字段的表现是「正确答案那一项没被标出来」，
 *   界面不报错、也不影响判分，只是复盘栏空着。**原型就是这么写的。**
 * - `percent`：正确率为 `0` 与「没有可统计的作答」是两件事。把 `0` 显示成 `—`
 *   会让一个真考了 0 分的人以为系统没在统计他。
 *
 * ⚠️ 只 import 纯函数。本工程**不引入 jsdom**（module-07 §8.1 的既有决策）。
 */

import { describe, expect, it } from 'vitest';
import { percent, referenceAnswerOf } from '../components/shell.js';

describe('referenceAnswerOf —— 参考答案按题型二选一', () => {
  it('单选题取 correct_answer', () => {
    expect(referenceAnswerOf({ correct_answer: '未认证', reference_answer: null })).toBe('未认证');
  });

  it('简答题取 reference_answer', () => {
    expect(referenceAnswerOf({ correct_answer: null, reference_answer: '先看监控再定位' }))
      .toBe('先看监控再定位');
  });

  it('判错的单选**同样**带着正确答案（复盘就是要看它）', () => {
    expect(referenceAnswerOf({
      is_correct: false, correct_answer: '未认证', reference_answer: null,
    })).toBe('未认证');
  });

  it('两个都为空（简答没有参考答案，或未判分）→ null', () => {
    expect(referenceAnswerOf({ correct_answer: null, reference_answer: null })).toBeNull();
  });

  it('两个都给时以 reference_answer 为准（契约上不会同时给，这里只保证不崩）', () => {
    expect(referenceAnswerOf({ correct_answer: 'A', reference_answer: 'B' })).toBe('B');
  });

  it('响应形状不对时不抛异常，返回 null', () => {
    expect(referenceAnswerOf(null)).toBeNull();
    expect(referenceAnswerOf(undefined)).toBeNull();
    expect(referenceAnswerOf({})).toBeNull();
  });

  it('**只读 reference_answer 是不够的** —— 单选会丢答案（原型踩过的坑）', () => {
    const result = { correct_answer: '未认证', reference_answer: null };
    expect(referenceAnswerOf(result)).not.toBeNull();
    // 钉住那版的写法会给 null，且不会有任何报错
    expect(result.reference_answer ?? null).toBeNull();
  });
});

describe('percent —— 正确率显示', () => {
  it('null → 「—」（没有可统计的作答）', () => {
    expect(percent(null)).toBe('—');
    expect(percent(undefined)).toBe('—');
  });

  it('**0 → 「0%」而不是「—」** —— 真考了 0 分与没数据是两件事', () => {
    expect(percent(0)).toBe('0%');
  });

  it('四舍五入到整数百分比', () => {
    expect(percent(0.714)).toBe('71%');
    expect(percent(0.667)).toBe('67%');
    expect(percent(1)).toBe('100%');
  });

  it('极小但非零的值仍如实报出，不退化成 0% 之外的别的东西', () => {
    expect(percent(0.004)).toBe('0%');
    expect(percent(0.006)).toBe('1%');
  });
});
