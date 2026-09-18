/**
 * 用户管理模块 —— Mock 联调测试（浏览器端）。
 *
 * 为什么不是 Vitest：module-07 §8.1 明确「不引入 DOM 测试框架（jsdom / Testing
 * Library）」，而本模块的价值恰恰在 DOM 行为 —— 二次确认、字段级报错、按钮禁用。
 * 所以这里用页面里的真实代码 + 拦截 fetch 的假后端来跑，既不新增依赖，
 * 又比手工点一遍更可靠（每次改动都能重跑）。
 *
 * 运行：npm run dev 后打开 /mock/users-harness.html
 */

import * as users from '../src/pages/users.js';
import * as session from '../src/session.js';

// 页面需要「已登录的 admin」才会渲染出用户管理；id=1 与 mock 里的 admin 对应，
// 用来验证「自己那一行不可操作」。
session.save('mock-token', {
  id: 1,
  username: 'admin',
  role: 'admin',
  is_active: true,
  created_at: '2026-08-02T09:00:00',
});

/* ==========================================================================
   1. 假后端 —— 拦截 fetch，按「METHOD 路径」返回预设响应
   ========================================================================== */

let USERS = [];

function seedUsers() {
  return [
    { id: 1, username: 'admin', role: 'admin', is_active: true, created_at: '2026-08-02T09:00:00' },
    { id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00' },
    { id: 3, username: 'zhao.ming', role: 'hr', is_active: true, created_at: '2026-09-01T09:00:00' },
    { id: 4, username: 'chen.xi', role: 'hr', is_active: false, created_at: '2026-09-05T09:00:00' },
    { id: 5, username: 'sun.qiang', role: 'admin', is_active: true, created_at: '2026-09-06T09:00:00' },
  ];
}

/** 每条可被用例覆盖的响应：{ status, body } */
let handlers = {};
let calls = [];

function setHandlers(map) {
  handlers = map;
}

/** 按「METHOD 路径」取处理器，支持 `:id` 这类占位段。 */
function resolveHandler(method, path) {
  const exact = handlers[`${method} ${path}`];
  if (exact) return exact;

  for (const [key, fn] of Object.entries(handlers)) {
    const [keyMethod, pattern] = key.split(' ');
    if (keyMethod !== method) continue;

    const patternParts = pattern.split('/').filter(Boolean);
    const pathParts = path.split('/').filter(Boolean);
    if (patternParts.length !== pathParts.length) continue;

    const matched = patternParts.every(
      (part, i) => part.startsWith(':') || part === pathParts[i],
    );
    if (matched) return fn;
  }
  return null;
}

window.fetch = async (url, options = {}) => {
  const method = (options.method || 'GET').toUpperCase();
  const path = String(url).replace(/^\/api/, '');
  const body = options.body ? JSON.parse(options.body) : undefined;

  calls.push({ method, path, body });

  const handler = resolveHandler(method, path);
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

/** 默认（成功）行为。用例可临时覆盖任意一条。 */
function defaultHandlers() {
  return {
    'GET /users': () => ({ status: 200, body: USERS }),
    'POST /users': ({ body }) => {
      const created = {
        id: USERS.length + 1,
        username: body.username,
        role: body.role,
        is_active: true,
        created_at: '2026-09-18T10:00:00',
      };
      USERS = [...USERS, created];
      return { status: 201, body: created };
    },
    'PATCH /users/:id': ({ path, body }) => {
      const id = Number(path.split('/')[2]);
      const index = USERS.findIndex((u) => u.id === id);
      if (index === -1) {
        return { status: 404, body: { code: 'NOT_FOUND', message: '用户不存在', detail: null } };
      }
      USERS[index] = { ...USERS[index], ...body };
      return { status: 200, body: USERS[index] };
    },
  };
}

/* ==========================================================================
   2. 测试脚手架
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

const settle = () => new Promise((resolve) => setTimeout(resolve, 25));

function clearToasts() {
  document.querySelectorAll('.toast').forEach((node) => node.remove());
}

function toasts() {
  return [...document.querySelectorAll('.toast')].map((n) => n.textContent.trim());
}

function rows() {
  return [...document.querySelectorAll('.main tbody tr')];
}

function rowOf(username) {
  return rows().find((tr) => tr.querySelector('strong')?.textContent.trim() === username);
}

function buttonIn(scope, text) {
  return [...scope.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
}

function openOverlay() {
  const all = [...document.querySelectorAll('.modal-overlay')];
  return all[all.length - 1] ?? null;
}

/** 关掉可能还开着的弹窗（点「取消」，让 confirmModal 的 Promise 正常结束）。 */
async function closeAnyModal() {
  const overlay = openOverlay();
  if (!overlay) return;
  const cancel = buttonIn(overlay, '取消');
  if (cancel) cancel.click();
  else overlay.remove();
  await settle();
}

function fieldErrorOf(labelText) {
  const field = [...document.querySelectorAll('.modal .field')].find(
    (f) => f.querySelector('.field-label')?.textContent.trim() === labelText,
  );
  if (!field) return null;
  const node = field.querySelector('.field-error');
  if (!node || node.hidden) return null;
  return node.textContent.trim();
}

function fillCreateForm({ username, password, role }) {
  const overlay = openOverlay();
  if (username !== undefined) overlay.querySelector('#user-username').value = username;
  if (password !== undefined) overlay.querySelector('#user-password').value = password;
  if (role !== undefined) overlay.querySelector('#user-role').value = role;
}

async function openCreateAndFill(fields) {
  buttonIn(document.querySelector('.main'), '创建用户').click();
  await settle();
  fillCreateForm(fields);
  return openOverlay();
}

/* ==========================================================================
   3. 用例
   ========================================================================== */

async function run() {
  const container = document.createElement('div');
  container.id = 'harness-root';
  document.body.append(container);

  const renderPage = async () => {
    await users.render(container);
    await settle();
  };

  // ---------- 列表渲染 ----------
  USERS = seedUsers();
  setHandlers(defaultHandlers());
  calls = [];
  await renderPage();

  check('列表渲染 5 行', rows().length === 5, `实际 ${rows().length} 行`);
  check(
    '按 id 升序，与接口返回顺序一致',
    rows().map((tr) => tr.querySelector('strong').textContent.trim()).join(',') ===
      'admin,li.yan,zhao.ming,chen.xi,sun.qiang',
    rows().map((tr) => tr.querySelector('strong').textContent.trim()).join(','),
  );

  const adminRow = rowOf('admin');
  const chenRow = rowOf('chen.xi');
  const tagsOf = (tr) => [...tr.querySelectorAll('.tag')].map((t) => t.textContent.trim());

  check('admin 行标签 = [管理员, 已启用]', tagsOf(adminRow).join(',') === '管理员,已启用', tagsOf(adminRow).join(','));
  check('chen.xi 行标签 = [HR, 已禁用]', tagsOf(chenRow).join(',') === 'HR,已禁用', tagsOf(chenRow).join(','));
  check('创建时间按 YYYY-MM-DD 渲染', adminRow.children[3].textContent.trim() === '2026-08-02', adminRow.children[3].textContent.trim());

  // ---------- 自身保护 ----------
  const adminButtons = [...adminRow.querySelectorAll('button')];
  check('自己那一行两个按钮都禁用', adminButtons.every((b) => b.disabled), adminButtons.map((b) => b.disabled).join(','));
  check('自己那一行带「（你自己）」标记', adminRow.textContent.includes('（你自己）'));
  check(
    '禁用态带说明性 title',
    adminButtons[0].title === '不能修改自己的角色' && adminButtons[1].title === '不能禁用自己的账号',
    `${adminButtons[0].title} / ${adminButtons[1].title}`,
  );

  const liyanButtons = [...rowOf('li.yan').querySelectorAll('button')];
  check('他人那一行按钮可用', liyanButtons.every((b) => !b.disabled));

  // ---------- 创建：字段级校验 ----------
  clearToasts();
  await openCreateAndFill({ username: '', password: '12345678', role: 'hr' });
  calls = [];
  buttonIn(openOverlay(), '创建用户').click();
  await settle();

  check('空用户名 → 用户名下方内联报错', fieldErrorOf('用户名') === '请填写用户名', String(fieldErrorOf('用户名')));
  check('空用户名 → 不发请求', calls.length === 0, `实际 ${calls.length} 次`);
  check('空用户名 → 不弹 toast', toasts().length === 0, toasts().join(' | '));
  await closeAnyModal();

  clearToasts();
  await openCreateAndFill({ username: 'new.hr', password: '123', role: 'hr' });
  calls = [];
  buttonIn(openOverlay(), '创建用户').click();
  await settle();

  check('密码不足 8 位 → 密码下方内联报错', fieldErrorOf('初始密码') === '密码长度不能少于 8 位', String(fieldErrorOf('初始密码')));
  check('密码不足 8 位 → 不发请求', calls.length === 0, `实际 ${calls.length} 次`);
  await closeAnyModal();

  await openCreateAndFill({});
  check(
    '密码框 maxlength=128',
    openOverlay().querySelector('#user-password').getAttribute('maxlength') === '128',
    String(openOverlay().querySelector('#user-password').getAttribute('maxlength')),
  );
  check(
    '用户名框 maxlength=50',
    openOverlay().querySelector('#user-username').getAttribute('maxlength') === '50',
    String(openOverlay().querySelector('#user-username').getAttribute('maxlength')),
  );
  await closeAnyModal();

  // ---------- 创建：成功 ----------
  clearToasts();
  const before = USERS.length;
  await openCreateAndFill({ username: 'new.hr', password: 'hr12345678', role: 'hr' });
  calls = [];
  buttonIn(openOverlay(), '创建用户').click();
  await settle();
  await settle();

  const postCall = calls.find((c) => c.method === 'POST' && c.path === '/users');
  check('创建成功 → 发出 POST /api/users', Boolean(postCall));
  check(
    '创建成功 → 请求体只含 username/password/role',
    postCall && JSON.stringify(postCall.body) === JSON.stringify({ username: 'new.hr', password: 'hr12345678', role: 'hr' }),
    JSON.stringify(postCall?.body),
  );
  check('创建成功 → 弹窗关闭', openOverlay() === null);
  check('创建成功 → 提示「用户已创建」', toasts().some((t) => t.includes('用户已创建')), toasts().join(' | '));
  check('创建成功 → 列表重新拉取（新增一行）', USERS.length === before + 1 && rows().length === before + 1, `${USERS.length} / ${rows().length}`);
  await closeAnyModal();

  // ---------- 创建：后端 400 → detail.fields 落到字段 ----------
  clearToasts();
  setHandlers({
    ...defaultHandlers(),
    'POST /users': () => ({
      status: 400,
      body: {
        code: 'VALIDATION_ERROR',
        message: '请求参数不合法',
        detail: { fields: [{ field: 'username', message: 'String should have at most 50 characters', type: 'string_too_long' }] },
      },
    }),
  });
  await openCreateAndFill({ username: 'x'.repeat(50), password: 'hr12345678', role: 'hr' });
  buttonIn(openOverlay(), '创建用户').click();
  await settle();
  await settle();

  check(
    '后端 400 → 错误落到 username 字段',
    fieldErrorOf('用户名') === 'String should have at most 50 characters',
    String(fieldErrorOf('用户名')),
  );
  check('后端 400 → 不再弹通用 toast（同一个错误不说两遍）', toasts().length === 0, toasts().join(' | '));
  check('后端 400 → 弹窗保持打开', openOverlay() !== null);
  await closeAnyModal();

  // ---------- 创建：409 重名 → 用后端文案 toast ----------
  clearToasts();
  setHandlers({
    ...defaultHandlers(),
    'POST /users': () => ({
      status: 409,
      body: { code: 'BUSINESS_ERROR', message: '用户名已存在', detail: null },
    }),
  });
  await openCreateAndFill({ username: 'li.yan', password: 'hr12345678', role: 'hr' });
  buttonIn(openOverlay(), '创建用户').click();
  await settle();
  await settle();

  check('409 重名 → toast 显示后端 message', toasts().includes('用户名已存在'), toasts().join(' | '));
  check('409 重名 → 不落到字段（它是业务冲突，不是字段格式错）', fieldErrorOf('用户名') === null, String(fieldErrorOf('用户名')));
  await closeAnyModal();

  // ---------- 禁用：二次确认 ----------
  setHandlers(defaultHandlers());
  USERS = seedUsers();
  await renderPage();
  clearToasts();

  buttonIn(rowOf('li.yan'), '禁用').click();
  await settle();
  check('点「禁用」→ 先弹出二次确认', openOverlay() !== null);
  check(
    '确认文案说明后果（会被立即登出）',
    openOverlay()?.textContent.includes('立即被登出') ?? false,
    openOverlay()?.textContent.slice(0, 60),
  );

  calls = [];
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('确认框点「取消」→ 不发 PATCH', calls.length === 0, `实际 ${calls.length} 次`);
  check('确认框点「取消」→ 状态未变', USERS.find((u) => u.username === 'li.yan').is_active === true);

  buttonIn(rowOf('li.yan'), '禁用').click();
  await settle();
  calls = [];
  buttonIn(openOverlay(), '禁用').click();
  await settle();
  await settle();

  const patch1 = calls.find((c) => c.method === 'PATCH');
  check('确认后 → 发出 PATCH /users/2', patch1?.path === '/users/2', String(patch1?.path));
  check('确认后 → 请求体为 { is_active: false }', JSON.stringify(patch1?.body) === '{"is_active":false}', JSON.stringify(patch1?.body));
  check('确认后 → 列表已刷新为「已禁用」', tagsOf(rowOf('li.yan')).includes('已禁用'), tagsOf(rowOf('li.yan')).join(','));

  // ---------- 启用：不确认，直接执行 ----------
  clearToasts();
  buttonIn(rowOf('chen.xi'), '启用').click();
  await settle();
  check('点「启用」→ 不弹确认框（是给回权限，不拿走东西）', openOverlay() === null);
  check('点「启用」→ 直接发 PATCH', calls.some((c) => c.method === 'PATCH' && c.path === '/users/4'), calls.map((c) => c.path).join(','));

  // ---------- 降级：二次确认 ----------
  USERS = seedUsers();
  await renderPage();
  clearToasts();

  buttonIn(rowOf('sun.qiang'), '降为 HR').click();
  await settle();
  check('点「降为 HR」→ 先弹出二次确认', openOverlay() !== null);
  check(
    '降级确认文案提到「用户管理」入口消失',
    openOverlay()?.textContent.includes('用户管理') ?? false,
    openOverlay()?.textContent.slice(0, 70),
  );

  calls = [];
  buttonIn(openOverlay(), '降为 HR').click();
  await settle();
  await settle();
  const patch2 = calls.find((c) => c.method === 'PATCH');
  check('降级确认后 → PATCH /users/5 { role: hr }', patch2?.path === '/users/5' && JSON.stringify(patch2?.body) === '{"role":"hr"}', `${patch2?.path} ${JSON.stringify(patch2?.body)}`);
  check('降级后 → 该行按钮变为「升为管理员」', Boolean(buttonIn(rowOf('sun.qiang'), '升为管理员')));

  // ---------- 升级：不确认 ----------
  clearToasts();
  calls = [];
  buttonIn(rowOf('sun.qiang'), '升为管理员').click();
  await settle();
  check('点「升为管理员」→ 不弹确认框', openOverlay() === null);
  check('点「升为管理员」→ 直接发 PATCH { role: admin }', calls.some((c) => JSON.stringify(c.body) === '{"role":"admin"}'), JSON.stringify(calls.map((c) => c.body)));

  // ---------- 自己那一行不可操作 ----------
  USERS = seedUsers();
  await renderPage();
  calls = [];
  const selfAdmin = [...rowOf('admin').querySelectorAll('button')];
  selfAdmin.forEach((b) => b.click());
  await settle();
  check('点自己那一行的按钮 → 不发任何请求', calls.length === 0, `实际 ${calls.length} 次`);
  check('点自己那一行的按钮 → 不出确认框', openOverlay() === null);

  // ---------- 加载失败 ----------
  setHandlers({
    'GET /users': () => ({ status: 403, body: { code: 'FORBIDDEN', message: '无权限执行此操作', detail: null } }),
  });
  calls = [];
  await renderPage();
  check('加载失败 → 显示错误空态而非空白表格', container.textContent.includes('用户加载失败'), container.textContent.slice(0, 60));
  check('加载失败 → 展示后端 message', container.textContent.includes('无权限执行此操作'));
}

/* ==========================================================================
   4. 渲染结果
   ========================================================================== */

function paint() {
  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;

  const head = document.createElement('h1');
  head.textContent = `用户模块 Mock 测试：${passed} 通过 / ${failed} 失败`;
  head.className = failed === 0 ? 'ok' : 'bad';

  const table = document.createElement('table');
  table.className = 'report';
  for (const r of results) {
    const tr = document.createElement('tr');
    tr.className = r.pass ? 'pass' : 'fail';
    const a = document.createElement('td');
    a.textContent = r.pass ? 'PASS' : 'FAIL';
    const b = document.createElement('td');
    b.textContent = r.name;
    const c = document.createElement('td');
    c.textContent = r.detail;
    tr.append(a, b, c);
    table.append(tr);
  }

  const box = document.getElementById('results');
  box.replaceChildren(head, table);
  if (errors.length) {
    const pre = document.createElement('pre');
    pre.textContent = errors.join('\n');
    box.append(pre);
  }
  // 供 headless 抓取用
  document.title = failed === 0 ? `MOCK-ALL-PASS ${passed}` : `MOCK-FAIL ${failed}/${results.length}`;
}

window.addEventListener('error', (e) => errors.push(`uncaught: ${e.message}`));
window.addEventListener('unhandledrejection', (e) => errors.push(`unhandled rejection: ${e.reason}`));

run()
  .catch((error) => errors.push(`用例执行中断: ${error?.stack || error}`))
  .finally(paint);
