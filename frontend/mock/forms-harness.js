/**
 * 表单一致性 —— Mock 联调测试（浏览器端）。
 *
 * 覆盖五个页面的表单：登录 / 岗位 / 题库 / 面试 / 面试详情。
 * 关注三件事：
 *   1. 本地校验的报错**落在字段下方**，不再弹一句泛泛的 toast
 *   2. 后端 400 的 detail.fields 落到同一处（API 文档 §12.1）
 *   3. 各输入框的 maxlength 与后端的字段约束对齐
 * 外加面试详情那个会抹掉数据的「清空」按钮。
 *
 * 运行：npm run dev 后打开 /mock/forms-harness.html
 */

import * as login from '../src/pages/login.js';
import * as positions from '../src/pages/positions.js';
import * as questions from '../src/pages/questions.js';
import * as interviews from '../src/pages/interviews.js';
import * as interviewDetail from '../src/pages/interview-detail.js';
import * as session from '../src/session.js';

/* ==========================================================================
   1. fetch 接管
   ========================================================================== */

let calls = [];
let handlers = {};

function matched(method, path) {
  const exact = handlers[`${method} ${path}`];
  if (exact) return exact;
  for (const [key, fn] of Object.entries(handlers)) {
    const [m, pattern] = key.split(' ');
    if (m !== method) continue;
    const pp = pattern.split('/').filter(Boolean);
    const ap = path.split('/').filter(Boolean);
    if (pp.length !== ap.length) continue;
    if (pp.every((part, i) => part.startsWith(':') || part === ap[i])) return fn;
  }
  return null;
}

window.fetch = async (url, options = {}) => {
  const method = (options.method || 'GET').toUpperCase();
  const path = String(url).replace(/^\/api/, '');
  const body = options.body ? JSON.parse(options.body) : undefined;
  calls.push({ method, path, body });

  const handler = matched(method, path);
  const result = handler
    ? handler({ method, path, body })
    : { status: 404, body: { code: 'NOT_FOUND', message: `未 mock 的路由：${method} ${path}`, detail: null } };

  return {
    ok: result.status >= 200 && result.status < 300,
    status: result.status,
    async json() {
      if (result.body === undefined) throw new Error('该响应无 JSON 体');
      return result.body;
    },
  };
};

/* ==========================================================================
   2. 脚手架
   ========================================================================== */

const results = [];
const errors = [];

function check(name, condition, detail = '') {
  // 条件允许传函数（惰性求值）。
  // 必须先判类型再调用 —— `Boolean(函数)` 恒为 true，
  // 直接 Boolean(condition) 会让惰性条件的断言**永远通过**（踩过一次）。
  const pass = Boolean(typeof condition === 'function' ? condition() : condition);
  results.push({ name, pass, detail });
}

const settle = (ms = 30) => new Promise((resolve) => setTimeout(resolve, ms));

