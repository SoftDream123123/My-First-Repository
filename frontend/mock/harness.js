/**
 * mock/harness.js —— 浏览器端 Mock 联调台的公共脚手架
 *
 * 为什么不是 jsdom：module-07 §8.1 明确「不引入 DOM 测试框架」，而页面模块的
 * 价值恰恰在 DOM 行为 —— 二次确认、字段级报错、按钮禁用、重定向。
 * 这里让**页面里的真实代码**跑在真浏览器里，只把 `window.fetch` 换成假后端，
 * 既不新增依赖，又比手工点一遍可靠（每次改动都能重跑）。
 *
 * 每个测试台把结果渲染到右上角面板，并写进 `document.title`
 * （`MOCK-ALL-PASS n` / `MOCK-FAIL n/m`），因此无头浏览器也能直接抓结果：
 *
 *   msedge --headless=new --virtual-time-budget=30000 \
 *     --dump-dom http://localhost:5173/mock/auth-harness.html
 */

/* ==========================================================================
   1. 假后端 —— 拦截 fetch，按「METHOD 路径」返回预设响应
   ========================================================================== */

/**
 * @param {Record<string, Function>} defaults 默认处理器：`'GET /users': ({path, body}) => ({status, body})`
 * 支持 `:id` 这类占位段。未命中的路由返回 404 + 一个能指出漏了哪条的 message。
 *
 * 处理器还可以返回 `{ status, stream: '<原始 SSE 报文>' , chunkSize }` —— 这时
 * 响应体会是一个真的 `ReadableStream` 替身，逐块吐出那段文本。
 * **`chunkSize` 可以刻意调小**（例如 5），用来逼出「一条事件被切成两半」的
 * 跨块缓冲问题 —— 那是 SSE 解析里最容易错、也最难靠肉眼发现的地方。
 */
export function installFakeBackend(defaults = {}) {
  const state = { handlers: defaults, calls: [] };

  function resolve(method, path) {
    const exact = state.handlers[`${method} ${path}`];
    if (exact) return exact;

    for (const [key, handler] of Object.entries(state.handlers)) {
      const [keyMethod, pattern] = key.split(' ');
      if (keyMethod !== method) continue;

      const patternParts = pattern.split('/').filter(Boolean);
      const pathParts = path.split('/').filter(Boolean);
      if (patternParts.length !== pathParts.length) continue;

      if (patternParts.every((part, i) => part.startsWith(':') || part === pathParts[i])) {
        return handler;
      }
    }
    return null;
  }

  window.fetch = async (url, options = {}) => {
    const method = (options.method || 'GET').toUpperCase();
    // 保留 query（岗位搜索靠它），但把基址去掉
    const raw = String(url).replace(/^\/api/, '');
    const [path, query = ''] = raw.split('?');
    // FormData（文件上传）必须原样传出：`JSON.parse` 收到 "[object FormData]"
    // 会抛错，把整个假后端打挂。处理器可以用 `body.get('file')` 取文件。
    const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const body = options.body === undefined
      ? undefined
      : isForm ? options.body : JSON.parse(options.body);
    const headers = options.headers || {};

    state.calls.push({ method, path, query, body, auth: headers.Authorization ?? null });

    const handler = resolve(method, path);
    const result = handler
      ? handler({ method, path, query, body })
      : { status: 404, body: { code: 'NOT_FOUND', message: `未 mock 的路由：${method} ${path}`, detail: null } };

    // 处理器可以返回 `delay: <ms>`。用来把「先发的请求后返回」做成**确定状态**
    // 而不是撞运气 —— 迟到的响应覆盖新结果这类竞态，只有能控制返回顺序才测得到。
    // 注意 `state.calls` 已在上面按**发出顺序**记录，延迟不改变调用流水。
    if (result.delay) await new Promise((resolve) => setTimeout(resolve, result.delay));

    return {
      ok: result.status >= 200 && result.status < 300,
      status: result.status,
      headers: {
        get: (name) => (result.headers ?? {})[name] ?? (result.headers ?? {})[name.toLowerCase()] ?? null,
      },
      // SSE：把预置报文切成若干块吐出来，驱动真实的流式读取循环
      body: result.stream === undefined
        ? null
        : streamOf(result.stream, result.chunkSize ?? 17, result.hold === true),
      async json() {
        if (result.body === undefined) throw new Error('该响应无 JSON 体');
        return result.body;
      },
      async blob() { return new Blob([result.blob ?? '']); },
    };
  };

  return {
    /** 实时引用：`reset()` 就地清空，因此不要重新赋值这个数组 */
    calls: state.calls,
    defaultHandlers: defaults,
    setHandlers(map) { state.handlers = map; },
    reset(map) {
      state.calls.length = 0;
      if (map) state.handlers = map;
    },
    /** 只取某条请求，找不到返回 undefined */
    find(method, path) { return state.calls.find((c) => c.method === method && c.path === path); },
  };
}

/* ==========================================================================
   1b. SSE 报文 → 可读流替身
   ========================================================================== */

/**
 * 按固定字节数切块，模拟网络分包。
 *
 * `hold` 为真时，报文吐完之后 `read()` **永不落地** —— 模拟「连接还开着、
 * 服务端还在评」。没有它就只能表达「推完即断」，而评估进行中恰恰是
 * 长连接状态，好几个断言（进度计数、阶段文案）必须在这个状态下才测得到。
 */
