/**
 * 登录态（module-07 §4.2）。
 *
 * 用 localStorage：刷新与跨标签保持登录，实现最简单。
 * 已声明的风险 —— localStorage 里的 token 可被 XSS 读取；本设计通过
 * 「界面无 HTML 注入点 + 全部 textContent 渲染」缓解（见 dom.js）。
 * 若将来面向公网，应迁移到 httpOnly Cookie + CSRF 防护。
 */

import * as api from './api.js';
import * as session from './session.js';

export const saveToken = session.save;
export const getToken = session.getToken;
export const getUser = session.getUser;

export function isLoggedIn() {
  return Boolean(session.getToken());
}

export function isAdmin() {
  return session.getUser()?.role === 'admin';
}

export function logout() {
  session.clear();
  location.hash = '#/login';
}

/** 刷新用户信息，保证角色是最新的（管理员改角色后立即生效）。 */
export async function refreshUser() {
  const user = await api.get('/auth/me');
  session.setUser(user);
  return user;
}
