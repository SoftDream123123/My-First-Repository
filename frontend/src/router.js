/**
 * router.js —— hash 路由 + 导航守卫
 *
 * 路由带 `side` 字段（hr / candidate）。端的解析与守卫决策都在这里，
 * 页面本身不关心自己属于哪一端。
 *
 * **守卫决策是纯函数**（`decide` / `defaultRoute` / `entryRoute`）：
 * 它们不碰 location、不碰 localStorage，因此能被 Vitest 直接测
 * （`src/__tests__/router.test.js`）。副作用集中在 `guard()` 这一个薄壳里。
 */

import * as auth from './auth.js';
import * as session from './session.js';
import { toast } from './components/toast.js';

/**
 * 路由表。
 *   side     属于哪一端（hr / candidate）。导航与默认页都按端过滤
 *   nav      出现在侧栏导航上的名字（无 nav 即不进导航，但地址仍可直接访问）
 *   isPublic 未登录可达
 *   open     **登录与否都可达、且不做重定向** —— 激活页要这样：
 *            没账号时凭码建号，已有账号时凭码绑定（PRD §4.1）。
 *            只标 isPublic 会让已登录的人被弹走，只标登录可达则新人进不来。
 *
 * ⚠️ **每个路由都必须有对应页面**：漏注册的表现是**报错**，不安静地落到
 * 别的页面把问题藏起来。因此这张表**只列已落地的页面** —— 尚未实现的模块
 * （题库、面试、评估、候选人端）在它们各自的模块里把行加进来，
 * 而不是先摆一行点进去报错的路由。
 *
 * ⚠️ **顺序即默认落地页的优先级**：`defaultRoute()` 取本端第一个带 nav 的路由。
 * 因此 `/interviews` 排在最前（HR 的日常入口），而 adminOnly 的 `/users` 排在最后 ——
 * 它排在前面会让 HR 角色登录后无页可去。
 */
export const routes = [
  { path: '/login',            key: 'login',           side: 'hr', isPublic: true },
  // 「面试」排在首位：它是 HR 每天打开应用要看的那一屏（「这场该我做什么」），
  // 也是本端的默认落地页。岗位与题库是备料，不是日常入口。
  { path: '/interviews',       key: 'interviews',      side: 'hr', nav: '面试' },
  { path: '/interviews/:id',   key: 'interviewDetail', side: 'hr' },
  { path: '/interviews/:id/evaluation', key: 'evaluation', side: 'hr' },
  { path: '/positions',        key: 'positions',       side: 'hr', nav: '岗位' },
  { path: '/questions',        key: 'questions',       side: 'hr', nav: '题库' },
  { path: '/users',            key: 'users',           side: 'hr', nav: '用户管理', adminOnly: true },
];

const LOGIN_BY_SIDE = { hr: '/login', candidate: '/candidate/login' };

const isRegistered = (path) => routes.some((route) => route.path === path);

/**
 * 某一端的登录页。该端的登录路由还没落地时（例如候选人端尚未建设），
 * 退回 HR 登录页 —— 返回一个不存在的路径会让 `resolve()` 匹配不上，
 * 进而把用户送进「重定向到路由不存在的地方」这种看不懂的状态。
 */
export function loginPath(side) {
  const preferred = LOGIN_BY_SIDE[side] ?? LOGIN_BY_SIDE.hr;
  return isRegistered(preferred) ? preferred : LOGIN_BY_SIDE.hr;
}

