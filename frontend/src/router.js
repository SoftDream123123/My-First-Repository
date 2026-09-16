/**
 * hash 路由（module-07 §3.1、§3.2、§3.3）。
 *
 * 页面模块契约：导出 render(container, params)，可选 destroy()。
 * 路由在切换前必须调用上一页的 destroy —— 评估页持有 SSE 长连接，
 * 不清理会导致连接泄漏、后台仍在推送、甚至重复渲染。
 */

import * as auth from './auth.js';
import { toast } from './components/toast.js';

const routes = [
  { path: '/login', load: () => import('./pages/login.js'), isPublic: true },
  { path: '/interviews', load: () => import('./pages/interviews.js') },
  { path: '/interviews/:id/evaluation', load: () => import('./pages/evaluation.js') },
  { path: '/interviews/:id', load: () => import('./pages/interview-detail.js') },
  { path: '/positions', load: () => import('./pages/positions.js') },
  { path: '/questions', load: () => import('./pages/questions.js') },
  { path: '/users', load: () => import('./pages/users.js'), adminOnly: true },
];

export const DEFAULT_ROUTE = '/interviews';

let container = null;
let currentPage = null;

/** 把当前 hash 解析为 { route, params }。 */
function resolve() {
  const raw = location.hash.replace(/^#/, '') || DEFAULT_ROUTE;
  const segments = raw.split('/').filter(Boolean);

  for (const route of routes) {
    const pattern = route.path.split('/').filter(Boolean);
    if (pattern.length !== segments.length) continue;

    const params = {};
    let matched = true;

    for (let i = 0; i < pattern.length; i += 1) {
      if (pattern[i].startsWith(':')) {
        params[pattern[i].slice(1)] = segments[i];
      } else if (pattern[i] !== segments[i]) {
        matched = false;
        break;
      }
    }

    if (matched) return { route, params };
  }

  return null;
}

/** 导航守卫（§3.3）。返回 true 表示放行。 */
function guard(route) {
  if (route.isPublic) {
    // 已登录还去登录页 → 送回默认页
    if (auth.isLoggedIn()) {
      location.replace(`#${DEFAULT_ROUTE}`);
      return false;
    }
    return true;
  }

  if (!auth.isLoggedIn()) {
    location.replace('#/login');
    return false;
  }

  if (route.adminOnly && !auth.isAdmin()) {
    toast.error('无权限访问该页面');
    location.replace(`#${DEFAULT_ROUTE}`);
    return false;
  }

  return true;
}

async function render() {
  const resolved = resolve();

  if (!resolved) {
    location.replace(`#${DEFAULT_ROUTE}`);
    return;
  }

  if (!guard(resolved.route)) return;

  // 离开上一页前必须清理 —— 评估页的 SSE 连接靠这一步关闭
  if (currentPage?.destroy) {
    try {
      currentPage.destroy();
    } catch (error) {
      console.error('页面清理失败', error);
    }
  }
  currentPage = null;

  let module;
  try {
    module = await resolved.route.load();
  } catch (error) {
    console.error('页面加载失败', error);
    toast.error('页面加载失败，请刷新重试');
    return;
  }

  currentPage = module;
  await module.render(container, resolved.params);
}

export function navigate(path) {
  const target = `#${path}`;
  if (location.hash === target) {
    render();
    return;
  }
  location.hash = target;
}

export function start(mountPoint) {
  container = mountPoint;
  window.addEventListener('hashchange', render);
  if (!location.hash) location.replace(`#${DEFAULT_ROUTE}`);
  render();
}
