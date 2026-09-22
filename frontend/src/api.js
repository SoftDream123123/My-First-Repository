/**
 * api.js —— HTTP 封装
 *
 *   2xx     → 解析后的 JSON；204 返回 null
 *   非 2xx  → 响应体是 {code, message, detail} 就原样抛出（文案来自后端，
 *             前端不重新编造）；不是该形状时用 HTTP 状态兜底
 *   401     → 清 token、触发注入的回调，同时抛出
 *   网络不可达 → NETWORK_ERROR
 *
 * ⚠️ **不是所有 401 都等于「登录态失效」**。三个公开端点自己就会返回 401：
 * `/auth/login` 的「用户名或密码错误」、`/candidate/invitations/{code}/accept`
 * 复用已有账号时的密码不符。把它们当成会话失效会把人**误登出**，
 * 而且真正的错误文案会被那一句「登录状态已失效」盖掉。
 *
 * 路径一律用相对地址 `/api/...`：开发期走 Vite 代理、部署期由后端同源托管，
 * 两种环境都不需要处理 CORS（API 文档 §1.1）。
 */

import * as session from './session.js';
import { parseChunk } from './sse.js';

const BASE = '/api';
const NETWORK_MESSAGE = '网络连接失败，请检查后端服务';

export class ApiError extends Error {
  constructor({ code = 'UNKNOWN', message, detail = null, status = 0 }) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
    this.status = status;
  }
}

/** 这两个端点的 401 是「凭据不符」，不是「会话失效」。 */
function isCredentialCheck(path) {
  return path === '/auth/login' || /^\/candidate\/invitations\/[^/]+\/accept$/.test(path);
}

let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) { unauthorizedHandler = fn; }

export async function request(method, path, body) {
  const token = session.getToken();
  // FormData 走 multipart：**不能**手工设 Content-Type —— 浏览器要自己带上
  // `multipart/form-data; boundary=…`，写死会丢掉 boundary，后端一个字段也收不到。
  const isForm = body instanceof FormData;
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: {
        ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError({ code: 'NETWORK_ERROR', message: NETWORK_MESSAGE });
  }

  // 204 无响应体：对该状态码调 response.json() 会抛错（API 文档 §6.5）
  if (response.status === 204) return null;

  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (response.ok) return payload;

  // 只有「带着 token 去了一个非凭据端点」才是会话失效。
  // 拼错路径的 404 由 Starlette 直接返回 {"detail": "Not Found"}（无 code 字段），
  // 下面 shaped 判定会兜住它，不会在拦截器里炸掉。
  if (response.status === 401 && token && !isCredentialCheck(path)) {
    session.clear();
    if (unauthorizedHandler) unauthorizedHandler();
  }

  const shaped = payload && typeof payload.code === 'string' && 'message' in payload;
  throw new ApiError(
    shaped
      ? { ...payload, status: response.status }
      : { code: 'UNKNOWN', message: `请求失败（${response.status}）`, status: response.status },
  );
}

export const get = (path) => request('GET', path);
export const post = (path, body) => request('POST', path, body);
export const put = (path, body) => request('PUT', path, body);
export const patch = (path, body) => request('PATCH', path, body);
export const del = (path) => request('DELETE', path);

/**
 * 发一个 `multipart/form-data`（文件上传）。
 *
 * 只有这一个方法支持 FormData，**不扩散到 put / patch**：将来真需要再开，
 * 现在多开等于给每个方法留一条无人测试的路径。
 *
 * 走 `request` 内部那个分支而不是另写一份 fetch，是为了**继承**它那套不能
 * 复制的逻辑：网络错误归一化、204 处理、`ApiError` 三字段包装、401 拦截器。
 */
export const postForm = (path, formData) => request('POST', path, formData);

