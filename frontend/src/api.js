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
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
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
