/**
 * session.js —— 登录态存储
 *
 * 单独成模块是为了打断 api ←→ auth 的循环依赖（api 要 token，auth 要 api）。
 *
 * 存储键**按端分命名空间**（`hr.*` / `candidate.*`）：同一 origin 下两端可以
 * 同时保持登录，互不顶号（PRD §9）。当前活动端由 router 在每次路由解析时
 * 设置（`setSide`），因此「取 token」不需要每个调用点都传一遍端。
 *
 * 出错的读操作必须能兜住：手工改坏过 localStorage、或浏览器禁用它，
 * 都不该让整个应用崩掉。
 */

let activeSide = 'hr';

function keys() {
  return activeSide === 'candidate'
    ? { token: 'candidate.token', user: 'candidate.user' }
    : { token: 'hr.token', user: 'hr.user' };
}

export function setSide(side) { activeSide = side === 'candidate' ? 'candidate' : 'hr'; }
export function getSide() { return activeSide; }

export function save(token, user) {
  const k = keys();
  try { localStorage.setItem(k.token, token); } catch { /* 存不下就只保留本次会话 */ }
  try { localStorage.setItem(k.user, JSON.stringify(user)); } catch { /* 同上 */ }
}

export function clear() {
  const k = keys();
  try { localStorage.removeItem(k.token); } catch { /* 忽略 */ }
  try { localStorage.removeItem(k.user); } catch { /* 忽略 */ }
}

export function getToken() {
  try { return localStorage.getItem(keys().token); } catch { return null; }
}

export function getUser() {
  try {
    const raw = localStorage.getItem(keys().user);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null; // 存储被改坏时不该让整个应用崩掉
  }
}

export function setUser(user) {
  try { localStorage.setItem(keys().user, JSON.stringify(user)); } catch { /* 忽略 */ }
}