function buttonWith(text, scope = document) {
  return [...scope.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
}

function toasts() {
  return [...document.querySelectorAll('.toast')].map((n) => n.textContent.trim());
}

function clearToasts() {
  document.querySelectorAll('.toast').forEach((n) => n.remove());
}

function overlay() {
  const all = [...document.querySelectorAll('.modal-overlay')];
  return all[all.length - 1] ?? null;
}

async function closeModal() {
  const box = overlay();
  if (!box) return;
  const cancel = buttonWith('取消', box);
  if (cancel) cancel.click();
  else box.remove();
  await settle();
}

/** 某个「字段标签」下方那条可见的错误文案；没显示则返回 null。 */
function fieldError(labelText, scope = document) {
  const field = [...scope.querySelectorAll('.field')].find(
    (f) => f.querySelector('.field-label')?.textContent.trim() === labelText,
  );
  const node = field?.querySelector('.field-error');
  return node && !node.hidden ? node.textContent.trim() : null;
}

function maxlengthOf(selector, scope = document) {
  return scope.querySelector(selector)?.getAttribute('maxlength') ?? null;
}

let container;

async function renderPage(page, params) {
  clearToasts();
  await page.render(container, params);
  await settle();
  // 页面自身的初始加载（GET /positions 等）不算「用户操作发的请求」，
  // 所以放在 render 之后再清 —— 否则「不该发请求」的断言永远是错的
  calls = [];
}

/* ==========================================================================
   3. 用例
   ========================================================================== */

function positionFixture() {
  return { id: 1, name: '后端工程师', jd: '负责后端。', evaluation_dimensions: ['沟通能力', '专业能力'], created_by: 1, created_at: '2026-09-17T10:00:00' };
}

function questionFixture() {
  return { id: 1, position_id: 1, category: '通用', dimension: '沟通能力', content: '谈谈你处理过的故障。', difficulty: 'medium', tags: [], source: 'bank', created_by: 1, created_at: '2026-09-17T10:00:00' };
}

function interviewDetailFixture(status = 'ongoing') {
  return {
    id: 1, position_id: 1, position_name: '后端工程师', candidate_name: '张三', candidate_contact: null,
    status, created_at: '2026-09-17T10:00:00', completed_at: null,
    question_count: 2, answered_count: 0, jd: '负责后端。', evaluation_dimensions: ['沟通能力', '专业能力'],
    questions: [
      { interview_question_id: 11, seq: 1, content: '题干一', dimension: '沟通能力', source: 'bank', answer: '已答内容', recorded_at: '2026-09-17T10:05:00' },
      { interview_question_id: 12, seq: 2, content: '题干二', dimension: '专业能力', source: 'bank', answer: null, recorded_at: null },
    ],
  };
}

async function run() {
  container = document.createElement('div');
  document.body.append(container);

  /* ===================== 登录 ===================== */

  session.clear();
  handlers = { 'POST /auth/login': () => ({ status: 200, body: { token: 't', user: { id: 1, username: 'admin', role: 'admin', is_active: true, created_at: '2026-08-02T09:00:00' } } }) };
  await renderPage(login);

  check('登录：用户名框 maxlength=50', maxlengthOf('#login-username') === '50', maxlengthOf('#login-username'));
  check('登录：密码框 maxlength=128', maxlengthOf('#login-password') === '128', maxlengthOf('#login-password'));

  buttonWith('登录').click();
  await settle();
  check('登录：空用户名 → 字段下方内联报错', fieldError('用户名') === '请填写用户名', String(fieldError('用户名')));
  check('登录：空用户名 → 不发请求', calls.length === 0, String(calls.length));
  check('登录：空用户名 → 不弹 toast', toasts().length === 0, toasts().join(' | '));

  document.querySelector('#login-username').value = 'admin';
  buttonWith('登录').click();
  await settle();
  check('登录：空密码 → 字段下方内联报错', fieldError('密码') === '请填写密码', String(fieldError('密码')));
  check('登录：空密码 → 不发请求', calls.length === 0, String(calls.length));

  // 后端 400 → 落到字段，而不是泛泛的「请求参数不合法」
  clearToasts();
  handlers['POST /auth/login'] = () => ({
    status: 400,
    body: { code: 'VALIDATION_ERROR', message: '请求参数不合法', detail: { fields: [{ field: 'username', message: '用户名过长', type: 'string_too_long' }] } },
  });
  document.querySelector('#login-password').value = 'x';
  buttonWith('登录').click();
  await settle();
  check('登录：后端 400 → 落到 username 字段', fieldError('用户名') === '用户名过长', String(fieldError('用户名')));
  check('登录：后端 400 → 不再弹通用 toast', toasts().length === 0, toasts().join(' | '));

  // 401 是业务错误，仍用后端文案 toast
  clearToasts();
  handlers['POST /auth/login'] = () => ({ status: 401, body: { code: 'UNAUTHORIZED', message: '用户名或密码错误', detail: null } });
  buttonWith('登录').click();
  await settle();
  check('登录：401 → 用后端 message 弹 toast', toasts().includes('用户名或密码错误'), toasts().join(' | '));

  /* ===================== 岗位 ===================== */

  session.save('t', { id: 1, username: 'admin', role: 'admin', is_active: true, created_at: '2026-08-02T09:00:00' });
  handlers = {
    'GET /positions': () => ({ status: 200, body: [] }),
    'POST /positions': () => ({ status: 201, body: positionFixture() }),
  };
  await renderPage(positions);
  buttonWith('创建岗位').click();
  await settle();

  check('岗位：JD 框 maxlength=10000', () => maxlengthOf('#position-jd', overlay()) === '10000', maxlengthOf('#position-jd', overlay()));
  check('岗位：名称框 maxlength=100', () => maxlengthOf('#position-name', overlay()) === '100', maxlengthOf('#position-name', overlay()));

  buttonWith('创建岗位', overlay()).click();
  await settle();
  check('岗位：空名称 → 内联报错', fieldError('岗位名称') === '请填写岗位名称', String(fieldError('岗位名称')));
  check('岗位：空名称 → 不发请求', calls.length === 0, String(calls.length));

  overlay().querySelector('#position-name').value = '后端工程师';
  buttonWith('创建岗位', overlay()).click();
  await settle();
  check('岗位：空 JD → 内联报错', fieldError('岗位描述（JD）') === '请填写岗位描述', String(fieldError('岗位描述（JD）')));

  // 维度校验仍走原来的内联错误出口。
  // 注意：维度编辑器内部数组靠 input 事件同步 —— 只改 .value 不会触发，
  // 编辑器仍以为自己是默认的那两个维度，于是校验会通过、请求会真的发出去。
  overlay().querySelector('#position-jd').value = '负责后端。';
  const dimInput = overlay().querySelector('.dim-editor-row .input');
  dimInput.value = '   ';
  dimInput.dispatchEvent(new Event('input'));
  buttonWith('创建岗位', overlay()).click();
  await settle();
  check('岗位：维度为空 → 维度编辑器下方报错', fieldError('评估维度') === '评估维度不能为空', String(fieldError('评估维度')));
  check('岗位：维度为空 → 不发请求', calls.length === 0, String(calls.length));

  // 409 重名 → 后端文案
  clearToasts();
  handlers['POST /positions'] = () => ({ status: 409, body: { code: 'BUSINESS_ERROR', message: '该岗位名称已存在', detail: null } });
  dimInput.value = '沟通能力';
  dimInput.dispatchEvent(new Event('input'));
  buttonWith('创建岗位', overlay()).click();
  await settle();
  await settle();
  check('岗位：409 → 用后端 message 弹 toast', toasts().includes('该岗位名称已存在'), toasts().join(' | '));
  check('岗位：409 → 弹窗保持打开', overlay() !== null);
  await closeModal();

  /* ===================== 题库 ===================== */

  handlers = {
    'GET /positions': () => ({ status: 200, body: [positionFixture()] }),
    'GET /questions': () => ({ status: 200, body: [] }),
    'POST /questions': () => ({ status: 201, body: questionFixture() }),
  };
  await renderPage(questions);
  buttonWith('创建题目').click();
  await settle();

  check('题库：题干 maxlength=2000', () => maxlengthOf('#question-content', overlay()) === '2000', maxlengthOf('#question-content', overlay()));

  buttonWith('创建题目', overlay()).click();
  await settle();
  check('题库：题干不足 5 字 → 内联报错', fieldError('题干') === '题干至少 5 个字', String(fieldError('题干')));
  check('题库：题干不足 → 不发请求', calls.length === 0, String(calls.length));

  overlay().querySelector('#question-content').value = '这是一道足够长的题干内容。';
  overlay().querySelector('#question-tags').value = Array.from({ length: 11 }, (_, i) => `标签${i}`).join('、');
  buttonWith('创建题目', overlay()).click();
  await settle();
  check(
    '题库：标签超过 10 个 → 内联报错',
    (fieldError('标签') ?? '').startsWith('标签最多 10 个'),
    String(fieldError('标签')),
  );
  check('题库：标签超限 → 不发请求', calls.length === 0, String(calls.length));

  overlay().querySelector('#question-tags').value = '这是一个超过二十个字符的很长很长的标签名称';
  buttonWith('创建题目', overlay()).click();
  await settle();
  check(
    '题库：单个标签超过 20 字 → 内联报错',
    (fieldError('标签') ?? '').startsWith('单个标签不能超过 20 个字符'),
    String(fieldError('标签')),
  );

  clearToasts();
  overlay().querySelector('#question-tags').value = '故障、沟通';
  calls = [];
  buttonWith('创建题目', overlay()).click();
  await settle();
  await settle();
  const post = calls.find((c) => c.method === 'POST' && c.path === '/questions');
  check('题库：合法提交 → 发出 POST /questions', Boolean(post));
  check('题库：标签按顿号拆成数组', JSON.stringify(post?.body?.tags) === '["故障","沟通"]', JSON.stringify(post?.body?.tags));
  await closeModal();

  /* ===================== 面试列表 ===================== */

  handlers = {
    'GET /interviews': () => ({ status: 200, body: [] }),
    'GET /positions': () => ({ status: 200, body: [positionFixture()] }),
    'POST /interviews': () => ({ status: 201, body: interviewDetailFixture() }),
  };
  await renderPage(interviews);
  buttonWith('创建面试').click();
  await settle();

  check('面试：姓名框 maxlength=100', () => maxlengthOf('#new-interview-name', overlay()) === '100', maxlengthOf('#new-interview-name', overlay()));
  check('面试：联系框 maxlength=200', () => maxlengthOf('#new-interview-contact', overlay()) === '200', maxlengthOf('#new-interview-contact', overlay()));

  buttonWith('创建并出题', overlay()).click();
  await settle();
  check('面试：空姓名 → 内联报错', fieldError('候选人姓名') === '请填写候选人姓名', String(fieldError('候选人姓名')));
  // 注意：打开创建弹窗本身会 GET /positions（填岗位下拉），那是正常的；
  // 这里要断的是「没有发出创建请求」
  check(
    '面试：空姓名 → 不发创建请求',
    calls.filter((c) => c.method === 'POST').length === 0,
    JSON.stringify(calls.map((c) => `${c.method} ${c.path}`)),
  );

  // 502 AI 出题失败 → 后端文案 toast，且弹窗可重试
  clearToasts();
  handlers['POST /interviews'] = () => ({ status: 502, body: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试', detail: null } });
  overlay().querySelector('#new-interview-name').value = '张三';
  buttonWith('创建并出题', overlay()).click();
  await settle();
  await settle();
  check('面试：502 → 用后端 message 弹 toast', toasts().includes('AI 服务调用失败，请稍后重试'), toasts().join(' | '));
  check('面试：502 → 弹窗保持打开可重试', overlay() !== null);
  check(
    '面试：502 → 按钮文案恢复',
    Boolean(buttonWith('创建并出题', overlay())),
    [...overlay().querySelectorAll('button')].map((b) => b.textContent).join(','),
  );
  await closeModal();

  /* ===================== 面试详情 ===================== */

  handlers = {
    'GET /interviews/:id': () => ({ status: 200, body: interviewDetailFixture('ongoing') }),
    'POST /interviews/:id/answers': () => ({ status: 200, body: { interview_question_id: 11, seq: 1, content: '', dimension: '沟通能力', source: 'bank', answer: '', recorded_at: '2026-09-17T10:09:00' } }),
  };
  await renderPage(interviewDetail, { id: '1' });

  check('详情：回答框 maxlength=10000', maxlengthOf('#answer-input') === '10000', maxlengthOf('#answer-input'));

  // 未修改就失焦 → 不发请求
  calls = [];
  document.querySelector('#answer-input').dispatchEvent(new Event('blur'));
  await settle();
  check('详情：没改动就失焦 → 不发保存请求', calls.length === 0, String(calls.length));

  // 改动后失焦 → 保存
  const textarea = document.querySelector('#answer-input');
  textarea.value = '改过的回答';
  textarea.dispatchEvent(new Event('blur'));
  await settle();
  check(
    '详情：改动后失焦 → 自动保存',
    calls.some((c) => c.method === 'POST' && c.path === '/interviews/1/answers'),
    JSON.stringify(calls.map((c) => c.path)),
  );

  // 清空要先确认
  clearToasts();
  calls = [];
  buttonWith('清空').click();
  await settle();
  check('详情：点「清空」→ 先弹二次确认', overlay() !== null);
  check(
    '详情：确认文案说明不可恢复',
    overlay()?.textContent.includes('无法恢复') ?? false,
    overlay()?.textContent.slice(0, 60),
  );

  buttonWith('取消', overlay()).click();
  await settle();
  check('详情：取消清空 → 不发请求', calls.length === 0, String(calls.length));
  check('详情：取消清空 → 文本仍在', document.querySelector('#answer-input').value === '改过的回答', document.querySelector('#answer-input').value);

  buttonWith('清空').click();
  await settle();
  buttonWith('清空', overlay()).click();
  await settle();
  const clearCall = calls.find((c) => c.method === 'POST');
  check('详情：确认清空 → 发保存请求且内容为空', clearCall?.body?.content === '', JSON.stringify(clearCall?.body));

  // 非 ongoing → 只读 + 提示
  handlers['GET /interviews/:id'] = () => ({ status: 200, body: interviewDetailFixture('completed') });
  await renderPage(interviewDetail, { id: '1' });
  check('详情：非进行中 → 回答框只读', document.querySelector('#answer-input').readOnly === true, String(document.querySelector('#answer-input').readOnly));
  check('详情：非进行中 → 给出回退提示', document.body.textContent.includes('需先回退到进行中才能修改回答'));
  check('详情：非进行中 → 不显示「清空」按钮', !buttonWith('清空'));
}

/* ==========================================================================
   4. 出结果
   ========================================================================== */

function paint() {
  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;

  const head = document.createElement('h1');
  head.textContent = `表单一致性 Mock 测试：${passed} 通过 / ${failed} 失败`;
  head.className = failed === 0 ? 'ok' : 'bad';

  const table = document.createElement('table');
  table.className = 'report';
  for (const r of results) {
    const tr = document.createElement('tr');
    tr.className = r.pass ? 'pass' : 'fail';
    for (const text of [r.pass ? 'PASS' : 'FAIL', r.name, r.detail]) {
      const td = document.createElement('td');
      td.textContent = text;
      tr.append(td);
    }
    table.append(tr);
  }

  const box = document.getElementById('results');
  box.replaceChildren(head, table);
  if (errors.length) {
    const pre = document.createElement('pre');
    pre.textContent = errors.join('\n');
    box.append(pre);
  }
  document.title = failed === 0 ? `MOCK-ALL-PASS ${passed}` : `MOCK-FAIL ${failed}/${results.length}`;
}

window.addEventListener('error', (e) => errors.push(`uncaught: ${e.message}`));
window.addEventListener('unhandledrejection', (e) => errors.push(`unhandled rejection: ${e.reason}`));

run()
  .catch((error) => errors.push(`用例执行中断: ${error?.stack || error}`))
  .finally(paint);
