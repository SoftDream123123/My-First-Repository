/**
 * SSE 解析的纯函数单测。
 *
 * 为什么值得单独测：**跨块缓冲与心跳注释**这两件事的错法都不显眼 ——
 * 尾包没留住会让某一条事件永远丢，心跳没忽略会让页面每次 ping 都报一次错。
 * 两种都表现为「有时候会少一条 / 闪一下」，靠肉眼几乎定位不到。
 */

import { describe, expect, it } from 'vitest';
import { parseChunk, parseEventBlock, splitBlocks } from '../sse.js';

describe('splitBlocks', () => {
  it('切出完整块，尾部不完整的原样留作剩余', () => {
    const [blocks, rest] = splitBlocks('event: a\ndata: 1\n\nevent: b\ndata: 2');
    expect(blocks).toEqual(['event: a\ndata: 1']);
    expect(rest).toBe('event: b\ndata: 2');
  });

  it('兼容 \\r\\n\\r\\n 分帧', () => {
    const [blocks, rest] = splitBlocks('event: a\r\ndata: 1\r\n\r\n');
    expect(blocks).toEqual(['event: a\r\ndata: 1']);
    expect(rest).toBe('');
  });

  it('没有空行时一个块都不产出', () => {
    const [blocks, rest] = splitBlocks('event: a\ndata: 1');
    expect(blocks).toEqual([]);
    expect(rest).toBe('event: a\ndata: 1');
  });

  it('一次切出多个块', () => {
    const [blocks] = splitBlocks('a\n\nb\n\nc\n\n');
    expect(blocks).toEqual(['a', 'b', 'c']);
  });
});

describe('parseEventBlock', () => {
  it('解析出事件名与 JSON 数据', () => {
    expect(parseEventBlock('event: question\ndata: {"seq":1}'))
      .toEqual({ name: 'question', data: { seq: 1 } });
  });

  it('没有 event 行时名字回落成 message', () => {
    expect(parseEventBlock('data: {"a":1}')).toEqual({ name: 'message', data: { a: 1 } });
  });

  it('**心跳是注释行，必须静默丢弃**', () => {
    // 后端每 15 秒推一行 `: ping` —— 它没有 data 行，不能产出事件
    expect(parseEventBlock(': ping')).toBeNull();
    expect(parseEventBlock(': ping\n: keep-alive')).toBeNull();
  });

  it('注释与事件混在一起时，注释被忽略、事件照常解析', () => {
    expect(parseEventBlock(': ping\nevent: done\ndata: {"status":"evaluated"}'))
      .toEqual({ name: 'done', data: { status: 'evaluated' } });
  });

  it('没有 data 行不产出事件', () => {
    expect(parseEventBlock('event: question')).toBeNull();
    expect(parseEventBlock('')).toBeNull();
  });

  it('多行 data 用换行连接后再解析', () => {
    expect(parseEventBlock('data: {"a":\ndata: 1}')).toEqual({ name: 'message', data: { a: 1 } });
  });

  it('畸形 JSON 不让整条流崩掉，原文照带出来', () => {
    expect(parseEventBlock('data: {半截')).toEqual({ name: 'message', data: { raw: '{半截' } });
  });

  it('只吃掉 data: 后的一个前导空格（规范如此）', () => {
    expect(parseEventBlock('data:  {"a":1}')).toEqual({ name: 'message', data: { a: 1 } });
  });

  it('事件名两侧的空白被去掉', () => {
    expect(parseEventBlock('event:  done \ndata: 1')).toEqual({ name: 'done', data: 1 });
  });
});

describe('parseChunk —— 跨块缓冲', () => {
  it('事件被切成两半时，第一半不产出任何东西', () => {
    const [events1, rest1] = parseChunk('', 'event: question\ndata: {"seq"');
    expect(events1).toEqual([]);

    const [events2] = parseChunk(rest1, ':1}\n\n');
    expect(events2).toEqual([{ name: 'question', data: { seq: 1 } }]);
  });

  it('逐字节喂入也能拼出完整事件', () => {
    const raw = 'event: done\ndata: {"status":"evaluated"}\n\n';
    let buffer = '';
    const seen = [];
    for (const char of raw) {
      const [events, rest] = parseChunk(buffer, char);
      buffer = rest;
      seen.push(...events);
    }
    expect(seen).toEqual([{ name: 'done', data: { status: 'evaluated' } }]);
    expect(buffer).toBe('');
  });

  it('一个 chunk 里的多条事件全部产出', () => {
    const [events] = parseChunk('', 'event: question\ndata: 1\n\nevent: question\ndata: 2\n\n');
    expect(events.map((e) => e.data)).toEqual([1, 2]);
  });

  it('心跳夹在两条事件中间，不产出事件也不打断缓冲', () => {
    const raw = 'event: question\ndata: 1\n\n: ping\n\nevent: question\ndata: 2\n\n';
    const [events, rest] = parseChunk('', raw);
    expect(events.map((e) => e.data)).toEqual([1, 2]);
    expect(rest).toBe('');
  });
});
