/**
 * 我的简历 Mock 联调测试 —— 简历增删改查 + 关联到面试 + 刷题按简历推荐与降级提示。
 *
 * 这是候选人端的最后一个模块，也是**契约最容易抄错**的一个（`PUT` 的「部分更新」
 * 语义、空串 vs `null`、`resume_id` 必填）。断言里的期望值全部从接口文档来
 * （§10.7 / §11.1–§11.5 / §12.3）。
 *
 * 三条最要紧的断言：
 *   1. **正文 textarea 没有 `maxlength`** —— 有它会静默截断粘贴，候选人以为整份
 *      简历存好了、尾部其实丢了。这是最糟的一类数据丢失：无提示、不可察觉。
 *   2. **可选字段清空后提交的是空串而不是 `null`** —— `PUT` 是部分更新，`null`
 *      表示「不改」，提交 `null` 会让「清空姓名」这个动作静默失效。
 *   3. **解除关联必须显式提交 `{"resume_id": null}`** —— 该字段必填，
 *      靠省略字段表达解除会被后端判成缺字段。
 *
 * 运行：npm run dev 后打开 /mock/resume-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import { buttonIn, clearToasts, createReport, installFakeBackend, openOverlay, settle, toasts } from './harness.js';

const report = createReport('我的简历 Mock 测试');
const { check } = report;

/* ==========================================================================
   固定数据
   ========================================================================== */

const CANDIDATE = { id: 7, username: 'li.yun', role: 'candidate', is_active: true, created_at: '2026-09-01T09:00:00' };

const RESUME_A = {
  id: 4, title: '李云-后端开发', content: '教育经历：某某大学\n工作经历：某某公司',
  candidate_name: '李云', candidate_contact: 'liyun@example.com',
  created_at: '2026-09-20T10:00:00', updated_at: '2026-09-21T09:40:00',
};
const RESUME_B = {
  id: 5, title: '李云-数据方向', content: '教育经历：某某大学\n项目经历：数据平台',
  candidate_name: '', candidate_contact: '',
  created_at: '2026-09-19T10:00:00', updated_at: '2026-09-19T11:00:00',
};
/** 第三份**没有被任何面试用到** —— 索引里要能看到「尚未用于面试」这一态。 */
const RESUME_C = {
  id: 6, title: '李云-运维方向', content: '教育经历：某某大学',
  candidate_name: '', candidate_contact: '',
  created_at: '2026-09-17T10:00:00', updated_at: '2026-09-17T10:00:00',
};

/** 三场面试：一场用着 A、一场用着 B、一场没有关联，另加一场已结束的。 */
const INTERVIEWS = [
  { id: 3, position_name: '后端工程师', status: 'ongoing', question_count: 8, answered_count: 2, submitted: false, resume_id: 4, created_at: '2026-09-21T10:00:00' },
  { id: 2, position_name: '前端工程师', status: 'ongoing', question_count: 5, answered_count: 0, submitted: false, resume_id: 5, created_at: '2026-09-18T10:00:00' },
  { id: 1, position_name: '数据工程师', status: 'ongoing', question_count: 6, answered_count: 0, submitted: false, resume_id: null, created_at: '2026-09-10T10:00:00' },
  { id: 9, position_name: '运维工程师', status: 'evaluated', question_count: 4, answered_count: 4, submitted: true, resume_id: null, created_at: '2026-09-05T10:00:00' },
];

const POSITIONS = [{ id: 1, name: '后端工程师', question_count: 12 }];

function sessionDetail(over = {}) {
  return {
    session: {
      id: 7, status: 'ongoing', position_id: 1,
      category: null, dimension: null, difficulty: null, question_type: null,
      total: 2, answered_count: 0, correct_count: 0,
      started_at: '2026-09-21T14:00:00', finished_at: null,
    },
    items: [{
      item_id: 61, seq: 1,
      question: { id: 12, position_id: 1, category: '基础', dimension: '专业能力', difficulty: 'easy',
        content: 'HTTP 状态码 401 表示什么？', question_type: 'single_choice',
        options: ['未认证', '未授权'], tags: [] },
      user_answer: null, is_correct: null, score: null, explanation: null, reference_answer: null,
    }],
    resume_id: null,
    resume_match_applied: false,
    ...over,
  };
}

/* ==========================================================================
   假后端
   ========================================================================== */

