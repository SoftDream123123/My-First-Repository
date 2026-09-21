/**
 * sse.js —— SSE 报文的纯解析
 *
 * **为什么不用浏览器的 `EventSource`**：它无法设置自定义请求头，而本项目的鉴权
 * 完全依赖 `Authorization: Bearer`。把 JWT 放进 query string 会让令牌进入
 * 服务器访问日志、代理日志与浏览器历史 —— 这是可以避免的泄露面。
 *
 * 这里**只放纯函数**，不碰 fetch / session：跨块缓冲是整条链路里最容易写错的
 * 一环（尾包不完整时必须原样留着与下一块拼接），把它与 I/O 分开，就能脱离
 * `ReadableStream` 直接单测（`src/__tests__/sse.test.js`）。
 * 真正的连接循环在 `api.js` 的 `stream()`。
 */

/**
 * 纯函数：把缓冲切成完整的事件块，返回 `[事件块数组, 剩余缓冲]`。
 *
 * 空行对分帧，兼容 `\n\n` 与 `\r\n\r\n`。**尾部不完整时必须原样保留** ——
 * 直接丢弃会让跨块的事件永远拼不回来。
 */
export function splitBlocks(buffer) {
  const blocks = [];
  let rest = buffer;

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
 * 纯函数：解析单个事件块，返回 `{ name, data }` 或 null。
 *
 * `:` 开头的行是注释 —— **心跳走的就是这条**（`data: ` 不出现），
 * 因此注释块必须静默丢弃，不能产出事件。
 */
export function parseEventBlock(block) {
  const lines = block.split(/\r?\n/);
  let name = 'message';
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith(':')) continue;

    if (line.startsWith('event:')) {
      name = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      // 规范只吃掉一个前导空格
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }

  if (!dataLines.length) return null;

  const raw = dataLines.join('\n');
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    // 畸形 JSON 不该让整条流崩掉 —— 半截报文照原样带出来，调用方自行忽略
    data = { raw };
  }

  return { name, data };
}

/**
 * 纯函数：把新到的 chunk 并入缓冲，产出**已经完整**的事件。
 *
 * 返回 `[events, remaining]`。`remaining` 是尾部尚未闭合的部分，
 * 必须原样交给下一次调用。
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

/** 终结事件：流到这两个之一就该收尾，不会再有下文。 */
export const TERMINAL_EVENTS = new Set(['done', 'error']);
