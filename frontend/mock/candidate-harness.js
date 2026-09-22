/**
 * 候选人端（面试链路）Mock 联调测试 —— 登录 / 注册 / 邀请激活 / 我的面试 /
 * 在线作答与交卷 / 脱敏反馈，外加两端共存的时序验证。
 *
 * 覆盖的是**只靠单测测不到**的那一半：真实路由跳转、真实 DOM、真实重定向、
 * 真实请求体。守卫的决策逻辑在 `src/__tests__/router.test.js` 里测，
 * 状态翻译在 `src/__tests__/candidate-state.test.js` 里测；
 * 这里测的是「决策与翻译真的被执行了没有」。
 *
 * ⚠️ 断言里的期望值优先**从契约来**（API 文档 §10 / §11 / §13），
 * 不从 `standalone.html` 原型的字段名来 —— 原型当年是照自己写的内存 mock
 * 开发的，两份一起错所以自洽，照搬进 `src/` 会直接不工作
 * （评估与准备两个模块都踩过，见 README）。
 *
 * 运行：npm run dev 后打开 /mock/candidate-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import { buttonIn, clearToasts, createReport, installFakeBackend, openOverlay, settle, toasts } from './harness.js';

const report = createReport('候选人端 Mock 测试');
const { check } = report;

/* ==========================================================================
   固定数据
   ========================================================================== */

const ADMIN = { id: 1, username: 'admin', role: 'admin', is_active: true, created_at: '2026-08-02T09:00:00' };
const CANDIDATE = { id: 7, username: 'li.yun', role: 'candidate', is_active: true, created_at: '2026-09-01T09:00:00' };

// 四态各一条，用来钉住 candidateState 的翻译真的落到了标签上
const AWAITING = { id: 3, position_name: '后端工程师', status: 'ongoing', question_count: 8, answered_count: 2, submitted: false, resume_id: null, created_at: '2026-09-21T10:00:00' };
const SUBMITTED = { id: 2, position_name: '前端工程师', status: 'completed', question_count: 5, answered_count: 5, submitted: true, resume_id: null, created_at: '2026-09-18T10:00:00' };
const EVALUATED = { id: 1, position_name: '数据工程师', status: 'evaluated', question_count: 6, answered_count: 6, submitted: true, resume_id: null, created_at: '2026-09-10T10:00:00' };
const CLOSED = { id: 4, position_name: '运维工程师', status: 'completed', question_count: 4, answered_count: 1, submitted: false, resume_id: null, created_at: '2026-09-15T10:00:00' };

const LIST = [AWAITING, SUBMITTED, EVALUATED, CLOSED];

/** 面试详情（候选人视图）：题目对象**恰好 5 个键**（API 文档 §13.16）。 */
function detailOf(over = {}) {
  return {
    id: 3, position_name: '后端工程师', status: 'ongoing', created_at: '2026-09-21T10:00:00',
    submitted: false, submitted_at: null, resume_id: null,
    questions: [
      { interview_question_id: 41, seq: 1, content: '请描述一次你处理线上故障的完整过程。', dimension: '沟通能力', my_answer: '我在上一家公司负责过…' },
      { interview_question_id: 42, seq: 2, content: '解释一下数据库索引的最左前缀原则。', dimension: '专业能力', my_answer: null },
      { interview_question_id: 43, seq: 3, content: '如何设计一个高可用的服务？', dimension: '逻辑思维', my_answer: null },
    ],
    ...over,
  };
}

const FEEDBACK_BASE = {
  interview_id: 1,
  level: 'summary',
  conclusion: '本场表现整体扎实：技术基础与表达都达到了岗位要求，在复杂问题的分析深度上还有提升空间。',
  strengths: ['专业能力（7.0）：技术基础扎实'],
  weaknesses: ['逻辑思维（6.0）：分析深度有待加强'],
  overall_score: null,
  generated_at: '2026-09-21T10:35:00',
};

/* ==========================================================================
   假后端
   ========================================================================== */

const flags = {
  selfRegisterDisabled: false,
  accept: null,            // null = 成功；否则 { status, body }
  answerStatus: 200,       // 200 或 409
  submitFails: false,
  feedbackLevel: 'summary',
  feedbackNotReady: false,
  listEmpty: false,
  detail: null,            // 覆盖面试详情的字段（已交卷 / 已收口等）
};

