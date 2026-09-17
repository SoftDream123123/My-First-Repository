/**
 * 登录态存储。
 *
 * 单独成一个模块，是为了打断 api ←→ auth 的循环依赖：
 * `api.js` 需要 token 来注入请求头，而 `auth.js` 需要 api 来刷新用户信息。
 * 存储键只在这一处定义，不会出现"两个文件各写一份、改一处漏一处"。
 */

const TOKEN_KEY = 'hr.token';
const USER_KEY = 'hr.user';

export function save(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clear() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // 手工改坏过 localStorage 时不该让整个应用崩掉
    return null;
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
