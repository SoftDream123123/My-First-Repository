/**
 * 地基模块 Mock 联调测试 —— 登录分流、路由守卫、外壳、按端分 key、统一 401。
 *
 * 覆盖的是**只靠单测测不到**的那一半：真实路由跳转、真实 DOM、真实重定向。
 * 路由守卫的决策逻辑本身在 `src/__tests__/router.test.js` 里测；
 * 这里测的是「决策真的被执行了没有」—— 少了这一步，守卫写对了没人调用也看不出来。
 *
 * 运行：npm run dev 后打开 /mock/auth-harness.html
 */

import { boot, installUnauthorizedHandler, PAGES } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import * as auth from '../src/auth.js';
import {
  buttonIn, clearToasts, createReport, installFakeBackend,
  openOverlay, settle, toasts,
} from './harness.js';

const report = createReport('地基模块 Mock 测试');
const { check } = report;

/* ---------- 假后端 ---------- */

const ADMIN = { id: 1, username: 'admin', role: 'admin', is_active: true, created_at: '2026-08-02T09:00:00' };
const CANDIDATE = { id: 7, username: 'li.yun', role: 'candidate', is_active: true, created_at: '2026-09-01T09:00:00' };

function handlers() {
  return {
    'POST /auth/login': ({ body }) => {
      if (body.username === 'admin' && body.password === 'admin12345') {
        return { status: 200, body: { token: 'hr-token', user: ADMIN } };
      }
      if (body.username === 'li.yun' && body.password === 'candidate123') {
        return { status: 200, body: { token: 'cand-token', user: CANDIDATE } };
      }
      return { status: 401, body: { code: 'UNAUTHORIZED', message: '用户名或密码错误', detail: null } };
    },
    'GET /auth/me': () => ({ status: 200, body: ADMIN }),
    'GET /interviews': () => ({ status: 200, body: [] }),
    'GET /positions': () => ({ status: 200, body: [] }),
    'GET /users': () => ({ status: 200, body: [ADMIN] }),
    'GET /candidate/interviews': () => ({ status: 200, body: [] }),
  };
}

const backend = installFakeBackend(handlers());
installUnauthorizedHandler();

/* ---------- 小工具 ---------- */

/**
 * 走真实路由跳转。
 *
 * 用 `router.navigate()` 而不是直接写 `location.hash`：**跳到当前所在的 hash
 * 不会触发 hashchange**，那样「改了登录态再回来」的场景会拿到上一轮的 DOM，
 * 断言全都测的是旧页面（踩过一次）。
 */
