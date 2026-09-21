/**
 * 准备助手 Mock 联调测试。
 *
 * 这个测试台的核心是**字段名**。原型 `standalone.html` 里用的是
 * `minutes` / `points` / `focus` / `followups`，而真实后端 schema
 * （`backend/app/interview/schemas.py`）要求的是
 * `duration_min` / `notes` / `point` / `follow_ups`，并且 `seq` 是必填。
 * 两边一起错所以原型自洽，照搬进 `src/` 会**保存必然 400、读取全是空白**。
 *
 * 所以假后端这里**按 Pydantic 的行为校验请求体**（缺字段就 400 并点名），
 * 而不是来什么收什么 —— 否则字段名写错了测试台照样全绿。
 *
 * 运行：npm run dev 后打开 /mock/prep-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import {
  buttonIn, clearToasts, closeAnyModal, createReport, installFakeBackend,
  openOverlay, settle, toasts,
} from './harness.js';

const report = createReport('准备助手 Mock 测试');
const { check } = report;

session.setSide('hr');
session.save('hr-token', {
  id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
});

/* ---------- 假数据 ---------- */

const DIMS = ['专业能力', '沟通能力'];

let STATUS = 'ongoing';

function detail() {
  return {
    id: 1, position_id: 1, position_name: '后端工程师', candidate_name: '张三',
    candidate_contact: '13800000000', status: STATUS,
    created_at: '2026-09-08T10:00:00', completed_at: null,
    question_count: 3, answered_count: 0, jd: '……',
    evaluation_dimensions: DIMS, resume_id: null,
    questions: [
      { interview_question_id: 101, seq: 1, content: '第 1 题的题干。', dimension: '专业能力', source: 'bank', answer: null, recorded_at: null },
    ],
  };
}

/** 一份合法的准备提纲 —— 字段名全部按后端 schema。 */
function prepFixture() {
  return {
    interview_id: 1,
    outline: [
      { seq: 1, phase: '开场与自我介绍', duration_min: 5, notes: '说明流程与时长' },
      { seq: 2, phase: '技术深挖', duration_min: 25, notes: '围绕本场题目追问到具体做法' },
    ],
    focus_points: [
      { dimension: '专业能力', point: '分布式事务的取舍', reason: '简历中主导过跨库改造' },
    ],
    question_plan: [
      { question: '讲一次你处理线上故障的过程', intent: '考察排查思路', follow_ups: ['为什么先看这个指标', '有没有别的方案'] },
    ],
    generated_at: '2026-09-21T10:20:00',
    edited_at: null,
  };
}

let PREP = -1;          // -1 = 未生成（GET 返回 404），否则是一份提纲
let PREP_FAIL = null;   // 非 404 的读取失败
let LAST_PUT = null;
let PRINTED = 0;

/**
 * 按 Pydantic 的严格程度校验 PUT 请求体：**缺字段就 400 并点名**。
 * 宽松地「来什么收什么」会让字段名写错也全绿 —— 那就白测了。
 */
const OUTLINE_KEYS = ['seq', 'phase', 'duration_min', 'notes'];
const FOCUS_KEYS = ['dimension', 'point', 'reason'];
const PLAN_KEYS = ['question', 'intent', 'follow_ups'];

function missingKeys(list, keys, prefix) {
  const fields = [];
  list.forEach((item, index) => {
    for (const key of keys) {
      if (!(key in (item ?? {}))) fields.push({ field: `${prefix}[${index}].${key}`, message: 'Field required', type: 'missing' });
    }
  });
  return fields;
}

function validatePrepBody(body) {
  const fields = [];
  if (!Array.isArray(body?.outline)) fields.push({ field: 'outline', message: 'Field required', type: 'missing' });
  if (!Array.isArray(body?.focus_points)) fields.push({ field: 'focus_points', message: 'Field required', type: 'missing' });
  if (!Array.isArray(body?.question_plan)) fields.push({ field: 'question_plan', message: 'Field required', type: 'missing' });
  if (fields.length) return fields;
  return [
    ...missingKeys(body.outline, OUTLINE_KEYS, 'outline'),
    ...missingKeys(body.focus_points, FOCUS_KEYS, 'focus_points'),
    ...missingKeys(body.question_plan, PLAN_KEYS, 'question_plan'),
  ];
}

