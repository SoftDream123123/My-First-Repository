/**
 * 登录态（module-07 §4.2）。
 *
 * 用 localStorage：刷新与跨标签保持登录，实现最简单。
 * 已声明的风险 —— localStorage 里的 token 可被 XSS 读取；本设计通过
 * "界面无 HTML 注入点 + 全部 textContent 渲染" 缓解（见 dom.js）。
 */

import * as api from './api.js';

const TOKEN_KEY = 'prototype.token';
const USER_KEY = 'prototype.user';

export function saveToken(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isLoggedIn() {
  return Boolean(getToken());
}

export function isAdmin() {
  return getUser()?.role === 'admin';
}

export function logout() {
  api.clearToken();
  location.hash = '#/login';
}

/** 刷新用户信息，保证角色是最新的（管理员改角色后立即生效）。 */
export async function refreshUser() {
  const user = await api.get('/auth/me');
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  return user;
}