async function go(hash) {
  router.navigate(String(hash).replace(/^#/, ''));
  await settle();
  await settle();
}

const hash = () => location.hash;
const page = () => document.getElementById('app');
const has = (selector) => Boolean(page().querySelector(selector));
const tokenIn = (side) => {
  const previous = session.getSide();
  session.setSide(side);
  const token = session.getToken();
  session.setSide(previous);
  return token;
};

/** 把登录态直接写进存储（跳过登录表单，用于只验守卫的用例）。 */
function signInAs(side, token, user) {
  session.setSide(side);
  session.save(token, user);
  session.setSide('hr');
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }

  /* ---------- 1. 起手：未登录 → 登录页 ---------- */
  await boot(document.getElementById('app'));
  await settle();
  await settle();
  await settle();

  check('未登录进裸入口 → 停在 #/login', hash() === '#/login', hash());
  check('登录页渲染了表单', has('.login-form'));
  check('登录页不套外壳（没有 .spine）', !has('.spine'));
  check('登录页展示了产品流程（4 步）', page().querySelectorAll('.login-flow-item').length === 4);

  /* ---------- 2. 表单本地校验 ---------- */
  clearToasts();
  backend.reset();
  buttonIn(page(), '登录').click();
  await settle();

  check('空用户名 → 用户名下方内联报错', page().querySelector('#login-username')?.nextElementSibling?.textContent === '请填写用户名',
    page().querySelector('#login-username')?.nextElementSibling?.textContent);
  check('空用户名 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  check('空用户名 → 不弹 toast', toasts().length === 0, toasts().join(' | '));

  /* ---------- 3. 登录失败：401 不等于「会话失效」 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#login-username').value = 'admin';
  page().querySelector('#login-password').value = 'wrong-password';
  buttonIn(page(), '登录').click();
  await settle();
  await settle();

  check('密码错 → 用后端文案提示', toasts().includes('用户名或密码错误'), toasts().join(' | '));
  check('密码错 → 不写登录态', tokenIn('hr') === null, String(tokenIn('hr')));
  check('密码错 → 不跳转，仍停在登录页', hash() === '#/login', hash());

  /* ---------- 4. 候选人账号在 HR 登录页登录 → 送到候选人端 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#login-username').value = 'li.yun';
  page().querySelector('#login-password').value = 'candidate123';
  buttonIn(page(), '登录').click();
  await settle();
  await settle();
  await settle();

  check('候选人账号在 HR 登录页 → 落到候选人默认页', hash() === '#/candidate/interviews', hash());
  check('候选人账号 → 登录态写进 candidate.*，不是 hr.*',
    tokenIn('candidate') === 'cand-token' && tokenIn('hr') === null,
    `${tokenIn('hr')} / ${tokenIn('candidate')}`);
  check('候选人账号 → 脊上是「候选人端」，不是「HR 工作台」',
    page().querySelector('.spine-sub')?.textContent === '候选人端',
    page().querySelector('.spine-sub')?.textContent);

  // 回到 HR 登录页继续后面的用例（此时 HR 端仍未登录，守卫会放行）
  await go('#/login');
  check('回到 HR 登录页仍然可达（候选人登录态不该把 HR 页挡住）',
    has('.login-form') && hash() === '#/login', `${hash()} / ${has('.login-form')}`);

  /* ---------- 5. admin 登录成功 → 外壳 + 默认页 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#login-username').value = 'admin';
  page().querySelector('#login-password').value = 'admin12345';
  buttonIn(page(), '登录').click();
  await settle();
  await settle();
  await settle();

  check('admin 登录成功 → 跳到本端默认页 #/interviews', hash() === '#/interviews', hash());
  check('admin 登录成功 → token 存在 hr.* 下', tokenIn('hr') === 'hr-token', String(tokenIn('hr')));
  // 候选人端此刻已经登录着（用例 4 留下的）—— HR 端登录**只写自己那一格**。
  // 这条比「候选人端是空的」更有意义：它测的是两端互不干扰，而不是「谁都没写」。
  check('HR 端登录不覆盖候选人端已有的登录态', tokenIn('candidate') === 'cand-token', String(tokenIn('candidate')));
  check('外壳渲染了脊', has('.spine'));
  check('脊上显示用户名', page().querySelector('.spine-username')?.textContent === 'admin');
  check('脊上显示角色为「管理员」', page().querySelector('.spine-role')?.textContent === '管理员');

  const navTexts = [...page().querySelectorAll('.nav-item')].map((a) => a.textContent.trim());
  // 期望值**从路由表算**，不写死清单 —— 写死的话每加一个页面都要改这里，
  // 而「改了忘了同步」恰恰是这类断言最该防的事。
  const expectedNav = (isAdmin) => router.routes
    .filter((r) => r.nav && r.side === 'hr' && (!r.adminOnly || isAdmin))
    .map((r) => r.nav);
  check('admin 的导航 = 路由表里本端带 nav 且角色可见的全部路由',
    navTexts.join(',') === expectedNav(true).join(','),
    `${navTexts.join(',')} vs ${expectedNav(true).join(',')}`);
  check('导航项确实有多于一项（否则上面那条会因为两边都空而恒真）', navTexts.length >= 2, String(navTexts.length));
  check('当前项高亮在「面试」上（默认落地页）', page().querySelector('.nav-item.is-active')?.textContent.trim() === '面试', page().querySelector('.nav-item.is-active')?.textContent.trim());
  check('业务请求带上了 JWT', backend.calls.some((c) => c.path === '/interviews' && c.auth === 'Bearer hr-token'),
    backend.calls.map((c) => `${c.path}:${c.auth}`).join(' '));

  /* ---------- 6. 守卫：HR 角色访问 adminOnly 页面 ---------- */
  session.setUser({ ...ADMIN, role: 'hr' });
  await go('#/positions');
  const hrNav = [...page().querySelectorAll('.nav-item')].map((a) => a.textContent.trim());
  check('HR 角色的导航里没有「用户管理」', !hrNav.includes('用户管理'), hrNav.join(','));
  check('HR 角色的导航 = 去掉 adminOnly 之后的那一份',
    hrNav.join(',') === expectedNav(false).join(','),
    `${hrNav.join(',')} vs ${expectedNav(false).join(',')}`);
  check('HR 角色确实少了东西（否则上面那条可能因为两边相等而没测到过滤）',
    expectedNav(false).length < expectedNav(true).length);

  clearToasts();
  await go('#/users');
  check('HR 角色进 #/users → 被拦下并提示', toasts().includes('无权限访问该页面'), toasts().join(' | '));
  check('HR 角色进 #/users → 改道到本端默认页', hash() === '#/interviews', hash());
  check('被拦下时没有真的去请求用户列表', !backend.calls.some((c) => c.path === '/users'));

  /* ---------- 7. 按端分 key：两端可以同时保持登录 ---------- */
  signInAs('candidate', 'cand-token', CANDIDATE);
  check('写入候选人端不覆盖 HR 端', tokenIn('hr') === 'hr-token' && tokenIn('candidate') === 'cand-token',
    `${tokenIn('hr')} / ${tokenIn('candidate')}`);
  session.setSide('candidate');
  check('活动端为候选人时取到的是候选人 token', auth.getToken() === 'cand-token', String(auth.getToken()));
  check('活动端为候选人时角色判定正确（非 admin）', auth.isAdmin() === false);
  session.setSide('hr');
  check('切回 HR 端取到的是 HR token', auth.getToken() === 'hr-token', String(auth.getToken()));

  /* ---------- 8. 退出登录只清当前端 ---------- */
  session.setUser(ADMIN);
  await go('#/positions');
  clearToasts();
  buttonIn(page().querySelector('.spine'), '退出登录').click();
  await settle();
  await settle();

  check('退出登录 → 清掉 HR token', tokenIn('hr') === null, String(tokenIn('hr')));
  check('退出登录 → **不**清掉候选人端（两端各有各的登录态）', tokenIn('candidate') === 'cand-token', String(tokenIn('candidate')));
  check('退出登录 → 回到登录页', hash() === '#/login', hash());

  /* ---------- 9. 统一 401：会话失效 ---------- */
  signInAs('hr', 'stale-token', ADMIN);
  backend.setHandlers({
    ...handlers(),
    'GET /positions': () => ({ status: 401, body: { code: 'UNAUTHORIZED', message: '未认证', detail: null } }),
  });
  clearToasts();
  await go('#/positions');
  await settle();

  check('受保护接口返回 401 → 清掉登录态', tokenIn('hr') === null, String(tokenIn('hr')));
  check('受保护接口返回 401 → 提示「登录状态已失效」',
    toasts().some((t) => t.includes('登录状态已失效')), toasts().join(' | '));
  check('受保护接口返回 401 → 回到登录页', hash() === '#/login', hash());

  /* ---------- 10. 会话失效后守卫重新生效 ---------- */
  clearToasts();
  await go('#/users');
  check('登录态没了 → 访问受保护页被送回登录页', hash() === '#/login', hash());
  check('登录态没了 → 不弹「无权限」（那是角色问题，不是登录问题）',
    !toasts().includes('无权限访问该页面'), toasts().join(' | '));

  /* ---------- 11. 注册表与路由表一一对应 ---------- */
  const missing = router.routes.filter((r) => !PAGES[r.key]).map((r) => r.key);
  check('路由表里每个 key 都有页面（没有点进去就报错的路由）', missing.length === 0, missing.join(','));
  const orphans = Object.keys(PAGES).filter((key) => !router.routes.some((r) => r.key === key));
  check('注册表里没有路由表用不到的孤儿页面', orphans.length === 0, orphans.join(','));

  check('没有残留的弹窗', openOverlay() === null);
});