const flags = {
  resumes: [RESUME_A, RESUME_B, RESUME_C],
  interviews: INTERVIEWS,
  deleteRejected: false,
  detail: null,
};

function handlers() {
  return {
    'GET /auth/me': () => ({ status: 200, body: CANDIDATE }),

    'GET /candidate/resumes': () => ({ status: 200, body: flags.resumes }),
    'POST /candidate/resumes': ({ body }) => ({
      status: 201,
      body: { id: 6, ...body, created_at: '2026-09-22T09:00:00', updated_at: '2026-09-22T09:00:00' },
    }),
    'PUT /candidate/resumes/:id': ({ body, path }) => ({
      status: 200,
      body: { id: Number(path.split('/')[3]), ...body, created_at: '2026-09-20T10:00:00', updated_at: '2026-09-22T10:00:00' },
    }),
    'DELETE /candidate/resumes/:id': () => (flags.deleteRejected
      ? { status: 409, body: { code: 'BUSINESS_ERROR', message: '该简历已被面试或练习关联，无法删除', detail: null } }
      : { status: 204 }),

    'GET /candidate/interviews': () => ({ status: 200, body: flags.interviews }),
    'PUT /candidate/interviews/:id/resume': ({ body }) => ({
      status: 200,
      body: body.resume_id == null ? null : { resume_id: body.resume_id, title: 'x', content: 'y', candidate_name: null, candidate_contact: null, updated_at: '2026-09-22T10:00:00' },
    }),

    'GET /candidate/positions': () => ({ status: 200, body: POSITIONS }),
    'GET /practice/sessions': () => ({ status: 200, body: [] }),
    // 预览响应是 `{total, items}`（§13.27）：本页只借它派生岗位/分类/维度下拉，
    // 但形状必须与真实后端一致 —— 否则页面读 `items` 会拿到 undefined
    'GET /practice/questions': () => ({
      status: 200,
      body: { total: 1, items: [{ id: 12, category: '基础', dimension: '专业能力' }] },
    }),
    'POST /practice/sessions': () => ({ status: 201, body: sessionDetail() }),
    'GET /practice/sessions/:id': () => ({ status: 200, body: flags.detail ?? sessionDetail() }),
  };
}

const backend = installFakeBackend(handlers());
installUnauthorizedHandler();

/* ==========================================================================
   小工具
   ========================================================================== */

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

const lastCall = (method, path) => [...backend.calls].reverse().find((c) => c.method === method && c.path === path);
const called = (method, path) => backend.calls.some((c) => c.method === method && c.path === path);

function signInAsCandidate() {
  const previous = session.getSide();
  session.setSide('candidate');
  session.save('cand-token', CANDIDATE);
  session.setSide(previous);
}

/**
 * 在**弹窗里**查元素。
 *
 * ⚠️ 弹窗挂在 `document.body` 上，是 `#app` 的**兄弟**而不是子孙
 * （`modal.js` 的 `document.body.append(overlay)`），所以 `page().querySelector`
 * 查不到它 —— 用它会得到 null，断言「查到了元素」的那几条会莫名其妙地失败。
 */