function streamOf(text, chunkSize, hold) {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  return {
    getReader() {
      return {
        async read() {
          if (offset >= bytes.length) {
            if (hold) return new Promise(() => {}); // 一直开着，什么都不返回
            return { done: true, value: undefined };
          }
          const slice = bytes.slice(offset, Math.min(offset + chunkSize, bytes.length));
          offset += chunkSize;
          return { done: false, value: slice };
        },
      };
    },
  };
}

/** 把一组 `{event, data}` 拼成 SSE 报文。`null` 项用来插心跳注释行。 */
export function sseText(events, { pingEvery = 0 } = {}) {
  const chunks = [];
  events.forEach((item, index) => {
    if (pingEvery && index > 0 && index % pingEvery === 0) chunks.push(': ping');
    if (item === null) { chunks.push(': ping'); return; }
    chunks.push(`event: ${item.event}\ndata: ${JSON.stringify(item.data)}`);
  });
  return `${chunks.join('\n\n')}\n\n`;
}

/* ==========================================================================
   2. 断言与结果面板
   ========================================================================== */

export function createReport(label) {
  const results = [];
  const errors = [];

  window.addEventListener('error', (e) => errors.push(`uncaught: ${e.message}`));
  window.addEventListener('unhandledrejection', (e) => errors.push(`unhandled rejection: ${e.reason}`));

  function check(name, condition, detail = '') {
    // 条件允许传函数（惰性求值）。
    // 必须先判类型再调用 —— `Boolean(函数)` 恒为 true，
    // 直接 Boolean(condition) 会让惰性条件的断言**永远通过**（踩过一次）。
    //
    // 断言体里抛错（例如 `nodes[0].querySelector` 撞上空数组）**记为失败而不是中断**：
    // 中断会让后面所有断言都不再执行，报告只留下前几条 ——
    // 那正是「出问题时最需要看全」的时候。
    let pass = false;
    let note = String(detail);
    try {
      pass = Boolean(typeof condition === 'function' ? condition() : condition);
    } catch (error) {
      note = `断言抛错：${error?.message ?? error}`;
    }
    results.push({ name, pass, detail: note });
  }

  function paint() {
    const passed = results.filter((r) => r.pass).length;
    const failed = results.length - passed;

    const head = document.createElement('h1');
    head.textContent = `${label}：${passed} 通过 / ${failed} 失败`;
    head.className = failed === 0 && !errors.length ? 'ok' : 'bad';

    const table = document.createElement('table');
    table.className = 'report';
    for (const r of results) {
      const tr = document.createElement('tr');
      tr.className = r.pass ? 'pass' : 'fail';
      const tag = document.createElement('td');
      tag.textContent = r.pass ? 'PASS' : 'FAIL';
      const name = document.createElement('td');
      name.textContent = r.name;
      const detail = document.createElement('td');
      detail.textContent = r.detail;
      tr.append(tag, name, detail);
      table.append(tr);
    }

    const box = document.getElementById('results');
    box.replaceChildren(head, table);
    if (errors.length) {
      const pre = document.createElement('pre');
      pre.textContent = errors.join('\n');
      box.append(pre);
    }
    // 供无头浏览器抓取
    document.title = failed === 0 && !errors.length
      ? `MOCK-ALL-PASS ${passed}`
      : `MOCK-FAIL ${failed}/${results.length}`;
  }

  return {
    check,
    errors,
    /** 跑用例，无论成败都出结果面板 —— 中断也要留下现场 */
    async run(body) {
      try {
        await body();
      } catch (error) {
        errors.push(`用例执行中断: ${error?.stack || error}`);
      }
      paint();
    },
  };
}

/* ==========================================================================
   3. DOM 断言用的小工具
   ========================================================================== */

export const settle = () => new Promise((resolve) => setTimeout(resolve, 25));

export function toasts() {
  return [...document.querySelectorAll('.toast')].map((n) => n.textContent.trim());
}
export function clearToasts() {
  document.querySelectorAll('.toast').forEach((node) => node.remove());
}

export function openOverlay() {
  const all = [...document.querySelectorAll('.modal-overlay')];
  return all[all.length - 1] ?? null;
}

export function buttonIn(scope, text) {
  return [...scope.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
}

/** 关掉可能还开着的弹窗（点「取消」，让 confirmModal 的 Promise 正常结束）。 */
export async function closeAnyModal() {
  const overlay = openOverlay();
  if (!overlay) return;
  const cancel = buttonIn(overlay, '取消');
  if (cancel) cancel.click();
  else overlay.remove();
  await settle();
}

/** 弹窗里某个字段下方**已显示**的报错文本；没显示返回 null。 */
export function fieldErrorOf(labelText, scope = openOverlay()) {
  if (!scope) return null;
  const field = [...scope.querySelectorAll('.field')].find(
    (f) => f.querySelector('.field-label')?.textContent.trim() === labelText,
  );
  if (!field) return null;
  const node = field.querySelector('.field-error');
  if (!node || node.hidden) return null;
  return node.textContent.trim();
}

/** 清空某个存储命名空间的登录态（每个用例之间隔离用）。 */
export function clearStorage() {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }
}