/** 把 `#/positions` 或 `/positions` 拆成 `['positions']`。 */
const segmentsOf = (value) => String(value ?? '').replace(/^#/, '').split('/').filter(Boolean);

/**
 * 匹配一条路由。返回 `{ route, params }`，都不匹配返回 null。
 * 匹配是**全段相等**（段数也必须相同）：`/interviews/abc/complete` 不会被
 * `/interviews/:id` 吃掉一部分。
 */
export function matchRoute(hash) {
  const segments = segmentsOf(hash);
  for (const route of routes) {
    const pattern = segmentsOf(route.path);
    if (pattern.length !== segments.length) continue;
    const params = {};
    let matched = true;
    for (let i = 0; i < pattern.length; i += 1) {
      if (pattern[i].startsWith(':')) params[pattern[i].slice(1)] = segments[i];
      else if (pattern[i] !== segments[i]) { matched = false; break; }
    }
    if (matched) return { route, params };
  }
  return null;
}

/**
 * 默认落地页：某一端里第一个**带导航的**非公开页；一个都没有时放宽到
 * 该端任意非公开页；再没有就返回它的登录页（调用方据此避免把用户
 * 重定向到自己身上 —— 同 hash 不触发 hashchange，页面会空着不渲染）。
 */
export function defaultRoute(side, isAdmin = false) {
  const usable = (route, topOnly) =>
    !route.isPublic &&
    (!topOnly || Boolean(route.nav)) &&
    !(route.adminOnly && !isAdmin) &&
    route.side === side;

  for (const route of routes) if (usable(route, true)) return route.path;
  for (const route of routes) if (usable(route, false)) return route.path;
  return loginPath(side);
}

/**
 * 裸入口（`#/`、未知 hash）该去哪。
 *
 * 单机约束下两端登录态分开存、可能同时存在（PRD §9），因此「谁登录了去谁那端」。
 * 两端都登录时**优先候选人**：HR 侧的入口永远在脊上摆着，而候选人一旦被弹到
 * HR 界面，就只能自己记得住地址。
 *
 * 未知 hash 还要**先看前缀**：`#/candidate/xxx` 不能把候选人弹到 HR 登录页 ——
 * 那是候选人输错地址后最费解的一种表现（module-15 §3.1）。
 *
 * `sides` 形如 `{ hr: { loggedIn, isAdmin }, candidate: { loggedIn, isAdmin } }`。
 */
export function entryRoute({ hash, sides }) {
  const path = String(hash ?? '').replace(/^#/, '');
  const order = path.startsWith('/candidate') || sides.candidate.loggedIn
    ? ['candidate', 'hr']
    : ['hr', 'candidate'];

  for (const side of order) {
    const target = defaultRoute(side, sides[side].isAdmin);
    if (target !== path) return target;
  }
  return LOGIN_BY_SIDE.hr;
}

/**
 * 守卫决策（纯函数，可单测）。
 *
 * 返回三者之一：
 *   { action: 'allow' }
 *   { action: 'redirect', to }                    —— 静默改道，不提示
 *   { action: 'deny', message, to }               —— 先提示，再改道（to 可为 null）
 *
 * `state` 形如 `{ loggedIn, isAdmin, target }`：
 *   `loggedIn` / `isAdmin` 必须是**这条路由所属那一端**的状态（调用方在取值前
 *   先 `session.setSide(route.side)`）；`target` 是本端的默认落地页。
 */
export function decide(route, { loggedIn, isAdmin, target }) {
  if (route.isPublic) {
    // 登录与否都可达的页面（激活页）不做重定向
    if (route.open) return { action: 'allow' };
    // 已登录还去登录页 → 送回**本端**的默认页
    if (!loggedIn || target === route.path) return { action: 'allow' };
    return { action: 'redirect', to: target };
  }

  if (!loggedIn) return { action: 'redirect', to: loginPath(route.side) };

  // 角色守卫是**精确匹配、无继承**（module-16 §3.1）：admin 不因为「权限大」
  // 就被放行到本端以外的页面，两侧是各自独立的集合。
  if (route.adminOnly && !isAdmin) {
    return {
      action: 'deny',
      message: '无权限访问该页面',
      // 改道目标就是本端默认页；它若正好是当前页，说明无处可去，
      // 此时给 to=null，调用方就不会发起一次「重定向到自己」的空转。
      to: target === route.path ? null : target,
    };
  }

  return { action: 'allow' };
}

/* ==========================================================================
   以下是有副作用的部分：读写 location、挂 hashchange、渲染页面。
   ========================================================================== */

let pages = {};
export function registerPages(map) { pages = map; }

let container = null;
let currentPage = null;

function guard(route) {
  session.setSide(route.side);
  const verdict = decide(route, {
    loggedIn: auth.isLoggedIn(),
    isAdmin: auth.isAdmin(),
    target: defaultRoute(route.side, auth.isAdmin()),
  });

  if (verdict.action === 'allow') return true;
  if (verdict.action === 'deny') toast.error(verdict.message);
  if (verdict.to) location.replace(`#${verdict.to}`);
  return false;
}

async function render() {
  const matched = matchRoute(location.hash.replace(/^#/, ''));
  if (!matched) {
    location.replace(`#${entryRouteOf()}`);
    return;
  }
  if (!guard(matched.route)) return;

  // 离开上一页前必须清理 —— 评估页的 SSE 连接靠这一步关闭
  if (currentPage?.destroy) {
    try { currentPage.destroy(); } catch (error) { console.error('页面清理失败', error); }
  }
  currentPage = null;

  const page = pages[matched.route.key];
  if (!page) {
    console.error(`页面未注册：${matched.route.key}`);
    toast.error('页面加载失败，请刷新重试');
    return;
  }

  currentPage = page;
  await page.render(container, matched.params);
}

function currentSides() {
  return {
    hr: { loggedIn: auth.isLoggedInOn('hr'), isAdmin: auth.isAdminOn('hr') },
    candidate: { loggedIn: auth.isLoggedInOn('candidate'), isAdmin: auth.isAdminOn('candidate') },
  };
}

function entryRouteOf() {
  return entryRoute({ hash: location.hash, sides: currentSides() });
}

export function navigate(path) {
  const target = `#${path}`;
  if (location.hash === target) { render(); return; }
  location.hash = target;
}

export function start(mountPoint) {
  container = mountPoint;
  window.addEventListener('hashchange', render);
  if (!location.hash) location.replace(`#${entryRouteOf()}`);
  render();
}