/**
 * 尽力送达的 POST —— 用在页面**正在被卸载**时（`pagehide`）保存还没落盘的作答。
 *
 * `keepalive: true` 让浏览器在文档卸载后仍把这个请求发完，这是卸载路径上唯一
 * 能把写入真的送到服务端的手段：那里 await 不到结果，普通 `fetch` 会被中断。
 *
 * 为什么不用 `sendBeacon`：它**带不了自定义请求头**，而这个 API 需要
 * `Authorization: Bearer`。载荷上限（本端点作答 ≤ 10000 字符）也远低于
 * keepalive 的 64KB 限额。
 *
 * 没有返回值 —— 调用方处在卸载路径上，既等不到结果，也不该在这里报错。
 */
export function postKeepalive(path, body) {
  const token = session.getToken();
  try {
    fetch(BASE + path, {
      method: 'POST',
      keepalive: true,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    }).catch(() => {});
  } catch {
    // 卸载中不做任何处理
  }
}

/* ==========================================================================
   SSE 流式读取
   ========================================================================== */

/**
 * 读一条 SSE 流。**不用 `EventSource`** —— 它带不了 `Authorization` 头，
 * 而这个端点需要 JWT（API 文档 §15.2）。
 *
 * 分帧与解析在 `sse.js`（纯函数、有单测）；这里只负责连接、解码与回调。
 *
 * ⚠️ **重连会从头重放**（API 文档 §9.2 明说的设计特性，不是缺陷）：
 * 调用方累加进度时必须**按 id/维度覆盖**而不是追加，否则刷新一次进度就翻倍。
 */
export async function stream(path, { onEvent, signal } = {}) {
  const token = session.getToken();
  let response;
  try {
    response = await fetch(BASE + path, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error; // 主动断开不算错误
    throw new ApiError({ code: 'NETWORK_ERROR', message: NETWORK_MESSAGE });
  }

  if (!response.ok) {
    // 403 / 404 在这里就结束：响应根本不是 event-stream，页面拿到的是一个正常错误
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    const shaped = payload && typeof payload.code === 'string' && 'message' in payload;
    throw new ApiError(shaped
      ? { ...payload, status: response.status }
      : { code: 'UNKNOWN', message: `请求失败（${response.status}）`, status: response.status });
  }
  if (!response.body) {
    throw new ApiError({ code: 'STREAM_UNAVAILABLE', message: '当前浏览器不支持流式响应' });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;

    const [events, rest] = parseChunk(buffer, decoder.decode(value, { stream: true }));
    buffer = rest;
    for (const event of events) onEvent(event);
  }
}

/* ==========================================================================
   下载后端生成的文件
   ========================================================================== */

/**
 * 纯函数：从 `Content-Disposition` 里取文件名。
 *
 * 中文名走 RFC 5987 的 `filename*=UTF-8''…`，`filename=` 只留 ASCII 兜底，
 * 因此**优先取 `filename*`**，都取不到时由调用方给一个本地名字。
 */
export function parseContentDisposition(header) {
  const value = String(header ?? '');
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(value);
  if (utf8) {
    try { return decodeURIComponent(utf8[1]); } catch { return null; }
  }
  const plain = /filename="?([^";]+)"?/i.exec(value);
  return plain ? plain[1] : null;
}

/**
 * 下载二进制响应（报告 DOCX）。
 *
 * 不能直接用 `<a href>` —— 那个带不上 JWT，会拿回一个 401（API 文档 §9.4）。
 */
export async function download(path, fallbackName) {
  const token = session.getToken();
  let response;
  try {
    response = await fetch(BASE + path, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    throw new ApiError({ code: 'NETWORK_ERROR', message: NETWORK_MESSAGE });
  }

  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    const shaped = payload && typeof payload.code === 'string' && 'message' in payload;
    throw new ApiError(shaped
      ? { ...payload, status: response.status }
      : { code: 'UNKNOWN', message: `导出失败（${response.status}）`, status: response.status });
  }

  const filename = parseContentDisposition(response.headers.get('Content-Disposition')) || fallbackName;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  // 立刻 revoke 会让部分浏览器来不及取数据，等一拍再释放
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return filename;
}