function handlers() {
  return {
    'POST /auth/login': ({ body }) => {
      if (body.username === 'admin' && body.password === 'admin12345') {
        return { status: 200, body: { token: 'hr-token', user: ADMIN } };
      }
      if (body.username === 'li.yun' && body.password === 'cand12345678') {
        return { status: 200, body: { token: 'cand-token', user: CANDIDATE } };
      }
      if (body.username === 'newbie' && body.password === 'newbie12345') {
        return { status: 200, body: { token: 'newbie-token', user: { ...CANDIDATE, id: 9, username: 'newbie' } } };
      }
      return { status: 401, body: { code: 'UNAUTHORIZED', message: '用户名或密码错误', detail: null } };
    },

    'POST /auth/register': () => (flags.selfRegisterDisabled
      ? {
          status: 409,
          body: {
            code: 'BUSINESS_ERROR',
            message: '候选人自助注册已关闭，请使用邀请码激活',
            detail: { reason: 'self_register_disabled' },
          },
        }
      : { status: 201, body: { id: 9, username: 'newbie', role: 'candidate', is_active: true, created_at: '2026-09-21T12:00:00' } }),

    'GET /auth/me': () => ({ status: 200, body: CANDIDATE }),

    'POST /candidate/invitations/:code/accept': () => flags.accept ?? {
      status: 200,
      body: {
        interview_id: 3,
        interview: { id: 3, position_name: '后端工程师', candidate_name: '李云', status: 'ongoing', question_count: 3 },
      },
    },

    'GET /candidate/interviews': () => ({ status: 200, body: flags.listEmpty ? [] : LIST }),

    'GET /candidate/interviews/:id': () => ({ status: 200, body: detailOf(flags.detail) }),

    'POST /candidate/interviews/:id/answers': ({ body }) => (flags.answerStatus === 200
      ? { status: 200, body: { interview_question_id: body.interview_question_id, content: body.content, submitted_at: null } }
      : { status: 409, body: { code: 'BUSINESS_ERROR', message: '已交卷，不可修改作答', detail: null } }),

    'POST /candidate/interviews/:id/submit': () => (flags.submitFails
      ? { status: 404, body: { code: 'NOT_FOUND', message: '面试不存在', detail: null } }
      : { status: 200, body: { interview_id: 3, submitted_at: '2026-09-21T11:20:00', answered_count: 2 } }),

    'GET /candidate/interviews/:id/feedback': () => {
      if (flags.feedbackNotReady) {
        return { status: 409, body: { code: 'BUSINESS_ERROR', message: '评估尚未完成', detail: null } };
      }
      return {
        status: 200,
        body: flags.feedbackLevel === 'full'
          ? { ...FEEDBACK_BASE, level: 'full', overall_score: 6.5 }
          : FEEDBACK_BASE,
      };
    },

    // HR 侧只用于「两端共存」的两条用例
    'GET /interviews': () => ({ status: 200, body: [] }),
  };
}

const backend = installFakeBackend(handlers());
installUnauthorizedHandler();

/* ==========================================================================
   小工具
   ========================================================================== */

/**
 * 走真实路由跳转。
 * 用 `router.navigate()` 而不是直接写 `location.hash`：**跳到当前所在的 hash
 * 不会触发 hashchange**，那样「改了登录态再回来」的场景会拿到上一轮的 DOM。
 */
