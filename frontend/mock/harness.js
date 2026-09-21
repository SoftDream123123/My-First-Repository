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
    const body = options.body ? JSON.parse(options.body) : undefined;
    const headers = options.headers || {};

    state.calls.push({ method, path, query, body, auth: headers.Authorization ?? null });

    const handler = resolve(method, path);
    const result = handler
      ? handler({ method, path, query, body })
      : { status: 404, body: { code: 'NOT_FOUND', message: `未 mock 的路由：${method} ${path}`, detail: null } };

    return {
      ok: result.status >= 200 && result.status < 300,
      status: result.status,
      headers: {
        get: (name) => (result.headers ?? {})[name] ?? (result.headers ?? {})[name.toLowerCase()] ?? null,
      },
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
    const pass = Boolean(typeof condition === 'function' ? condition() : condition);
    results.push({ name, pass, detail: String(detail) });
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