function defaultHandlers() {
  return {
    'GET /auth/me': () => ({ status: 200, body: { id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00' } }),
    'GET /interviews/:id': () => ({ status: 200, body: detail() }),

    'GET /interviews/:id/prep': () => {
      if (PREP_FAIL && PREP_FAIL.status !== 404) return PREP_FAIL;
      if (PREP === -1) return { status: 404, body: { code: 'NOT_FOUND', message: '准备提纲尚未生成', detail: null } };
      return { status: 200, body: PREP };
    },

    'POST /interviews/:id/prep': () => {
      if (STATUS !== 'draft' && STATUS !== 'ongoing') {
        return { status: 409, body: { code: 'BUSINESS_ERROR', message: '面试已进入评估或已完成，不可再生成准备提纲', detail: null } };
      }
      // 重新生成 = 整体覆盖，edited_at 置回 null
      PREP = { ...prepFixture(), outline: [{ seq: 1, phase: 'AI 生成的阶段', duration_min: 10, notes: 'AI 写的要点' }] };
      return { status: 200, body: PREP };
    },

    'PUT /interviews/:id/prep': ({ body }) => {
      LAST_PUT = body;
      const fields = validatePrepBody(body);
      if (fields.length) {
        return { status: 400, body: { code: 'VALIDATION_ERROR', message: '请求参数不合法', detail: { fields } } };
      }
      if (PREP === -1) {
        return { status: 404, body: { code: 'NOT_FOUND', message: '准备提纲尚未生成', detail: null } };
      }
      if (STATUS !== 'draft' && STATUS !== 'ongoing') {
        return { status: 409, body: { code: 'BUSINESS_ERROR', message: '面试已进入评估或已完成，不可再编辑准备提纲', detail: null } };
      }
      // 编辑后 edited_at 置位，generated_at 不变
      PREP = { ...PREP, ...body, edited_at: '2026-09-21T11:00:00' };
      return { status: 200, body: PREP };
    },
  };
}

const backend = installFakeBackend(defaultHandlers());
installUnauthorizedHandler();
window.print = () => { PRINTED += 1; };

/* ---------- DOM 助手 ---------- */

const page = () => document.getElementById('app');
const panels = () => [...page().querySelectorAll('.panel')];
const panelByTitle = (title) => panels().find((p) => p.querySelector('.panel-title')?.textContent.trim() === title);
const stages = () => [...page().querySelectorAll('.prep-stage')];
const stageTimes = () => stages().map((n) => n.querySelector('.prep-time').textContent.trim());
const editBlocks = (title) => [...panelByTitle(title).querySelectorAll('.prep-edit-block')];
const blockErrorIn = (block) => {
  const node = block?.querySelector('.field-error');
  return node && !node.hidden ? node.textContent.trim() : null;
};
const actionButtons = () => [...page().querySelectorAll('.page-head-actions button')].map((b) => b.textContent.trim());

function setInput(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
}
function setSelect(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('change', { bubbles: true }));
}

async function go(target) {
  router.navigate(String(target).replace(/^#/, ''));
  await settle();
  await settle();
  await settle();
}

function reset({ status = 'ongoing', generated = true, fail = null } = {}) {
  STATUS = status;
  PREP = generated ? prepFixture() : -1;
  PREP_FAIL = fail;
  LAST_PUT = null;
  PRINTED = 0;
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }
  session.setSide('hr');
  session.save('hr-token', {
    id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
  });

  reset({ generated: true });
  backend.setHandlers(defaultHandlers());
  await boot(document.getElementById('app'));
  await settle();

  /* ---------- 1. 尚未生成：给「生成」入口 ---------- */
  reset({ generated: false });
  await go('#/interviews/1/prep');
  check('未生成（GET 404）→ 显示「尚未生成」而不是报错',
    panelByTitle('尚未生成') !== null, panels().map((p) => p.textContent.slice(0, 12)).join(' | '));
  check('未生成 → 有「生成准备提纲」按钮', buttonIn(page(), '生成准备提纲') !== undefined);
  check('未生成 → 不出现「重新生成」「编辑」（同一个动作不摆两处）',
    buttonIn(page(), '重新生成') === undefined && buttonIn(page(), '编辑') === undefined,
    actionButtons().join(','));
  check('说明会读哪些输入（岗位 JD + 维度 + 本场题目）',
    page().textContent.includes('AI 会读岗位的 JD 与评估维度、本场已有的题目'), '');
  check('未关联简历时不提简历', !page().textContent.includes('候选人关联的简历'));

  /* ---------- 2. 生成 ---------- */
  backend.reset();
  buttonIn(page(), '生成准备提纲').click();
  await settle();
  await settle();
  await settle();
  const genCall = backend.find('POST', '/interviews/1/prep');
  check('点「生成准备提纲」→ POST /prep', Boolean(genCall));
  check('生成**不带请求体**（端点无参数）', genCall?.body === undefined, JSON.stringify(genCall?.body));
  check('生成后渲染出提纲', stages().length === 1, `实际 ${stages().length}`);
  check('生成后出现「重新生成 / 编辑 / 导出 PDF」',
    ['重新生成', '编辑', '导出 PDF'].every((t) => actionButtons().includes(t)), actionButtons().join(','));

  /* ---------- 3. 只读视图：字段名以后端 schema 为准 ---------- */
  reset({ generated: true });
  await go('#/interviews/1/prep');
  check('提纲按分钟刻度排：累计区间 0–5、5–30',
    stageTimes().join(' / ') === '0–5 分 / 5–30 分', stageTimes().join(' / '));
  check('面板注明总时长（5 + 25 = 30 分钟）',
    panelByTitle('面试提纲')?.querySelector('.panel-note')?.textContent === '共约 30 分钟',
    String(panelByTitle('面试提纲')?.querySelector('.panel-note')?.textContent));
  check('阶段名渲染正确', stages()[0].querySelector('.prep-phase')?.textContent === '开场与自我介绍');
  check('`notes` 渲染成文字（它是字符串，不是数组）',
    stages()[0].textContent.includes('说明流程与时长'), stages()[0].textContent);
  check('考察重点用的是 `point`（原型写的是 focus）',
    panelByTitle('考察重点')?.textContent.includes('分布式事务的取舍') ?? false,
    panelByTitle('考察重点')?.textContent?.slice(0, 60));
  check('考察重点带维度标签与理由',
    panelByTitle('考察重点')?.querySelector('.tag')?.textContent === '专业能力' &&
      (panelByTitle('考察重点')?.textContent.includes('简历中主导过跨库改造') ?? false));
  check('问题预案用的是 `follow_ups`（原型写的是 followups），渲染成列表',
    [...panelByTitle('问题预案').querySelectorAll('.prep-points li')].map((n) => n.textContent).join(' | ')
      === '为什么先看这个指标 | 有没有别的方案',
    [...panelByTitle('问题预案').querySelectorAll('.prep-points li')].map((n) => n.textContent).join(' | '));
  check('问题预案显示考察意图',
    panelByTitle('问题预案')?.textContent.includes('考察排查思路') ?? false);

  /* ---------- 4. 时间轴：编辑后累计区间跟着变 ---------- */
  reset({ generated: true });
  await go('#/interviews/1/prep');
  check('生成时间显示在页头', page().textContent.includes('生成于 2026-09-21 10:20'),
    page().querySelector('.page-head .meta')?.textContent ?? '');
  check('未编辑过 → 不提「最后编辑」', !page().textContent.includes('最后编辑'));
  check('正交说明：交代不影响面试进度',
    page().querySelector('.prep-note')?.textContent.includes('不影响面试本身的进度') ?? false,
    String(page().querySelector('.prep-note')?.textContent?.slice(0, 40)));
  check('正交说明：并交代面试当前状态',
    page().querySelector('.prep-note')?.textContent.includes('面试当前：进行中') ?? false,
    String(page().querySelector('.prep-note')?.textContent));

  /* ---------- 5. 编辑：提交体必须是 schema 的字段名 ---------- */
  buttonIn(page(), '编辑').click();
  await settle();
  check('点「编辑」→ 整页换成表单', panelByTitle('面试提纲')?.querySelector('.prep-edit-block') !== null);
  check('提纲有 2 个可编辑阶段', editBlocks('面试提纲').length === 2, `实际 ${editBlocks('面试提纲').length}`);
  check('考察重点预填了 `point` 的值',
    editBlocks('考察重点')[0].querySelector('textarea')?.value === '分布式事务的取舍',
    String(editBlocks('考察重点')[0].querySelector('textarea')?.value));
  check('问题预案预填了 `follow_ups`（按行拆分）',
    editBlocks('问题预案')[0].querySelectorAll('textarea')[1]?.value === '为什么先看这个指标\n有没有别的方案',
    JSON.stringify(editBlocks('问题预案')[0].querySelectorAll('textarea')[1]?.value));

  backend.reset();
  buttonIn(page(), '保存').click();
  await settle();
  await settle();
  await settle();

  const put = backend.find('PUT', '/interviews/1/prep');
  check('保存 → PUT /prep', Boolean(put), JSON.stringify(backend.calls.map((c) => `${c.method} ${c.path}`)));
  check('提交体：outline 带 **seq**（删除中间一条后重编，不留空洞）',
    JSON.stringify(put?.body?.outline?.map((s) => s.seq)) === '[1,2]',
    JSON.stringify(put?.body?.outline?.map((s) => s.seq)));
  check('提交体：outline 用 `duration_min`（不是 minutes）',
    put?.body?.outline?.[0]?.duration_min === 5 && !('minutes' in (put?.body?.outline?.[0] ?? {})),
    JSON.stringify(put?.body?.outline?.[0]));
  check('提交体：outline 的 `notes` 是**字符串**（不是 points 数组）',
    typeof put?.body?.outline?.[0]?.notes === 'string' && !('points' in (put?.body?.outline?.[0] ?? {})),
    JSON.stringify(put?.body?.outline?.[0]?.notes));
  check('提交体：focus_points 用 `point`（不是 focus）',
    put?.body?.focus_points?.[0]?.point === '分布式事务的取舍' && !('focus' in (put?.body?.focus_points?.[0] ?? {})),
    JSON.stringify(put?.body?.focus_points?.[0]));
  check('提交体：question_plan 用 `follow_ups` 数组（不是 followups 字符串）',
    JSON.stringify(put?.body?.question_plan?.[0]?.follow_ups) === '["为什么先看这个指标","有没有别的方案"]' &&
      !('followups' in (put?.body?.question_plan?.[0] ?? {})),
    JSON.stringify(put?.body?.question_plan?.[0]));
  check('保存成功 → 提示并回到只读态', toasts().some((t) => t.includes('准备提纲已保存')), toasts().join(' | '));
  check('保存后出现「最后编辑」（edited_at 已置位）',
    page().textContent.includes('最后编辑 2026-09-21 11:00'),
    page().querySelector('.page-head .meta')?.textContent ?? '');
  check('保存后 generated_at **不变**',
    page().textContent.includes('生成于 2026-09-21 10:20'),
    page().querySelector('.page-head .meta')?.textContent ?? '');

  /* ---------- 6. 编辑：本地校验拦住必然 400 的提交 ---------- */
  clearToasts();
  reset({ generated: true });
  await go('#/interviews/1/prep');
  buttonIn(page(), '编辑').click();
  await settle();

  const nameInput = () => editBlocks('面试提纲')[0].querySelector('.prep-edit-head .input');
  setInput(nameInput(), '   ');
  backend.reset();
  buttonIn(page(), '保存').click();
  await settle();
  check('阶段名为空 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  check('阶段名为空 → 报错落在**那一条**下面',
    blockErrorIn(editBlocks('面试提纲')[0]) === '阶段名称不能为空',
    String(blockErrorIn(editBlocks('面试提纲')[0])));
  check('阶段名为空 → 提示「有几处还没填完」',
    toasts().some((t) => t.includes('还没填完')), toasts().join(' | '));

  setInput(nameInput(), '开场');
  const minsInput = () => editBlocks('面试提纲')[0].querySelector('.prep-edit-head .mins');
  setInput(minsInput(), '0');
  backend.reset();
  buttonIn(page(), '保存').click();
  await settle();
  check('分钟数 0 → 不发请求（后端要求 ge=1）', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  check('分钟数 0 → 报错', blockErrorIn(editBlocks('面试提纲')[0]) === '分钟数至少为 1',
    String(blockErrorIn(editBlocks('面试提纲')[0])));

  setInput(minsInput(), '5');
  setInput(editBlocks('面试提纲')[1].querySelector('.prep-edit-head .input'), '技术深挖');
  setInput(editBlocks('考察重点')[0].querySelector('textarea'), '   ');
  backend.reset();
  buttonIn(page(), '保存').click();
  await settle();
  check('考察重点为空 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  check('考察重点为空 → 报错落在那一条',
    blockErrorIn(editBlocks('考察重点')[0]) === '「重点验证什么」不能为空',
    String(blockErrorIn(editBlocks('考察重点')[0])));

  /* ---------- 7. 增删条目 ---------- */
  clearToasts();
  reset({ generated: true });
  await go('#/interviews/1/prep');
  buttonIn(page(), '编辑').click();
  await settle();
  buttonIn(panelByTitle('面试提纲'), '添加阶段').click();
  await settle();
  check('点「添加阶段」→ 多一条', editBlocks('面试提纲').length === 3, `实际 ${editBlocks('面试提纲').length}`);
  check('新阶段预填了默认名与分钟数（不是空行，免得一保存就 400）',
    editBlocks('面试提纲')[2].querySelector('.prep-edit-head .input')?.value === '新阶段' &&
      editBlocks('面试提纲')[2].querySelector('.prep-edit-head .mins')?.value === '5');

  editBlocks('面试提纲')[0].querySelector('.dim-editor-remove').click();
  await settle();
  check('点「×」→ 少一条', editBlocks('面试提纲').length === 2, `实际 ${editBlocks('面试提纲').length}`);
  check('删掉后剩下的是原来第二条与新增的那条',
    editBlocks('面试提纲').map((b) => b.querySelector('.prep-edit-head .input').value).join(',') === '技术深挖,新阶段',
    editBlocks('面试提纲').map((b) => b.querySelector('.prep-edit-head .input').value).join(','));

  /* ---------- 8. 取消编辑不落库 ---------- */
  clearToasts();
  backend.reset();
  buttonIn(page(), '取消').click();
  await settle();
  await settle();
  check('点「取消」→ 不发 PUT', !backend.calls.some((c) => c.method === 'PUT'), JSON.stringify(backend.calls.map((c) => c.method)));
  check('点「取消」→ 回到只读态', stages().length === 2, `实际 ${stages().length}`);

  /* ---------- 9. 重新生成：二次确认 + 覆盖 ---------- */
  clearToasts();
  buttonIn(page(), '重新生成').click();
  await settle();
  check('点「重新生成」→ 先二次确认（会覆盖手工改过的内容）',
    openOverlay()?.textContent.includes('整体覆盖') ?? false, openOverlay()?.textContent?.slice(0, 60));
  check('确认文案说明无法撤销', openOverlay()?.textContent.includes('无法撤销') ?? false);
  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发 POST', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  buttonIn(page(), '重新生成').click();
  await settle();
  backend.reset();
  buttonIn(openOverlay(), '重新生成').click();
  await settle();
  await settle();
  await settle();
  check('确认后 → POST /prep 并重载', Boolean(backend.find('POST', '/interviews/1/prep')));
  check('重新生成后内容是新的那份（edited_at 回到 null，不再显示「最后编辑」）',
    page().textContent.includes('AI 生成的阶段') && !page().textContent.includes('最后编辑'),
    page().querySelector('.page-head .meta')?.textContent ?? '');

  /* ---------- 10. 生成失败：502 不动旧内容 ---------- */
  clearToasts();
  reset({ generated: true });
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/prep': () => ({
      status: 502, body: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试', detail: null },
    }),
  });
  await go('#/interviews/1/prep');
  buttonIn(page(), '重新生成').click();
  await settle();
  buttonIn(openOverlay(), '重新生成').click();
  await settle();
  await settle();
  check('AI 失败 → 502 文案原样展示', toasts().some((t) => t.includes('AI 服务调用失败')), toasts().join(' | '));
  check('AI 失败 → 页面上原来那份提纲**还在**（后端不动旧内容）',
    stages().length === 2 && page().textContent.includes('开场与自我介绍'),
    `${stages().length} 段`);
  check('AI 失败 → 按钮恢复可用', buttonIn(page(), '重新生成')?.disabled === false);

  /* ---------- 11. 冻结：已完成及之后不可生成 / 编辑 ---------- */
  clearToasts();
  reset({ status: 'completed', generated: true });
  backend.setHandlers(defaultHandlers());
  await go('#/interviews/1/prep');
  check('已完成 → 「重新生成」禁用', buttonIn(page(), '重新生成')?.disabled === true);
  check('已完成 → 「编辑」禁用', buttonIn(page(), '编辑')?.disabled === true);
  check('已完成 → 说明为什么（要改先回退）',
    buttonIn(page(), '编辑')?.title.includes('请先回退到进行中') ?? false,
    String(buttonIn(page(), '编辑')?.title));
  check('已完成 → 提示条改说「已定稿」',
    page().querySelector('.prep-note')?.textContent.includes('随之定稿') ?? false,
    String(page().querySelector('.prep-note')?.textContent?.slice(0, 40)));
  check('已完成 → 仍可导出 PDF（阅读不受冻结影响）',
    buttonIn(page(), '导出 PDF')?.disabled !== true);
  check('已完成 → 页头交代面试当前状态',
    page().querySelector('.prep-note')?.textContent.includes('面试当前：已完成') ?? false,
    String(page().querySelector('.prep-note')?.textContent));

  /* ---------- 12. 未生成且已冻结：不给生成入口 ---------- */
  reset({ status: 'completed', generated: false });
  await go('#/interviews/1/prep');
  check('已冻结且未生成 → 没有「生成准备提纲」按钮', buttonIn(page(), '生成准备提纲') === undefined);
  check('已冻结且未生成 → 说明原因', page().textContent.includes('请先回退到进行中'));

  /* ---------- 13. 读取失败（非 404）要说清，不假装没生成 ---------- */
  reset({ generated: false, fail: { status: 500, body: { code: 'INTERNAL_ERROR', message: '服务器内部错误', detail: null } } });
  await go('#/interviews/1/prep');
  check('GET 非 404 失败 → 展示后端 message，而不是「尚未生成」',
    page().textContent.includes('服务器内部错误'), page().textContent.slice(0, 90));
  check('读取失败时不给生成按钮（状态不明就别乱动）',
    buttonIn(page(), '生成准备提纲') === undefined);

  /* ---------- 14. 导出 PDF ---------- */
  reset({ generated: true });
  backend.setHandlers(defaultHandlers());
  await go('#/interviews/1/prep');
  const before = PRINTED;
  buttonIn(page(), '导出 PDF').click();
  await settle();
  check('导出 PDF → 调 window.print()（后端没有 prep 的导出接口）', PRINTED === before + 1, `${before} → ${PRINTED}`);
  check('标签页标题是打印文件名用的那个', document.title === '张三 · 面试准备', document.title);

  /* ---------- 15. 面试详情页有「面试准备」入口 ---------- */
  await go('#/interviews/1');
  check('详情页给出「面试准备」入口（与状态机正交，单独一颗）',
    buttonIn(page().querySelector('.page-head-actions'), '面试准备') !== undefined,
    actionButtons().join(','));
  await closeAnyModal();
});