async function go(hash) {
  router.navigate(String(hash).replace(/^#/, ''));
  await settle();
  await settle();
  await settle();
}

const hash = () => location.hash;
const page = () => document.getElementById('app');
const text = () => page().textContent;
const has = (selector) => Boolean(page().querySelector(selector));
const all = (selector) => [...page().querySelectorAll(selector)];
const navTexts = () => all('.nav-item').map((a) => a.textContent.trim());

const tokenIn = (side) => {
  const previous = session.getSide();
  session.setSide(side);
  const token = session.getToken();
  session.setSide(previous);
  return token;
};

/** 把登录态直接写进存储（跳过登录表单，用于只验某个页面本身的用例）。 */
function signInAs(side, token, user) {
  const previous = session.getSide();
  session.setSide(side);
  session.save(token, user);
  session.setSide(previous);
}

function signOut(side) {
  const previous = session.getSide();
  session.setSide(side);
  session.clear();
  session.setSide(previous);
}

/** 最近一次命中某路径的请求。 */
const lastCall = (method, path) => [...backend.calls].reverse().find((c) => c.method === method && c.path === path);
const called = (method, path) => backend.calls.some((c) => c.method === method && c.path === path);

/** 页面上某个字段下方**已显示**的报错文本；没显示返回 null。 */
function inlineError(id) {
  const node = page().querySelector(`#${id}`)?.parentElement?.querySelector('.field-error');
  return node && !node.hidden ? node.textContent.trim() : null;
}

/**
 * 登录卡片上的**提交**按钮。
 *
 * 不能用 `buttonIn(page(), '登录')` —— 分段控件的「登录」排在提交按钮之前，
 * 取到的是它，于是「点了一下」实际上只是又切了一次模式：用例会**绿着什么都没测**
 * （断言「不发请求」也会因为确实没发而通过）。这类恒真断言是本工程踩过的坑。
 */
const submitBtn = () => page().querySelector('.login-form button[type="submit"]');
const segBtn = (label) => all('.seg-btn').find((b) => b.textContent.trim() === label);
const switchTo = async (label) => { segBtn(label).click(); await settle(); };

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }

  await boot(document.getElementById('app'));
  await settle();
  await settle();
  await settle();

  /* ---------- 1. 未登录进候选人页面 → 送去候选人登录页 ---------- */
  check('未登录的裸入口停在 HR 登录页（两端都没登录时优先 HR）', hash() === '#/login', hash());

  await go('#/candidate/interviews');
  check('未登录进 #/candidate/interviews → 跳 **候选人** 登录页（不是 #/login）',
    hash() === '#/candidate/login', hash());
  check('候选人登录页不套外壳（没有 .spine）', !has('.spine'));
  check('候选人登录页的品牌副标题是「候选人端」',
    page().querySelector('.login-mark-sub')?.textContent === '候选人端',
    page().querySelector('.login-mark-sub')?.textContent);
  check('候选人登录页展示的是本人的闭环（4 步）',
    all('.login-flow-item').length === 4 && text().includes('受邀'), String(all('.login-flow-item').length));

  /* ---------- 2. 登录 / 注册切换 ---------- */
  check('默认是登录模式（提交按钮写「登录」）', submitBtn()?.textContent === '登录', submitBtn()?.textContent);
  check('两种模式都在同一页（分段控件有两个选项）', all('.seg-btn').length === 2, String(all('.seg-btn').length));

  clearToasts();
  backend.reset();
  submitBtn().click();
  await settle();
  check('空用户名 → 用户名下方内联报错', inlineError('cand-username') === '请填写用户名', inlineError('cand-username'));
  check('空用户名 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  /* ---------- 3. HR 账号走错入口 → 明确拒绝且不写登录态 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#cand-username').value = 'admin';
  page().querySelector('#cand-password').value = 'admin12345';
  submitBtn().click();
  await settle();
  await settle();
  check('HR 账号在候选人登录页 → 明确拒绝',
    toasts().some((t) => t.includes('候选人端')), toasts().join(' | '));
  check('HR 账号 → 不写候选人端登录态（写进去会让 HR 页反而「未登录」）',
    tokenIn('candidate') === null, String(tokenIn('candidate')));
  check('HR 账号 → 仍停在候选人登录页（不写 HR 登录态、不跳走）',
    hash() === '#/candidate/login' && tokenIn('hr') === null, `${hash()} / ${tokenIn('hr')}`);

  /* ---------- 4. 登录成功 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#cand-username').value = 'li.yun';
  page().querySelector('#cand-password').value = 'cand12345678';
  submitBtn().click();
  await settle();
  await settle();
  await settle();

  check('登录成功 → 落到候选人默认页 #/candidate/interviews', hash() === '#/candidate/interviews', hash());
  check('登录成功 → token 存在 candidate.* 下', tokenIn('candidate') === 'cand-token', String(tokenIn('candidate')));
  check('登录成功 → HR 端仍未被写入', tokenIn('hr') === null, String(tokenIn('hr')));
  check('候选人外壳渲染了脊，副标题是「候选人端」',
    has('.spine') && page().querySelector('.spine-sub')?.textContent === '候选人端',
    page().querySelector('.spine-sub')?.textContent);

  /* ---------- 5. 我的面试：两块分组 + 四态标签 ---------- */
  const tags = all('.tag').map((n) => n.textContent.trim());
  check('列表请求带的是**候选人** token',
    lastCall('GET', '/candidate/interviews')?.auth === 'Bearer cand-token',
    String(lastCall('GET', '/candidate/interviews')?.auth));
  check('渲染了「待你作答」与「我的记录」两块',
    text().includes('待你作答') && text().includes('我的记录'));
  // 「待作答」在三态里是被**块标题 + 进度**表达的，记录那一块才逐行挂标签 ——
  // 待你作答的每一行都是待作答，再挂一个标签是把同一句话说两遍
  check('记录块里三态各有标签，且文案与状态翻译一致',
    ['已交卷', '有反馈', '已结束'].every((label) => tags.includes(label)) && tags.length === 3,
    tags.join(','));
  check('「待作答」由块标题表达（不在记录块的标签里重复）',
    all('.panel')[0].textContent.includes('待你作答') && !tags.includes('待作答'),
    `${tags.join(',')} / ${all('.panel')[0]?.querySelector('.panel-title')?.textContent}`);
  check('只有「待作答」那一场进了「待你作答」块（另三场都在记录里）',
    all('.panel').length === 2 && all('.panel')[0].textContent.includes('后端工程师')
      && !all('.panel')[0].textContent.includes('前端工程师'),
    all('.panel').map((p) => p.textContent.slice(0, 24)).join(' || '));
  check('有反馈的那一场给的是「查看反馈」，其余给「查看作答」',
    all('.table button').filter((b) => b.textContent.trim() === '查看反馈').length === 1
      && all('.table button').filter((b) => b.textContent.trim() === '查看作答').length === 2,
    all('.table button').map((b) => b.textContent.trim()).join(','));
  check('候选人端没有任何 HR 侧入口（导航里只有候选人页面）',
    navTexts().includes('我的面试') && !navTexts().includes('岗位') && !navTexts().includes('题库'),
    navTexts().join(','));

  /* ---------- 6. 空态：把最可能的下一步直接给出 ---------- */
  flags.listEmpty = true;
  backend.reset();
  await go('#/candidate/interviews');
  check('空态文案给的是「凭邀请码进入」', text().includes('还没有面试') && text().includes('凭邀请码进入'));
  flags.listEmpty = false;

  /* ---------- 7. 邀请激活：已登录时用户名固定为当前账号 ---------- */
  backend.reset();
  await go('#/candidate/activate');
  // 激活页与登录页同一种版式：**不套外壳**（它是进门之前的那一步）
  check('激活页不套外壳，且品牌副标题是「候选人端」',
    !has('.spine') && page().querySelector('.login-mark-sub')?.textContent === '候选人端',
    page().querySelector('.login-mark-sub')?.textContent);
  check('已登录时用户名预填且只读',
    page().querySelector('#activate-username')?.value === 'li.yun'
      && page().querySelector('#activate-username')?.readOnly === true,
    page().querySelector('#activate-username')?.value);
  check('密码字段的说明跟着**真实契约**（账号已存在时校验密码，不是「忽略」）',
    text().includes('核对身份') && !text().includes('会被忽略'),
    text().includes('会被忽略') ? '仍写着「会被忽略」' : 'ok');

  /* ---------- 8. 激活成功：已登录时不再重复登录 ---------- */
  clearToasts();
  backend.reset();
  page().querySelector('#activate-code').value = 'hT9rQ2xLm4ZbN1vCk8sPwA';
  page().querySelector('#activate-password').value = 'cand12345678';
  buttonIn(page(), '激活并进入面试').click();
  await settle();
  await settle();
  await settle();

  check('激活请求提交的是 {username, password}',
    lastCall('POST', '/candidate/invitations/hT9rQ2xLm4ZbN1vCk8sPwA/accept')?.body?.username === 'li.yun',
    JSON.stringify(lastCall('POST', '/candidate/invitations/hT9rQ2xLm4ZbN1vCk8sPwA/accept')?.body));
  check('已登录时不再重复发登录请求（token 已在手上）', !called('POST', '/auth/login'));
  check('激活成功 → 直接进入该场面试的作答页', hash() === '#/candidate/interviews/3', hash());
  check('激活成功 → 提示里带出了绑定的岗位', toasts().some((t) => t.includes('后端工程师')), toasts().join(' | '));

  /* ---------- 9. 在线作答：导航、待答/已答、失焦自动保存 ---------- */
  check('作答页顶部有交卷条（未交卷、进行中）', has('.submit-bar') && !has('.submit-bar.is-frozen'));
  check('交卷条报出「已答 1 / 3」（只有第 1 题有作答）', text().includes('已答 1 / 3'), text().match(/已答 \d+ \/ \d+/)?.[0]);
  check('左侧导航列出全部 3 题', all('.qnav-item').length === 3, String(all('.qnav-item').length));
  check('导航里已答的写「已答」、其余写「待答」',
    all('.qnav-mark').map((n) => n.textContent.trim()).join(',') === '已答,待答,待答',
    all('.qnav-mark').map((n) => n.textContent.trim()).join(','));

  backend.reset();
  const textarea = page().querySelector('#candidate-answer');
  textarea.value = '这是我在输入框里改过但还没失焦的内容';
  textarea.dispatchEvent(new Event('blur'));
  await settle();
  await settle();
  check('失焦自动保存 → 提交体用的是 interview_question_id（不是面试 id、不是题目 id）',
    lastCall('POST', '/candidate/interviews/3/answers')?.body?.interview_question_id === 41,
    JSON.stringify(lastCall('POST', '/candidate/interviews/3/answers')?.body));
  check('保存成功 → 就地显示「已保存」', page().querySelector('.save-state.is-saved')?.textContent === '已保存',
    page().querySelector('.save-state')?.className);

  backend.reset();
  page().querySelector('#candidate-answer').dispatchEvent(new Event('blur'));
  await settle();
  check('没改就不发请求（失焦不应造成无谓的写库）', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  /* ---------- 9b. 没失焦也要落盘：pagehide 与 SPA 换页 ---------- */
  // blur 覆盖不到 F5 / 关标签页 / 浏览器后退键 —— 那几条路径输入框都不会失焦，
  // 原来整段作答会**静默消失**，而页面上还写着「离开输入框会自动保存」。
  backend.reset();
  const unblurred = page().querySelector('#candidate-answer');
  unblurred.value = '写了很长一段但一次都没失焦的作答';
  window.dispatchEvent(new Event('pagehide'));
  await settle();
  const flushed = lastCall('POST', '/candidate/interviews/3/answers');
  check('pagehide（F5 / 关标签页）也会把未落盘的作答发出去',
    flushed?.body?.content === '写了很长一段但一次都没失焦的作答',
    JSON.stringify(flushed?.body));
  check('兜底落盘用的也是 interview_question_id（不是面试 id）',
    flushed?.body?.interview_question_id === 41, String(flushed?.body?.interview_question_id));
  check('兜底落盘带上了 Authorization（keepalive 请求不能丢鉴权）',
    Boolean(flushed?.auth), String(flushed?.auth));

  // SPA 内部换页（含后退键）走的是 router 的 destroy()，同样不会让输入框失焦
  backend.reset();
  page().querySelector('#candidate-answer').value = '换页前没失焦的作答';
  await go('#/candidate/interviews');
  await settle();
  check('SPA 内换页（含浏览器后退键）也会把未落盘的作答发出去',
    lastCall('POST', '/candidate/interviews/3/answers')?.body?.content === '换页前没失焦的作答',
    JSON.stringify(lastCall('POST', '/candidate/interviews/3/answers')?.body));

  /* ---------- 10. 已交卷态：输入框只读 + 冻结条 ---------- */
  flags.detail = { submitted: true, submitted_at: '2026-09-21T11:20:00' };
  backend.reset();
  await go('#/candidate/interviews/3');
  check('已交卷 → 输入框只读', page().querySelector('#candidate-answer')?.readOnly === true);
  check('已交卷 → 交卷条变成冻结态并写明交卷时刻',
    has('.submit-bar.is-frozen') && text().includes('已于'), page().querySelector('.submit-bar')?.textContent);
  check('已交卷 → 页面说明「作答已锁定」而不是「离开输入框会自动保存」',
    text().includes('你已交卷，作答已锁定') && !text().includes('离开输入框会自动保存'),
    text().includes('离开输入框会自动保存') ? '仍在说会自动保存' : 'ok');
  check('已交卷 → 导航里剩下的题写「未答」而不是「待答」',
    all('.qnav-mark').map((n) => n.textContent.trim()).join(',') === '已答,未答,未答',
    all('.qnav-mark').map((n) => n.textContent.trim()).join(','));
  check('未评估时不给反馈入口，但说明「评估完成后会出现」',
    !all('button').some((b) => b.textContent.trim() === '查看反馈')
      && text().includes('评估完成后'), text().includes('评估完成后') ? 'ok' : '缺说明');

  /* ---------- 11. 面试已收口但本人未交卷 ---------- */
  flags.detail = { status: 'completed' };
  backend.reset();
  await go('#/candidate/interviews/3');
  check('面试已收口且未交卷 → 没有交卷条（这页只剩回看一个用途）', !has('.submit-bar'));
  check('面试已收口 → 说明「作答通道已关闭」，不谎称会自动保存',
    text().includes('作答通道已关闭'), text().includes('作答通道已关闭') ? 'ok' : '缺说明');
  check('面试已收口 → 输入框只读', page().querySelector('#candidate-answer')?.readOnly === true);
  flags.detail = null;

  /* ---------- 12. 交卷：先 flush 再确认，取消则什么都不发生 ---------- */
  backend.reset();
  await go('#/candidate/interviews/3');
  const box2 = page().querySelector('#candidate-answer');
  box2.value = '交卷前刚改、还没失焦的内容';
  buttonIn(page(), '交卷').click();
  await settle();
  await settle();
  check('点交卷先 flush 未保存内容（不等失焦）',
    lastCall('POST', '/candidate/interviews/3/answers')?.body?.content === '交卷前刚改、还没失焦的内容',
    JSON.stringify(lastCall('POST', '/candidate/interviews/3/answers')?.body));
  check('flush 之后才弹二次确认', openOverlay() !== null);
  check('未答的题数被如实说出来（还有 2 题）',
    openOverlay()?.textContent.includes('还有 2 题没有作答'), openOverlay()?.textContent.slice(0, 60));

  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  await settle();
  check('取消交卷 → 不发交卷请求', !called('POST', '/candidate/interviews/3/submit'));
  check('取消交卷 → 仍是可作答状态（交卷条还在）', has('.submit-bar') && !has('.submit-bar.is-frozen'));

  backend.reset();
  buttonIn(page(), '交卷').click();
  await settle();
  await settle();
  buttonIn(openOverlay(), '交卷').click();
  await settle();
  await settle();
  await settle();
  check('确认交卷 → 发出交卷请求', called('POST', '/candidate/interviews/3/submit'));
  check('交卷成功 → 输入框转为只读', page().querySelector('#candidate-answer')?.readOnly === true);
  check('交卷成功 → 交卷条冻结并显示后端返回的交卷时刻',
    has('.submit-bar.is-frozen') && text().includes('2026-09-21 11:20'), page().querySelector('.submit-bar')?.textContent);
  check('交卷成功 → 提示里报出提交了几题', toasts().some((t) => t.includes('2 题')), toasts().join(' | '));

  /* ---------- 13. 保存失败则中止交卷 ---------- */
  flags.answerStatus = 409;
  backend.reset();
  await go('#/candidate/interviews/3');
  page().querySelector('#candidate-answer').value = '这段存不下去';
  buttonIn(page(), '交卷').click();
  await settle();
  await settle();
  check('保存失败 → 不在「这段作答丢了」的前提下交卷', !called('POST', '/candidate/interviews/3/submit'));
  check('保存失败 → 弹出的是保存失败的提示',
    toasts().some((t) => t.includes('已交卷，不可修改作答')), toasts().join(' | '));
  flags.answerStatus = 200;

  /* ---------- 14. 反馈页：summary 档无总分 ---------- */
  backend.reset();
  await go('#/candidate/interviews/1/feedback');
  check('summary 档 → 没有总分块', !has('.feedback-total'));
  check('summary 档 → 说明里写清了「不含分数」', text().includes('不含分数'), text().includes('不含分数') ? 'ok' : '缺说明');
  check('反馈三个部分都在（结论 / 优点 / 待改进）',
    text().includes('综合结论') && text().includes('优点') && text().includes('待改进'));
  check('结论用的是后端重写的那一份（不含去留判断）',
    text().includes('在复杂问题的分析深度上还有提升空间')
      && !text().includes('建议进入下一轮') && !text().includes('不建议继续推进'));

  /* ---------- 15. 反馈页：full 档有总分，但**仍然没有**逐题分与雷达图 ---------- */
  flags.feedbackLevel = 'full';
  backend.reset();
  await go('#/candidate/interviews/1/feedback');
  check('full 档 → 出现总分块', has('.feedback-total'));
  check('full 档 → 总分是后端给的那个数', page().querySelector('.feedback-total .score-value')?.textContent === '6.5',
    page().querySelector('.feedback-total .score-value')?.textContent);
  check('full 档 → 说明跟着档位改口（不再说不含分数）', !text().includes('不含分数'));
  check('**任何档位都没有雷达图**', !has('svg.radar'));
  check('**任何档位都没有逐题分 / 维度分**（那两样结构上就不在下发范围里）',
    !text().includes('逐题评分') && !text().includes('维度得分') && !has('.dim-bar'));
  check('候选人侧任何位置都不出现 match_reason（那是 HR 的决策辅助信息）',
    !text().includes('match_reason') && !text().includes('简历匹配'));
  flags.feedbackLevel = 'summary';

  /* ---------- 16. 反馈未生成：409 是正常状态，不是错误 ---------- */
  flags.feedbackNotReady = true;
  clearToasts();
  backend.reset();
  await go('#/candidate/interviews/1/feedback');
  check('未评估 409 → 用空态说明「反馈还没出来」，不是报错样式',
    text().includes('反馈还没出来'), text().slice(0, 80));
  check('未评估 409 → 也不弹错误 toast', toasts().length === 0, toasts().join(' | '));
  flags.feedbackNotReady = false;

  /* ---------- 17. 注册：两步请求 + 自助注册关闭时的引导 ---------- */
  signOut('candidate');
  backend.reset();
  await go('#/candidate/login');
  await switchTo('注册');
  check('切到注册模式 → 提交按钮写「注册并登录」', submitBtn()?.textContent === '注册并登录', submitBtn()?.textContent);

  page().querySelector('#cand-username').value = 'newbie';
  page().querySelector('#cand-password').value = 'newbie12345';
  submitBtn().click();
  await settle();
  await settle();
  await settle();
  check('注册走两步：先 POST /auth/register，再 POST /auth/login',
    called('POST', '/auth/register') && called('POST', '/auth/login'));
  check('注册成功后落的是新账号的登录态', tokenIn('candidate') === 'newbie-token', String(tokenIn('candidate')));
  check('注册成功 → 同样落到候选人默认页', hash() === '#/candidate/interviews', hash());

  signOut('candidate');
  flags.selfRegisterDisabled = true;
  backend.reset();
  await go('#/candidate/login');
  await switchTo('注册');
  page().querySelector('#cand-username').value = 'newbie';
  page().querySelector('#cand-password').value = 'newbie12345';
  submitBtn().click();
  await settle();
  await settle();
  check('自助注册被关闭 → 不是弹一句报错，而是翻成「凭邀请码进入」那一版',
    text().includes('自助注册已关闭') && buttonIn(page(), '凭邀请码进入') !== undefined,
    text().slice(0, 80));
  check('自助注册被关闭 → 只发了注册那一步，没有继续去登录',
    called('POST', '/auth/register') && !called('POST', '/auth/login'));
  check('自助注册被关闭 → 不落任何登录态', tokenIn('candidate') === null, String(tokenIn('candidate')));

  buttonIn(page(), '凭邀请码进入').click();
  await settle();
  await settle();
  check('点「凭邀请码进入」→ 去到激活页', hash() === '#/candidate/activate', hash());
  flags.selfRegisterDisabled = false;

  /* ---------- 18. 激活：未登录可进（open 路由）+ 成功后自动登录 ---------- */
  signOut('candidate');
  backend.reset();
  await go('#/candidate/activate');
  check('未登录也能进激活页（它是本端唯一的 open 路由）', hash() === '#/candidate/activate', hash());
  check('未登录时用户名可编辑', page().querySelector('#activate-username')?.readOnly === false);

  page().querySelector('#activate-code').value = 'Kq3n8XvT2mLpRa7BwYc9dA';
  page().querySelector('#activate-username').value = 'newbie';
  page().querySelector('#activate-password').value = 'newbie12345';
  buttonIn(page(), '激活并进入面试').click();
  await settle();
  await settle();
  await settle();
  check('未登录时激活 → 接受邀请之后自动登录一次',
    called('POST', '/candidate/invitations/Kq3n8XvT2mLpRa7BwYc9dA/accept') && called('POST', '/auth/login'));
  check('自动登录成功 → 落登录态并进入面试', tokenIn('candidate') === 'newbie-token' && hash() === '#/candidate/interviews/3',
    `${tokenIn('candidate')} / ${hash()}`);

  /* ---------- 19. 激活失败：三种原因各自的落点 ---------- */
  signOut('candidate');
  flags.accept = {
    status: 401,
    body: { code: 'UNAUTHORIZED', message: '用户名或密码错误', detail: null },
  };
  backend.reset();
  await go('#/candidate/activate');
  page().querySelector('#activate-code').value = 'SomeCode1234567890abcd';
  page().querySelector('#activate-username').value = 'li.yun';
  page().querySelector('#activate-password').value = 'wrong-password';
  buttonIn(page(), '激活并进入面试').click();
  await settle();
  await settle();
  check('密码不符（这个端点唯一的 401）→ 报错落在**密码字段**上',
    inlineError('activate-password') === '用户名或密码错误', inlineError('activate-password'));
  check('密码不符 → 不落登录态、不跳走',
    tokenIn('candidate') === null && hash() === '#/candidate/activate', `${tokenIn('candidate')} / ${hash()}`);

  for (const message of ['邀请码无效或已失效', '用户名已被占用', '你已接受过该面试的邀请']) {
    flags.accept = { status: 409, body: { code: 'BUSINESS_ERROR', message, detail: null } };
    clearToasts();
    backend.reset();
    await go('#/candidate/activate');
    page().querySelector('#activate-code').value = 'SomeCode1234567890abcd';
    page().querySelector('#activate-username').value = 'li.yun';
    page().querySelector('#activate-password').value = 'cand12345678';
    buttonIn(page(), '激活并进入面试').click();
    await settle();
    await settle();
    check(`激活 409「${message}」→ 原样展示后端文案，前端不自行推断原因`,
      toasts().includes(message), toasts().join(' | '));
  }
  flags.accept = null;

  /* ---------- 20. 两端共存：先开 HR 页再切候选人页，请求带对 token ---------- */
  // 这条是 module-15 §6.4 的第 6 条，也是最容易漏测的一条：它检验
  // `session.setSide` 是否在**请求之前**执行。只在「先开候选人页」的路径上
  // 测试不会暴露时序错误。
  signInAs('hr', 'hr-token', ADMIN);
  signInAs('candidate', 'cand-token', CANDIDATE);

  backend.reset();
  await go('#/interviews');
  check('先开 HR 页 → HR 请求带 HR token',
    lastCall('GET', '/interviews')?.auth === 'Bearer hr-token',
    String(lastCall('GET', '/interviews')?.auth));

  backend.reset();
  await go('#/candidate/interviews');
  check('紧接切到候选人页 → 候选人请求带的是**候选人** token（时序正确）',
    lastCall('GET', '/candidate/interviews')?.auth === 'Bearer cand-token',
    String(lastCall('GET', '/candidate/interviews')?.auth));

  check('切到候选人页后，HR 端的登录态没被动过', tokenIn('hr') === 'hr-token', String(tokenIn('hr')));

  /* ---------- 21. 跨端串号：候选人 token 进不了 HR 页 ---------- */
  signOut('hr');
  clearToasts();
  await go('#/positions');
  check('只有候选人登录时进 HR 页 → 被送去 HR 登录页（不是吃一屏 403）',
    hash() === '#/login', hash());
  check('候选人登录态在这之后仍然完好', tokenIn('candidate') === 'cand-token', String(tokenIn('candidate')));

  /* ---------- 22. 退出登录只清自己那一端 ---------- */
  signInAs('hr', 'hr-token', ADMIN);
  await go('#/interviews');
  buttonIn(page().querySelector('.spine'), '退出登录').click();
  await settle();
  await settle();
  check('HR 端退出 → 清的是 hr.*', tokenIn('hr') === null, String(tokenIn('hr')));
  check('HR 端退出 → **不**动候选人端（两端各有各的登录态）',
    tokenIn('candidate') === 'cand-token', String(tokenIn('candidate')));

  /* ---------- 23. 收尾 ---------- */
  check('没有残留的弹窗', openOverlay() === null);
});
