/**
 * HTTP 封装（module-07 §4.1）。
 *
 * 只有真实后端一条路径 —— 原型期的内存 mock 已移除。页面代码自始至终按真实
 * 契约书写，因此这次切换没有改动任何一个页面。
 *
 * 行为与 API 文档 §1.3 / §1.4 逐条对应：
 *   2xx        → 解析后的 JSON；204 无响应体（岗位 / 题目删除）返回 null
 *   非 2xx     → 响应体是 {code, message, detail} 就原样抛出 ——
 *                文案来自后端，前端不重新编造
 *                响应体不是该形状时用 HTTP 状态兜底
 *   401        → 清 token、触发注入的回调（跳登录），同时抛出
 *   网络不可达  → NETWORK_ERROR
 */

import { clear, getToken } from './session.js';

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

let unauthorizedHandler = null;

/** 由 main.js 注入「清 token + 跳登录」。页面不必各自处理 401。 */
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

export async function request(method, path, body) {
  const token = getToken();

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

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (response.ok) return payload;

  // 会话失效 ≠ 认证失败，两者都返回 401，必须分开处理：
  //   · /auth/login 的 401 表示"用户名或密码错误" —— 由登录表单自己提示，
  //     若也走统一处理，会在登录页上再弹一条「登录状态已失效」，两条文案打架。
  //   · 其余接口只有在**确实带了 token** 时才说明会话失效（被禁用 / 过期 / 篡改）；
  //     没带 token 的 401 属于调用方问题，不该清掉会话。
  const credentialsRejected = path === '/auth/login';
  if (response.status === 401 && !credentialsRejected && token) {
    clear();
    if (unauthorizedHandler) unauthorizedHandler();
  }

  const shaped = payload && typeof payload.code === 'string' && 'message' in payload;

  throw new ApiError(
    shaped
      ? { ...payload, status: response.status }
      : {
          code: 'UNKNOWN',
          message: `请求失败（${response.status}）`,
          status: response.status,
        },
  );
}

export const get = (path) => request('GET', path);
export const post = (path, body) => request('POST', path, body);
export const put = (path, body) => request('PUT', path, body);
export const patch = (path, body) => request('PATCH', path, body);
export const del = (path) => request('DELETE', path);
