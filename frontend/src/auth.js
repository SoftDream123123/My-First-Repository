/**
 * auth.js —— 登录态语义
 *
 * 已声明的风险：localStorage 里的 token 可被 XSS 读取；本设计通过
 * 「界面无 HTML 注入点 + 全部 textContent 渲染」缓解（见 dom.js）。
 *
 * ⚠️ **角色不缓存在 JWT 里** —— 后端每次请求都回查数据库。admin 把某 HR 提升为
 * 管理员后，对方**用旧 token 即可立即访问** `/api/users`（API 文档 §2.2）。
 * 所以界面上的角色必须靠 `refreshUser()` 刷新，不能只信登录那一刻拿到的值。
 */

import * as api from './api.js';
import * as session from './session.js';

export const saveToken = session.save;
export const getToken = session.getToken;
export const getUser = session.getUser;
export const isLoggedIn = () => Boolean(session.getToken());
export const isAdmin = () => session.getUser()?.role === 'admin';
export const isCandidate = () => session.getUser()?.role === 'candidate';

/**
 * 某一端是否已登录 —— **不依赖当前活动端**。
 *
 * 两端登录态分开存且可能同时存在（PRD §9），因此「进来该去哪」这种决策
 * 必须能同时问两端。实现上借活动端切换一问一答再还原，避免把「按端读」
 * 的口子开到 session 模块之外去。
 */
export function isLoggedInOn(side) {
  const previous = session.getSide();
  session.setSide(side);
  const logged = Boolean(session.getToken());
  session.setSide(previous);
  return logged;
}

/** 某一端的用户是否为 admin（同样不依赖当前活动端）。 */
export function isAdminOn(side) {
  const previous = session.getSide();
  session.setSide(side);
  const admin = isAdmin();
  session.setSide(previous);
  return admin;
}

/** 退出**当前端**，并回到该端的登录页。两端可以同时登录，因此不能两端一起清。 */
export function logout() {
  const side = session.getSide();
  session.clear();
  location.hash = side === 'candidate' ? '#/candidate/login' : '#/login';
}

/** 刷新用户信息，保证角色是最新的（管理员改角色后立即生效）。 */
export async function refreshUser() {
  const user = await api.get('/auth/me');
  session.setUser(user);
  return user;
}
