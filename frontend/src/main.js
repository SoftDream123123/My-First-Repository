/**
 * 应用启动（module-07 §3）。
 *
 * 页面在这里静态导入并注册给路由 —— 模块图完全静态，
 * 既能让单文件打包工作，也让"这个应用由哪些页面组成"一眼可见。
 */

import { setUnauthorizedHandler } from './api.js';
import * as auth from './auth.js';
import { registerPages, start } from './router.js';
import { toast } from './components/toast.js';

import * as login from './pages/login.js';
import * as interviews from './pages/interviews.js';
import * as interviewDetail from './pages/interview-detail.js';
import * as evaluation from './pages/evaluation.js';
import * as positions from './pages/positions.js';
import * as questions from './pages/questions.js';
import * as users from './pages/users.js';

registerPages({
  login,
  interviews,
  interviewDetail,
  evaluation,
  positions,
  questions,
  users,
});

// 统一 401 处理：清 token + 跳登录。页面不必各自处理。
setUnauthorizedHandler(() => {
  toast.error('登录状态已失效，请重新登录');
  location.hash = '#/login';
});

const app = document.getElementById('app');
if (!app) {
  throw new Error('找不到挂载点 #app');
}

/**
 * 启动前刷新一次用户信息（module-07 §4.2）。
 *
 * 角色不缓存在 JWT 里，后端每次请求都回查数据库 —— 所以被提升为 admin 后
 * 无需重新登录，这里刷新后侧边栏立刻出现「用户管理」。
 * 失败不阻塞启动：401 已由上面的统一处理器接管，其余错误先用缓存的信息渲染。
 */
async function boot() {
  if (auth.isLoggedIn()) {
    try {
      await auth.refreshUser();
    } catch {
      /* 交给统一 401 处理；其它错误不阻塞 */
    }
  }
  start(app);
}

boot();
