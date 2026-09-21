/**
 * 简历表单的纯函数单测。
 *
 * 为什么要抽成纯函数：本工程的**前端测试只能测纯函数**（无 DOM 环境，
 * module-07 §8.1 的既有决策）。把「能否提交」的判定留在 `render()` 里，
 * 就等于**它永远不会被测到** —— 而它错起来很安静：超限判定写反不会报错，
 * 只会让人在点了保存之后吃一个 422。
 *
 * 最后一条（常量守门）是刻意的：前端无法 import 后端配置，20000 只能各写一份。
 * 用一条断言把「值是 20000」钉住，至少让改动成为一个**需要显式修改测试的动作**，
 * 而不是静默漂移。
 */

import { describe, expect, it } from 'vitest';
import {
  RESUME_CONTENT_MAX_LENGTH, canSubmitResume, contentLengthState,
} from '../pages/candidate-resumes.js';

const ok = { title: '后端开发 · 主投版', content: '教育经历…' };

describe('canSubmitResume —— 能否提交', () => {
  it('标题为空白 → false', () => {
    expect(canSubmitResume({ ...ok, title: '' })).toBe(false);
    expect(canSubmitResume({ ...ok, title: '   ' })).toBe(false);
  });

  it('正文为空白 → false', () => {
    expect(canSubmitResume({ ...ok, content: '' })).toBe(false);
    expect(canSubmitResume({ ...ok, content: ' \n\t ' })).toBe(false);
  });

  it('标题 / 正文前后空白不影响判定（先 trim 再判空）', () => {
    expect(canSubmitResume({ title: '  标题  ', content: '  正文  ' })).toBe(true);
  });

  it('正文长度**恰好**是上限 → true（边界取闭区间）', () => {
    expect(canSubmitResume({ ...ok, content: 'a'.repeat(RESUME_CONTENT_MAX_LENGTH) })).toBe(true);
  });

  it('正文长度上限 + 1 → false', () => {
    expect(canSubmitResume({ ...ok, content: 'a'.repeat(RESUME_CONTENT_MAX_LENGTH + 1) })).toBe(false);
  });

  it('姓名 / 联系方式为空 → 仍然 true（它们是可选字段）', () => {
    expect(canSubmitResume({ ...ok, candidate_name: '', candidate_contact: '' })).toBe(true);
    expect(canSubmitResume(ok)).toBe(true);
  });

  it('缺字段 / null 不抛异常', () => {
    expect(canSubmitResume({})).toBe(false);
    expect(canSubmitResume({ title: null, content: null })).toBe(false);
  });

  it('上限可以覆盖（判定不写死 20000）', () => {
    expect(canSubmitResume({ title: 't', content: 'abcd', maxLength: 3 })).toBe(false);
    expect(canSubmitResume({ title: 't', content: 'abc', maxLength: 3 })).toBe(true);
  });
});

describe('contentLengthState —— 字数计数', () => {
  it('length 等于 content.length，**不做去空白**（计数要反映用户看到的长度）', () => {
    expect(contentLengthState('  三个空格加内容  ').length).toBe('  三个空格加内容  '.length);
  });

  it('恰好到上限时 over 为 false', () => {
    expect(contentLengthState('a'.repeat(RESUME_CONTENT_MAX_LENGTH)).over).toBe(false);
  });

  it('超限时 over 为 true', () => {
    expect(contentLengthState('a'.repeat(RESUME_CONTENT_MAX_LENGTH + 1)).over).toBe(true);
  });

  it('空内容 → 0 / 未超限', () => {
    expect(contentLengthState('')).toEqual({ length: 0, over: false });
    expect(contentLengthState(null)).toEqual({ length: 0, over: false });
  });
});

describe('RESUME_CONTENT_MAX_LENGTH —— 与后端对齐的守门断言', () => {
  it('常量等于 20000', () => {
    // 与后端 `RESUME_CONTENT_MAX_LENGTH` 一致。改了这里，后端那边必须同时改
    expect(RESUME_CONTENT_MAX_LENGTH).toBe(20000);
  });
});
