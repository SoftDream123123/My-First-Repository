/**
 * SSE 客户端（module-07 §4.3）。
 *
 * 为什么不用浏览器的 EventSource：它无法设置自定义请求头，而本项目的鉴权
 * 完全依赖 Authorization: Bearer。把 JWT 放进 query string 会让令牌进入
 * 服务器访问日志、代理日志与浏览器历史 —— 这是可以避免的泄露面。
 *
 * 解析逻辑抽成纯函数（splitBlocks / parseEventBlock / parseChunk），
 * 因此跨块缓冲这类最易错的逻辑可以脱离 ReadableStream 直接单测（§8.2）。
 */

import { clear, getToken } from './session.js';

const TERMINAL_EVENTS = new Set(['done', 'error']);

/**
 * 纯函数：把缓冲切成完整事件块，返回 [事件块, 剩余缓冲]。
 *
 * 跨块缓冲是最容易写错的地方 —— 尾部不完整时必须原样保留，
 * 与下一个 chunk 拼接后再切分。
 */
export function splitBlocks(buffer) {
  const blocks = [];
  let rest = buffer;

  // 空行对分帧，兼容 \n\n 与 \r\n\r\n
  const separator = /\r?\n\r?\n/;
  let match = separator.exec(rest);

  while (match) {
    blocks.push(rest.slice(0, match.index));
    rest = rest.slice(match.index + match[0].length);
    match = separator.exec(rest);
  }

  return [blocks, rest];
}

/**
 * 纯函数：解析单个事件块。
 * 返回 { name, data } 或 null（注释行 / 空块不产出事件）。
 */
export function parseEventBlock(block) {
  const lines = block.split(/\r?\n/);
  let name = 'message';
  const dataLines = [];

  for (const line of lines) {
    // ':' 开头是注释 —— 心跳走这里，不产出事件
    if (line.startsWith(':')) continue;

    if (line.startsWith('event:')) {
      name = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }

  if (!dataLines.length) return null;

  const raw = dataLines.join('\n');
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    // 畸形 JSON 不该让整个流崩掉
    data = { raw };
  }

  return { name, data };
}

/**
 * 纯函数：把新到的 chunk 并入缓冲，产出**已经完整**的事件。
 *
 * 返回 [events, remaining] —— remaining 是尾部尚未闭合的部分，
 * 必须原样交给下一次调用，否则跨块的事件会丢。
 * sseConnect 的读取循环就是靠它保持"缓冲在循环外、解析在纯函数里"。
 */
export function parseChunk(buffer, chunk) {
  const [blocks, rest] = splitBlocks(buffer + chunk);
  const events = [];

  for (const block of blocks) {
    const event = parseEventBlock(block);
    if (event) events.push(event);
  }

  return [events, rest];
}

/** 建连。返回 { close, isOpen }。 */
export function sseConnect(path, handlers) {
  const controller = new AbortController();
  let open = true;

  const token = getToken();

  fetch(path, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      Accept: 'text/event-stream',
    },
    signal: controller.signal,
  })
    .then(async (response) => {
      if (response.status === 401) {
        clear();
        if (handlers.onUnauthorized) handlers.onUnauthorized();
        return;
      }

      if (!response.ok) {
        throw new Error(`连接失败（${response.status}）`);
      }
      if (!response.body) {
        throw new Error('响应不支持流式读取');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;

        const [events, rest] = parseChunk(buffer, decoder.decode(value, { stream: true }));
        buffer = rest;

        for (const event of events) {
          handlers.onEvent?.(event.name, event.data);
          if (TERMINAL_EVENTS.has(event.name)) {
            open = false;
            handlers.onClose?.();
            return;
          }
        }
      }

      open = false;
      handlers.onClose?.();
    })
    .catch((error) => {
      if (error.name === 'AbortError') return; // 主动关闭不算错误
      open = false;
      // 不自动重连 —— 由页面显式控制，避免无限重试风暴
      handlers.onError?.(error);
    });

  return {
    close() {
      open = false;
      controller.abort();
    },
    isOpen: () => open,
  };
}
