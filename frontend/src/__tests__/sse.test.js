/**
 * SSE 分帧解析单测（module-07 §8.2）。
 *
 * 被测对象是三个纯函数 —— 不需要真实 ReadableStream，也不需要 DOM。
 * 跨块缓冲（事件被 TCP 切成两半）是最容易写错的地方，因此占了 4 条用例。
 */

import { describe, expect, it } from 'vitest';

import { parseChunk, parseEventBlock, splitBlocks } from '../sse.js';

/** 把一串 chunk 依次喂进解析器，模拟 sseConnect 的读取循环。 */
function feed(chunks) {
  let buffer = '';
  const events = [];

  for (const chunk of chunks) {
    const [parsed, rest] = parseChunk(buffer, chunk);
    buffer = rest;
    events.push(...parsed);
  }

  return { events, pending: buffer };
}

describe('splitBlocks', () => {
  it('按空行分帧，尾部不完整时原样保留', () => {
    const [blocks, rest] = splitBlocks('event: a\ndata: 1\n\nevent: b\ndata: 2\n\npartial');

    expect(blocks).toEqual(['event: a\ndata: 1', 'event: b\ndata: 2']);
    expect(rest).toBe('partial');
  });

  it('\\r\\n\\r\\n 同样能分帧', () => {
    const [blocks, rest] = splitBlocks('event: a\r\ndata: 1\r\n\r\n');

    expect(blocks).toEqual(['event: a\r\ndata: 1']);
    expect(rest).toBe('');
  });
});

describe('parseEventBlock', () => {
  it('解析事件名与 data', () => {
    expect(parseEventBlock('event: question\ndata: {"score":7}')).toEqual({
      name: 'question',
      data: { score: 7 },
    });
  });

  it('没有 event 行时事件名缺省为 message', () => {
    expect(parseEventBlock('data: {"a":1}').name).toBe('message');
  });

  it('多行 data 按换行拼接后解析', () => {
    const block = 'event: report\ndata: {"a":\ndata: 1}';

    expect(parseEventBlock(block)).toEqual({ name: 'report', data: { a: 1 } });
  });

  it('以 : 开头的注释行（心跳）不产出事件', () => {
    expect(parseEventBlock(': ping')).toBeNull();
    expect(parseEventBlock(': ping\n: keep-alive')).toBeNull();
  });

  it('畸形 JSON 不抛异常，按原文兜底', () => {
    expect(() => parseEventBlock('data: not-json')).not.toThrow();
    expect(parseEventBlock('data: not-json')).toEqual({
      name: 'message',
      data: { raw: 'not-json' },
    });
  });

  it('没有 data 行的块不产出事件', () => {
    expect(parseEventBlock('event: question')).toBeNull();
    expect(parseEventBlock('')).toBeNull();
  });
});

describe('parseChunk（含跨块缓冲）', () => {
  it('单个完整事件', () => {
    const { events, pending } = feed(['event: question\ndata: {"a":1}\n\n']);

    expect(events).toEqual([{ name: 'question', data: { a: 1 } }]);
    expect(pending).toBe('');
  });

  it('一个 chunk 里的多个事件全部产出', () => {
    const { events } = feed(['event: a\ndata: 1\n\nevent: b\ndata: 2\n\n']);

    expect(events.map((e) => e.name)).toEqual(['a', 'b']);
    expect(events.map((e) => e.data)).toEqual([1, 2]);
  });

  it('事件被切成两个 chunk —— 拼接后正确解析（跨块缓冲）', () => {
    const { events, pending } = feed(['event: quest', 'ion\ndata: {"score":8.5}\n\n']);

    expect(events).toEqual([{ name: 'question', data: { score: 8.5 } }]);
    expect(pending).toBe('');
  });

  it('切在 JSON 中间也不丢数据', () => {
    const { events } = feed(['event: question\ndata: {"dim', 'ension":"沟通能力"}\n\n']);

    expect(events).toEqual([{ name: 'question', data: { dimension: '沟通能力' } }]);
  });

  it('切在空行中间（\\n + \\n）也能正确分帧', () => {
    const { events, pending } = feed(['event: a\ndata: 1\n', '\n']);

    expect(events).toEqual([{ name: 'a', data: 1 }]);
    expect(pending).toBe('');
  });

  it('尾部不完整时暂存，不提前产出事件', () => {
    const { events, pending } = feed(['event: question\ndata: {"score":7.0}']);

    expect(events).toEqual([]);
    expect(pending).toBe('event: question\ndata: {"score":7.0}');
  });

  it('空 chunk 不产出事件', () => {
    expect(feed(['']).events).toEqual([]);
    expect(feed(['\n\n']).events).toEqual([]);
  });

  it('心跳注释夹在事件之间被忽略，不影响其余事件', () => {
    const { events } = feed([': ping\n\nevent: done\ndata: {"status":"evaluated"}\n\n']);

    expect(events).toEqual([{ name: 'done', data: { status: 'evaluated' } }]);
  });

  it('逐字节喂入也能还原完整事件', () => {
    const payload = 'event: question\ndata: {"seq":3}\n\n';
    const { events } = feed(payload.split(''));

    expect(events).toEqual([{ name: 'question', data: { seq: 3 } }]);
  });
});
