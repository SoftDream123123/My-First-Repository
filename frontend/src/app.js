/**
 * app.js —— 应用装配
 *
 * 与 main.js 分开，是为了让浏览器侧的 Mock 测试台（`mock/*-harness.html`）
 * 能用**同一份页面注册表**启动真实路由，而不是各抄一份 ——
 * 抄一份的代价是「新增页面时测试台悄悄漏掉它」。
 *
 * 页面注册表是**静态**的：不在这里注册的路由找不到页面（`router.render()`
 * 会报错，而不是安静地落到别处）。因此每加一个页面，这里要同步加一行。
 */

import * as api from './api.js';
import * as auth from './auth.js';
import * as session from './session.js';
import { registerPages, start, loginPath } from './router.js';
import { toast } from './components/toast.js';

import * as login from './pages/login.js';
import * as interviews from './pages/interviews.js';
import * as interviewDetail from './pages/interview-detail.js';
import * as evaluation from './pages/evaluation.js';
import * as interviewPrep from './pages/interview-prep.js';
import * as positions from './pages/positions.js';
import * as questions from './pages/questions.js';
import * as users from './pages/users.js';
import * as candidateLogin from './pages/candidate-login.js';
import * as candidateActivate from './pages/candidate-activate.js';
import * as candidateInterviews from './pages/candidate-interviews.js';
import * as candidateInterviewDetail from './pages/candidate-interview-detail.js';
import * as candidateFeedback from './pages/candidate-feedback.js';
import * as candidatePractice from './pages/candidate-practice.js';
import * as practiceSession from './pages/candidate-practice-session.js';
import * as wrongBook from './pages/candidate-wrong-book.js';
import * as practiceStats from './pages/candidate-stats.js';

export const PAGES = {
  login,
  interviews,
  interviewDetail,
  evaluation,
  interviewPrep,
  positions,
  questions,
  users,
  candidateLogin,
  candidateActivate,
  candidateInterviews,
  candidateInterviewDetail,
  candidateFeedback,
  candidatePractice,
  practiceSession,
  wrongBook,
  practiceStats,
};

/**
 * 统一 401 处理：清 token + 跳**本端**登录页。页面不必各自处理。
 *
 * 注意 api.js 已把「凭据不符」类 401（登录失败、邀请码复用账号时密码错）
 * 排除在外，它们不会被走到这里。
 */
export function installUnauthorizedHandler() {
  api.setUnauthorizedHandler(() => {
    toast.error('登录状态已失效，请重新登录');
    location.replace(`#${loginPath(session.getSide())}`);
  });
}

/**
 * 启动前刷新用户信息。
 *
 * 角色**不缓存在 JWT 里**（API 文档 §2.2）：管理员把某人提升为管理员后，
 * 对方用旧 token 即可访问新权限的接口。若界面只信登录那一刻的角色，
 * 就会出现「后端放行、前端却把入口藏起来」的不一致。
 *
 * 401 由统一处理器接管（清登录态并回登录页），这里只吞掉异常本身。
 * 网络故障时也继续启动 —— 页面自己会显示加载失败。
 */
export async function refreshLoggedInSides() {
  for (const side of ['hr', 'candidate']) {
    if (!auth.isLoggedInOn(side)) continue;
    session.setSide(side);
    try {
      await auth.refreshUser();
    } catch {
      // 已由统一 401 处理器处理
    }
  }
}

export async function boot(app = document.getElementById('app')) {
  if (!app) throw new Error('找不到挂载点 #app');
  installUnauthorizedHandler();
  await refreshLoggedInSides();
  registerPages(PAGES);
  start(app);
}