const inModal = (selector) => openOverlay()?.querySelector(selector) ?? null;
const allInModal = (selector) => [...(openOverlay()?.querySelectorAll(selector) ?? [])];

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }

  await boot(document.getElementById('app'));
  await settle();
  await settle();
  await settle();

  signInAsCandidate();
  await go('#/candidate/resumes');

  /* ---------- 1. 导航与列表 ---------- */
  check('候选人导航里出现了「我的简历」', navTexts().includes('我的简历'), navTexts().join(','));
  check('「我的面试」仍排在导航第一位（默认落地页不变）', navTexts()[0] === '我的面试', navTexts().join(','));
  check('「我的简历」排在最后（它是备料，不是日常入口）',
    navTexts()[navTexts().length - 1] === '我的简历', navTexts().join(','));

  check('左索引列出三份简历', all('.split-item').length === 3, String(all('.split-item').length));
  check('索引项显示关联场次数（取自每场的 resume_id），没用到的写「尚未用于面试」',
    text().includes('用于 1 场面试') && text().includes('尚未用于面试'),
    all('.split-item-meta').map((n) => n.textContent).join(' || '));
  check('右栏默认选中第一份，显示标题与正文',
    page().querySelector('.dossier-title')?.textContent === '李云-后端开发'
      && text().includes('教育经历：某某大学'),
    page().querySelector('.dossier-title')?.textContent);
  check('右栏的「用于面试」列出用到它的那一场',
    page().querySelector('.used-row-name')?.textContent === '后端工程师',
    page().querySelector('.used-row')?.textContent);
  check('「用于面试」这一块带状态标签（能看出那场进行到哪了）',
    Boolean(page().querySelector('.used-row .tag')));

  /* ---------- 2. 新建弹窗：正文**不能**有 maxlength ---------- */
  buttonIn(page(), '新建简历').click();
  await settle();
  check('新建弹窗打开了', openOverlay() !== null);
  const content = inModal('#resume-content');
  check('正文是 textarea（弹窗在 body 上，要用 openOverlay 查）', Boolean(content));
  // 这一条是本模块最要紧的断言
  check('**正文 textarea 没有 maxlength 属性**（有它会静默截断粘贴，尾部丢了都不知道）',
    !content.hasAttribute('maxlength'), content.getAttribute('maxlength'));
  check('标题与可选字段**有** maxlength（与后端长度约束一致，且它们不会造成数据丢失）',
    inModal('#resume-title')?.getAttribute('maxlength') === '100'
      && inModal('#resume-name')?.getAttribute('maxlength') === '100'
      && inModal('#resume-contact')?.getAttribute('maxlength') === '200',
    inModal('#resume-title')?.getAttribute('maxlength'));
  check('正文旁边有实时字数', inModal('.char-count')?.textContent === '0 / 20000',
    inModal('.char-count')?.textContent);

  /* ---------- 3. 粘贴超长正文：不截断、计数变红、保存禁用 ---------- */
  const tooLong = 'a'.repeat(25000);
  content.value = tooLong;
  content.dispatchEvent(new Event('input'));
  await settle();
  check('超长后**内容仍是 25000 字**（没有被浏览器截断）',
    content.value.length === 25000, String(content.value.length));
  check('超长后计数变红并给出真实字数',
    inModal('.char-count.is-over')?.textContent === '25000 / 20000',
    inModal('.char-count')?.textContent);
  check('超长后「创建简历」被禁用（这一条是硬上限，点下去只会被后端拒）',
    buttonIn(openOverlay(), '创建简历')?.disabled === true);

  const exactly = 'a'.repeat(20000);
  content.value = exactly;
  content.dispatchEvent(new Event('input'));
  await settle();
  check('恰好 20000 字 → 计数不再标红、保存恢复可用',
    inModal('.char-count.is-over') === null
      && buttonIn(openOverlay(), '创建简历')?.disabled === false,
    inModal('.char-count')?.className);

  /* ---------- 4. 本地校验：空标题 / 空正文不发请求 ---------- */
  clearToasts();
  backend.reset();
  content.value = '';
  content.dispatchEvent(new Event('input'));
  buttonIn(openOverlay(), '创建简历').click();
  await settle();
  check('空标题 + 空正文 → 字段级报错，不发请求',
    !called('POST', '/candidate/resumes'), backend.calls.map((c) => c.path).join(','));

  /* ---------- 5. 可选字段清空 → 提交空串而不是 null ---------- */
  inModal('#resume-title').value = '新简历';
  content.value = '正文内容';
  content.dispatchEvent(new Event('input'));
  // 姓名与联系方式留空 —— 提交的必须是 `""`（`null` 表示「不改」，会让清空失效）
  backend.reset();
  buttonIn(openOverlay(), '创建简历').click();
  await settle();
  await settle();

  const created = lastCall('POST', '/candidate/resumes')?.body ?? {};
  check('新建提交的四个字段齐全', created.title === '新简历' && created.content === '正文内容',
    JSON.stringify(created));
  check('**可选字段留空时提交空串而不是 null**（null 在 PUT 语义里表示「不改」）',
    created.candidate_name === '' && created.candidate_contact === '',
    JSON.stringify(created));
  check('创建成功后关闭弹窗并提示', openOverlay() === null && toasts().includes('已创建'),
    toasts().join(' | '));

  /* ---------- 6. 编辑：改标题 + 清空姓名 ---------- */
  await go('#/candidate/resumes');
  buttonIn(page(), '编辑').click();
  await settle();
  check('编辑弹窗预填了当前值',
    inModal('#resume-title')?.value === '李云-后端开发'
      && inModal('#resume-content')?.value.includes('某某公司'),
    inModal('#resume-title')?.value);
  inModal('#resume-name').value = '';   // 清空姓名
  backend.reset();
  buttonIn(openOverlay(), '保存修改').click();
  await settle();
  await settle();
  check('编辑走 PUT', called('PUT', '/candidate/resumes/4'),
    backend.calls.map((c) => `${c.method} ${c.path}`).join(','));
  check('**清空姓名提交的是空串**，这样「清空」才真的生效',
    lastCall('PUT', '/candidate/resumes/4')?.body?.candidate_name === '',
    JSON.stringify(lastCall('PUT', '/candidate/resumes/4')?.body));

  /* ---------- 7. 删除：二次确认；被引用时原样展示 409 ---------- */
  await go('#/candidate/resumes');
  clearToasts();
  backend.reset();
  buttonIn(page(), '删除').click();
  await settle();
  check('删除先弹二次确认', openOverlay()?.textContent.includes('删除这份简历？'));
  buttonIn(openOverlay(), '取消').click();
  await settle();
  await settle();
  check('取消 → 不发删除请求', !called('DELETE', '/candidate/resumes/4'));

  flags.deleteRejected = true;
  clearToasts();
  backend.reset();
  buttonIn(page(), '删除').click();
  await settle();
  buttonIn(openOverlay(), '删除').click();
  await settle();
  await settle();
  check('被引用时删除 → 原样展示后端文案（前端不重编）',
    toasts().includes('该简历已被面试或练习关联，无法删除'), toasts().join(' | '));
  flags.deleteRejected = false;

  /* ---------- 8. 「用于面试」：回显当前关联 ---------- */
  await go('#/candidate/resumes');
  buttonIn(page(), '用于面试').click();
  await settle();
  const rows = allInModal('.pick-row');
  check('四场面试各一行', rows.length === 4, String(rows.length));
  check('当前用的就是这份的那一场 → 勾上并说明',
    rows[0].querySelector('.pick-row-note')?.textContent === '本场现在用的就是这份简历'
      && rows[0].querySelector('input').checked === true,
    rows[0].textContent);
  check('用着**别的**简历的那一场 → 不勾，并说明当前用的是哪一份',
    rows[1].querySelector('.pick-row-note')?.textContent === '本场现在用的是《李云-数据方向》'
      && rows[1].querySelector('input').checked === false,
    rows[1].textContent);
  check('没有关联的那一场 → 不勾并说明',
    rows[2].querySelector('.pick-row-note')?.textContent === '本场还没有关联简历');
  check('**已结束的那一场只读并说明原因**（后端同样会拒，前端禁用是为了不让人白点）',
    rows[3].querySelector('input').disabled === true
      && rows[3].querySelector('.pick-row-note')?.textContent === '本场面试已结束，关联已冻结',
    rows[3].textContent);

  /* ---------- 9. 勾选 / 取消 → 逐场 PUT，解除显式传 null ---------- */
  clearToasts();
  backend.reset();
  rows[2].querySelector('input').checked = true;                       // 第三场改用这份
  rows[2].querySelector('input').dispatchEvent(new Event('change'));
  rows[0].querySelector('input').checked = false;                      // 第一场解除
  rows[0].querySelector('input').dispatchEvent(new Event('change'));
  buttonIn(openOverlay(), '保存').click();
  await settle();
  await settle();

  check('勾上 = 本场改用这份 → PUT {resume_id: 4}',
    lastCall('PUT', '/candidate/interviews/1/resume')?.body?.resume_id === 4,
    JSON.stringify(lastCall('PUT', '/candidate/interviews/1/resume')?.body));
  check('**取消勾 = 解除 → 显式提交 {"resume_id": null}**（该字段必填，省略会被判成缺字段）',
    Object.prototype.hasOwnProperty.call(lastCall('PUT', '/candidate/interviews/3/resume')?.body ?? {}, 'resume_id')
      && lastCall('PUT', '/candidate/interviews/3/resume')?.body?.resume_id === null,
    JSON.stringify(lastCall('PUT', '/candidate/interviews/3/resume')?.body));
  check('保存后关窗、提示中性措辞（解除关联时「已关联简历」就成了错话）',
    openOverlay() === null && toasts().includes('已更新关联'), toasts().join(' | '));
  check('保存后重载页面（界面与事实一致）', hash() === '#/candidate/resumes');

  /* ---------- 10. 空态 ---------- */
  flags.resumes = [];
  await go('#/candidate/resumes');
  check('一份简历都没有 → 空态给「新建简历」并说清它能干什么',
    text().includes('还没有简历') && text().includes('招聘方才能按它补题'),
    text().slice(0, 80));
  check('空态里也有「新建简历」按钮', buttonIn(page(), '新建简历') !== undefined);
  flags.resumes = [RESUME_A, RESUME_B, RESUME_C];

  /* ---------- 11. 刷题页：按简历推荐的下拉 ---------- */
  await go('#/candidate/practice');
  const subBar = page().querySelector('.filterbar--sub');
  check('「取题方式」**另起一行**（它不是筛选条件，不缩小题目池）',
    Boolean(subBar) && subBar.querySelector('.filterbar-label')?.textContent === '取题方式',
    subBar?.textContent);
  const resumeSelect = subBar.querySelector('select');
  check('简历下拉的选项取自 /candidate/resumes',
    [...resumeSelect.options].map((o) => o.textContent.trim()).join(',')
      === '不使用简历,李云-后端开发,李云-数据方向,李云-运维方向',
    [...resumeSelect.options].map((o) => o.textContent.trim()).join(','));
  check('有简历时下拉可用', resumeSelect.disabled === false);

  backend.reset();
  buttonIn(page(), '开始练习').click();
  await settle();
  await settle();
  check('不选简历 → 请求体里**不含** resume_id（省略比传 null 干净）',
    !Object.prototype.hasOwnProperty.call(lastCall('POST', '/practice/sessions')?.body ?? {}, 'resume_id'),
    JSON.stringify(lastCall('POST', '/practice/sessions')?.body));

  await go('#/candidate/practice');
  page().querySelector('.filterbar--sub select').value = '5';
  backend.reset();
  buttonIn(page(), '开始练习').click();
  await settle();
  await settle();
  check('选了简历 → 请求体带上 resume_id',
    lastCall('POST', '/practice/sessions')?.body?.resume_id === 5,
    JSON.stringify(lastCall('POST', '/practice/sessions')?.body));

  /* ---------- 12. 没有简历时：下拉只留「不使用」并禁用 + 指路 ---------- */
  flags.resumes = [];
  await go('#/candidate/practice');
  const emptySelect = page().querySelector('.filterbar--sub select');
  check('没有简历 → 下拉**禁用**且只有「不使用」一项',
    emptySelect.disabled === true && emptySelect.options.length === 1,
    `${emptySelect.disabled} / ${emptySelect.options.length}`);
  check('没有简历 → 旁边直接把「去哪录」指出来', buttonIn(page(), '去录入') !== undefined);
  buttonIn(page(), '去录入').click();
  await settle();
  await settle();
  check('点「去录入」→ 到我的简历页', hash() === '#/candidate/resumes', hash());
  flags.resumes = [RESUME_A, RESUME_B, RESUME_C];

  /* ---------- 13. 降级提示：关联了简历却没按它推荐 ---------- */
  // 三个分支必须分清：没关联（不提示）/ 降级了（提示）/ 生效了（不提示）
  flags.detail = sessionDetail({ resume_id: 5, resume_match_applied: false });
  backend.reset();
  await go('#/candidate/practice/7');
  check('关联了简历但没按它推荐 → 显示**信息条**（不是报错样式）',
    text().includes('按简历推荐这次没有生效，已按筛选条件取题。'),
    page().querySelector('.note-box')?.textContent);
  check('信息条用的是 note-box 而不是错误色（练习本身是可用的，说成坏了会误导）',
    Boolean(page().querySelector('.note-box')) && !has('.note-box.is-error'));

  flags.detail = sessionDetail({ resume_id: 5, resume_match_applied: true });
  await go('#/candidate/practice/7');
  check('**推荐真的生效了 → 不显示任何提示**', !has('.note-box'),
    page().querySelector('.note-box')?.textContent);

  flags.detail = sessionDetail({ resume_id: null, resume_match_applied: false });
  await go('#/candidate/practice/7');
  check('**压根没关联简历 → 也不提示**（那是正常选择，不是降级）', !has('.note-box'),
    page().querySelector('.note-box')?.textContent);
  flags.detail = null;

  /* ---------- 14. 收尾 ---------- */
  check('没有残留的弹窗', openOverlay() === null);
});
