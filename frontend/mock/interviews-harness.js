/**
 * 面试模块 Mock 联调测试（列表 + 详情）。
 *
 * 这个测试台**启动真实路由**，所以「点一行 → 进详情页」是真的走了一遍
 * 路由守卫与页面切换，而不是分别渲染两个页面。
 *
 * 重点在那些界面上看不出来的约定：提交的 `interview_question_id` 是不是
 * 面试题 id（不是题目 id、也不是面试 id）、失焦保存会不会在没改时白发请求、
 * 状态机给哪几个按钮、未关联简历是 404 而不是 403。
 *
 * 运行：npm run dev 后打开 /mock/interviews-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import {
  buttonIn, clearToasts, closeAnyModal, createReport, installFakeBackend,
  openOverlay, settle, toasts,
} from './harness.js';

const report = createReport('面试模块 Mock 测试');
const { check } = report;

session.setSide('hr');
session.save('hr-token', {
  id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
});

/* ---------- 假后端 ---------- */

const POSITIONS = [
  { id: 1, name: '后端工程师', jd: '……', evaluation_dimensions: ['专业能力', '沟通能力'], created_by: 2, created_at: '2026-09-01T10:00:00' },
];

const LIST = [
  { id: 3, position_id: 1, position_name: '后端工程师', candidate_name: '王五', candidate_contact: null,
    status: 'evaluated', created_at: '2026-09-10T10:00:00', completed_at: '2026-09-10T11:00:00',
    question_count: 8, answered_count: 8 },
  { id: 2, position_id: 1, position_name: '后端工程师', candidate_name: '李四', candidate_contact: 'lisi@example.com',
    status: 'completed', created_at: '2026-09-09T10:00:00', completed_at: '2026-09-09T11:00:00',
    question_count: 8, answered_count: 5 },
  { id: 1, position_id: 1, position_name: '后端工程师', candidate_name: '张三', candidate_contact: '13800000000',
    status: 'ongoing', created_at: '2026-09-08T10:00:00', completed_at: null,
    question_count: 8, answered_count: 2 },
];

function questionsOf(count, status) {
  return Array.from({ length: count }, (_, i) => ({
    interview_question_id: 100 + i,
    seq: i + 1,
    content: `第 ${i + 1} 题的题干内容。`,
    dimension: i % 2 === 0 ? '专业能力' : '沟通能力',
    source: i === 2 ? 'resume_match' : 'bank',
    match_reason: i === 2 ? '候选人简历里提到主导过跨库改造' : null,
    answer: status === 'ongoing' ? (i < 2 ? `第 ${i + 1} 题的已有回答` : null) : `第 ${i + 1} 题的已有回答`,
    recorded_at: status === 'ongoing' ? (i < 2 ? '2026-09-08T10:30:00' : null) : '2026-09-09T11:00:00',
    answer_source: 'hr',
  }));
}

let DETAIL = {};
let INVITATIONS = [];
let RESUME = null;
let NEXT_ID = 900;
let CREATED = null;

function makeDetail(id) {
  const item = LIST.find((row) => row.id === id) ?? LIST[2];
  return {
    ...item,
    jd: '负责后端服务。',
    evaluation_dimensions: ['专业能力', '沟通能力'],
    resume_id: null,
    questions: questionsOf(item.question_count, item.status),
  };
}

function defaultHandlers() {
  return {
    'GET /auth/me': () => ({ status: 200, body: { id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00' } }),
    'GET /positions': () => ({ status: 200, body: POSITIONS }),
    'GET /interviews': () => ({ status: 200, body: LIST }),
    'GET /interviews/:id': ({ path }) => {
      const id = Number(path.split('/')[2]);
      const detail = DETAIL[id];
      if (!detail) return { status: 404, body: { code: 'NOT_FOUND', message: '面试不存在', detail: null } };
      return { status: 200, body: detail };
    },
    'POST /interviews': ({ body }) => {
      const created = makeDetail(1);
      created.id = (NEXT_ID += 1);
      created.candidate_name = body.candidate_name;
      created.candidate_contact = body.candidate_contact;
      created.status = 'ongoing';
      created.question_count = 8;
      created.answered_count = 0;
      created.questions = questionsOf(8, 'ongoing');
      CREATED = created;
      DETAIL[created.id] = created;
      return { status: 201, body: created };
    },
    'POST /interviews/:id/answers': ({ path, body }) => {
      const id = Number(path.split('/')[2]);
      const question = DETAIL[id].questions.find((q) => q.interview_question_id === body.interview_question_id);
      if (!question) return { status: 404, body: { code: 'NOT_FOUND', message: '题目不属于该面试', detail: null } };
      question.answer = body.content;
      question.recorded_at = '2026-09-21T10:00:00';
      question.answer_source = 'hr';
      return { status: 200, body: question };
    },
    'POST /interviews/:id/complete': ({ path }) => {
      const id = Number(path.split('/')[2]);
      if (DETAIL[id].status !== 'ongoing') {
        return { status: 409, body: { code: 'BUSINESS_ERROR', message: '不允许从「已完成」迁移到「已完成」', detail: { from: 'completed', to: 'completed' } } };
      }
      DETAIL[id].status = 'completed';
      DETAIL[id].completed_at = '2026-09-21T10:05:00';
      return { status: 200, body: DETAIL[id] };
    },
    'POST /interviews/:id/rollback': ({ path }) => {
      const id = Number(path.split('/')[2]);
      DETAIL[id].status = 'ongoing';
      DETAIL[id].completed_at = null;
      return { status: 200, body: DETAIL[id] };
    },
    'GET /interviews/:id/resume': () => (RESUME
      ? { status: 200, body: RESUME }
      : { status: 404, body: { code: 'NOT_FOUND', message: '该面试尚未关联简历', detail: null } }),
    'GET /interviews/:id/invitations': () => ({ status: 200, body: INVITATIONS }),
    'POST /interviews/:id/invitations': ({ path }) => {
      const id = Number(path.split('/')[2]);
      const invitation = {
        id: (NEXT_ID += 1), interview_id: id, code: 'hT9rQ2xLm4ZbN1vCk8sPwA',
        status: 'pending', expires_at: '2026-09-28T10:00:00', accepted_at: null,
        candidate_username: null, created_at: '2026-09-21T10:00:00',
      };
      INVITATIONS = [invitation, ...INVITATIONS];
      return { status: 201, body: invitation };
    },
    'DELETE /interviews/:id/invitations/:invitationId': ({ path }) => {
      const invitationId = Number(path.split('/')[4]);
      const found = INVITATIONS.find((i) => i.id === invitationId);
      if (!found) return { status: 404, body: { code: 'NOT_FOUND', message: '邀请不存在', detail: null } };
      found.status = 'revoked';
      return { status: 200, body: found };
    },
    'POST /interviews/:id/questions/match': () => ({ status: 200, body: { added_count: 0, added: [], total_questions: 8 } }),
  };
}

const backend = installFakeBackend(defaultHandlers());
installUnauthorizedHandler();

/* ---------- DOM 助手 ---------- */

const page = () => document.getElementById('app');
const hash = () => location.hash;
const rows = () => [...page().querySelectorAll('.main tbody tr')];
const navItems = () => [...page().querySelectorAll('.qnav-item')];
const editorSeq = () => page().querySelector('.editor-seq')?.textContent;
const answerBox = () => page().querySelector('#answer-input');

function setInput(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
}

async function go(target) {
  router.navigate(String(target).replace(/^#/, ''));
  await settle();
  await settle();
  await settle();
}

/** 让失焦保存真的发生（原生 blur 不会在程序化改值后自动触发）。 */
async function blurAnswer() {
  answerBox().dispatchEvent(new Event('blur'));
  await settle();
  await settle();
}

function resetWorld() {
  DETAIL = { 1: makeDetail(1), 2: makeDetail(2), 3: makeDetail(3) };
  INVITATIONS = [];
  RESUME = null;
  CREATED = null;
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

  resetWorld();
  backend.setHandlers(defaultHandlers());
  await boot(document.getElementById('app'));
  await settle();
  await settle();
  await settle();

  /* ---------- 1. 起手即落在面试列表 ---------- */
  check('登录后默认落在 #/interviews', hash() === '#/interviews', hash());
  check('导航当前项是「面试」', page().querySelector('.nav-item.is-active')?.textContent.trim() === '面试',
    page().querySelector('.nav-item.is-active')?.textContent?.trim());

  /* ---------- 2. 列表渲染 ---------- */
  check('列表渲染 3 行', rows().length === 3, `实际 ${rows().length}`);
  check('保持接口返回顺序（新的在前，接口已按 id 降序）',
    rows().map((tr) => tr.querySelector('strong').textContent.trim()).join(',') === '王五,李四,张三',
    rows().map((tr) => tr.querySelector('strong').textContent.trim()).join(','));

  const statusOf = (tr) => tr.querySelector('.tag')?.textContent.trim();
  check('状态标签逐个翻译对（evaluated / completed / ongoing）',
    rows().map(statusOf).join(',') === '已评估,已完成,进行中', rows().map(statusOf).join(','));
  check('答题进度按「已答 / 总数」显示',
    rows()[1].querySelector('.progress-value')?.textContent === '5 / 8',
    String(rows()[1].querySelector('.progress-value')?.textContent));
  check('进度条宽度与进度一致',
    rows()[1].querySelector('.progress-fill')?.style.width === '63%',
    String(rows()[1].querySelector('.progress-fill')?.style.width));
  check('没有联系方式的行不渲染副信息', rows()[0].querySelector('.meta') === null ||
    rows()[0].querySelectorAll('td')[0].querySelectorAll('.meta').length === 0);
  check('有联系方式的行渲染副信息',
    rows()[1].querySelectorAll('td')[0].textContent.includes('lisi@example.com'),
    rows()[1].querySelectorAll('td')[0].textContent);
  check('创建时间按 YYYY-MM-DD HH:mm 渲染',
    rows()[2].querySelectorAll('td')[4].textContent.trim() === '2026-09-08 10:00',
    rows()[2].querySelectorAll('td')[4].textContent.trim());

  check('进行中的行主操作是「记录回答」',
    buttonIn(rows()[2], '记录回答') !== undefined, [...rows()[2].querySelectorAll('button')].map((b) => b.textContent).join(','));
  check('已评估的行主操作是「查看」', buttonIn(rows()[0], '查看') !== undefined);

  /* ---------- 3. 点一行 → 真的进详情页 ---------- */
  buttonIn(rows()[2], '记录回答').click();
  await settle();
  await settle();
  await settle();
  check('点行内主操作 → 跳到 #/interviews/1', hash() === '#/interviews/1', hash());
  check('详情页渲染出来了', page().querySelector('.editor') !== null);

  /* ---------- 4. 详情：状态轨 ---------- */
  check('状态轨当前段是「进行中」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '进行中',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));
  check('状态轨只呈现 4 段（draft 是瞬态，不对外可见）',
    page().querySelectorAll('.rail-step').length === 4, String(page().querySelectorAll('.rail-step').length));
  check('进行中：状态轨后面没有已完成段',
    page().querySelectorAll('.rail-step')[1].className.includes('is-done') === false);

  /* ---------- 5. 详情：题目导航 ---------- */
  check('导航列出 8 道题', navItems().length === 8, `实际 ${navItems().length}`);
  check('导航计数显示「2 / 8」',
    page().querySelector('.qnav-count')?.textContent === '2 / 8', String(page().querySelector('.qnav-count')?.textContent));
  check('已答的题标「已答」，未答的标「待答」',
    navItems().map((n) => n.querySelector('.qnav-mark').textContent).join('') === '已答已答待答待答待答待答待答待答',
    navItems().map((n) => n.querySelector('.qnav-mark').textContent).join(''));
  check('打开时定位到第一道**未答**的题（第 3 题）', editorSeq() === '3', String(editorSeq()));
  check('当前题在导航里高亮', navItems()[2].classList.contains('is-current'));

  /* ---------- 6. 详情：编辑区 ---------- */
  check('编辑区显示题干', page().querySelector('.editor-question')?.textContent.startsWith('第 3 题'),
    String(page().querySelector('.editor-question')?.textContent));
  check('编辑区显示维度标签', page().querySelector('.editor-dim, .editor-head .tag') !== null);
  check('未答的题输入框为空', answerBox().value === '', answerBox().value);
  check('进行中：输入框可编辑', answerBox().readOnly === false);
  check('输入框 maxlength 与后端 10000 对齐', answerBox().getAttribute('maxlength') === '10000',
    String(answerBox().getAttribute('maxlength')));
  check('未答的题显示「未修改」', page().querySelector('.save-state')?.textContent === '未修改',
    String(page().querySelector('.save-state')?.textContent));
  check('进行中给「标记完成」', buttonIn(page().querySelector('.page-head-actions'), '标记完成') !== undefined,
    [...page().querySelectorAll('.page-head-actions button')].map((b) => b.textContent).join(','));

  /* ---------- 7. 换题：导航点选 ---------- */
  navItems()[0].click();
  await settle();
  check('点导航第 1 项 → 编辑区跟着换', editorSeq() === '1', String(editorSeq()));
  check('已有回答的题会预填内容', answerBox().value === '第 1 题的已有回答', answerBox().value);
  check('已有回答的题显示最后录入时间',
    page().querySelector('.editor-answer-head .hint')?.textContent.includes('2026-09-08 10:30') ?? false,
    String(page().querySelector('.editor-answer-head .hint')?.textContent));
  check('第 1 题在导航里高亮', navItems()[0].classList.contains('is-current'));

  /* ---------- 8. 上一题 / 下一题 ---------- */
  check('第 1 题的「上一题」禁用', buttonIn(page().querySelector('.editor-pager'), '上一题').disabled);
  buttonIn(page().querySelector('.editor-pager'), '下一题').click();
  await settle();
  check('点「下一题」→ 序号前进', editorSeq() === '2', String(editorSeq()));

  /* ---------- 9. 保存：只在真的改了才发请求 ---------- */
  // 换到一道**未答**的题（第 3 题）—— 已答的题上测不出「标记从待答变已答」
  buttonIn(page().querySelector('.editor-pager'), '下一题').click();
  await settle();
  check('再点「下一题」→ 到第 3 题（未答）', editorSeq() === '3', String(editorSeq()));

  backend.reset();
  await blurAnswer();
  check('失焦但没改动 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  setInput(answerBox(), '改过的回答内容');
  backend.reset();
  await blurAnswer();
  const saveCall = backend.find('POST', '/interviews/1/answers');
  check('改动后失焦 → POST answers', Boolean(saveCall));
  check('提交的是 interview_question_id（不是题目 id、也不是面试 id）',
    saveCall?.body?.interview_question_id === 102, JSON.stringify(saveCall?.body));
  check('提交的 content 是输入框里的内容',
    saveCall?.body?.content === '改过的回答内容', JSON.stringify(saveCall?.body?.content));
  check('保存成功 → 状态变「已保存」', page().querySelector('.save-state')?.textContent === '已保存',
    String(page().querySelector('.save-state')?.textContent));
  check('保存后该题在导航里由「待答」变「已答」（已答数 2 → 3）',
    navItems().filter((n) => n.classList.contains('is-answered')).length === 3 &&
      navItems()[2].querySelector('.qnav-mark').textContent === '已答',
    `${navItems().filter((n) => n.classList.contains('is-answered')).length} / ${navItems()[2].querySelector('.qnav-mark').textContent}`);

  /* ---------- 10. 保存失败：就地标红，不清空输入 ---------- */
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/answers': () => ({
      status: 409, body: { code: 'BUSINESS_ERROR', message: '当前状态下不可修改回答，请先回退到进行中', detail: null },
    }),
  });
  clearToasts();
  setInput(answerBox(), '又改了一次');
  await blurAnswer();
  check('保存失败 → 状态标成「保存失败」', page().querySelector('.save-state')?.textContent === '保存失败',
    String(page().querySelector('.save-state')?.textContent));
  check('保存失败 → 提示后端文案',
    toasts().some((t) => t.includes('请先回退到进行中')), toasts().join(' | '));
  check('保存失败 → 输入框里的内容**没有**被清掉', answerBox().value === '又改了一次', answerBox().value);

  /* ---------- 11. 简历面板：未关联是 404，不是错误 ---------- */
  backend.setHandlers(defaultHandlers());
  const resumePanel = () => [...page().querySelectorAll('.panel')].find((p) => p.textContent.includes('候选人简历'));
  check('未关联简历 → 标题旁标注「尚未关联」',
    resumePanel()?.querySelector('.panel-note')?.textContent === '尚未关联',
    String(resumePanel()?.querySelector('.panel-note')?.textContent));
  check('未关联简历 → 说明是「候选人尚未提交」，而不是报错',
    resumePanel()?.querySelector('.prose')?.textContent.includes('尚未提交简历') ?? false,
    String(resumePanel()?.querySelector('.prose')?.textContent));
  check('未关联简历 → 按简历补题禁用',
    buttonIn(resumePanel(), '按简历补题').disabled === true);
  check('并说明禁用原因', buttonIn(resumePanel(), '按简历补题').title === '该面试尚未关联简历',
    buttonIn(resumePanel(), '按简历补题').title);

  /* ---------- 12. 简历面板：已关联 ---------- */
  RESUME = {
    resume_id: 4, title: '张三-后端开发', content: '（简历全文）\n第二行',
    candidate_name: '张三', candidate_contact: 'zhangsan@example.com', updated_at: '2026-09-20T09:40:00',
  };
  // 详情里的 resume_id 与简历端点必须**同时**成立 —— 补题按钮看的是前者
  DETAIL[1].resume_id = 4;
  await go('#/interviews/1');
  check('已关联 → 显示简历标题', resumePanel()?.textContent.includes('张三-后端开发') ?? false);
  check('已关联 → 正文按 pre-wrap 保留换行', page().querySelector('.resume-body')?.textContent.includes('\n'));
  check('已关联 → 显示最后更新时间（HR 据此判断是不是最新的）',
    resumePanel()?.textContent.includes('最后更新 2026-09-20 09:40') ?? false,
    resumePanel()?.textContent?.slice(0, 120));
  check('已关联 → 补题按钮可用', buttonIn(resumePanel(), '按简历补题').disabled === false);

  /* ---------- 13. 补题：0 条是正常结果 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/questions/match': () => ({ status: 200, body: { added_count: 0, added: [], total_questions: 8 } }),
  });
  buttonIn(resumePanel(), '按简历补题').click();
  await settle();
  await settle();
  await settle();
  check('补题 0 条 → info 提示「未匹配到新的题目」（200，不是错误）',
    toasts().some((t) => t.includes('未匹配到新的题目')), toasts().join(' | '));

  /* ---------- 14. 补题：有新增时报本场总数 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/questions/match': () => ({
      status: 200,
      body: { added_count: 2, added: [], total_questions: 10 },
    }),
  });
  buttonIn(resumePanel(), '按简历补题').click();
  await settle();
  await settle();
  await settle();
  check('补题有新增 → 同时报增量与本场总数（只报增量会让人以为在重复加）',
    toasts().some((t) => t.includes('本次新增 2 题') && t.includes('本场共 10 题')), toasts().join(' | '));

  /* ---------- 15. 补题失败：502 用后端文案，按钮恢复可用 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/questions/match': () => ({
      status: 502, body: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试', detail: null },
    }),
  });
  buttonIn(resumePanel(), '按简历补题').click();
  await settle();
  await settle();
  await settle();
  check('补题失败 → 502 文案原样展示', toasts().some((t) => t.includes('AI 服务调用失败')), toasts().join(' | '));
  check('补题失败 → 按钮恢复可用（可以重试）',
    buttonIn(resumePanel(), '按简历补题').disabled === false);

  /* ---------- 16. 邀请面板：空态 ---------- */
  backend.setHandlers(defaultHandlers());
  await go('#/interviews/1');
  const invitePanel = () => [...page().querySelectorAll('.panel')].find((p) => p.textContent.includes('作答邀请'));
  check('没有邀请码 → 引导去生成，而不是空白面板',
    invitePanel()?.querySelector('.prose')?.textContent.includes('还没有邀请码') ?? false,
    String(invitePanel()?.querySelector('.prose')?.textContent));

  /* ---------- 17. 生成邀请码 ---------- */
  clearToasts();
  backend.reset();
  buttonIn(invitePanel(), '生成邀请码').click();
  await settle();
  await settle();
  await settle();
  check('生成邀请码 → POST invitations', Boolean(backend.find('POST', '/interviews/1/invitations')));
  check('生成后提示「复制后发给候选人」',
    toasts().some((t) => t.includes('邀请码已生成')), toasts().join(' | '));
  check('列表里出现这张码，状态为「待接受」',
    invitePanel()?.querySelector('.code')?.textContent === 'hT9rQ2xLm4ZbN1vCk8sPwA' &&
      invitePanel()?.querySelector('.tag')?.textContent === '待接受',
    `${invitePanel()?.querySelector('.code')?.textContent} / ${invitePanel()?.querySelector('.tag')?.textContent}`);
  check('待接受的码给「复制」', buttonIn(invitePanel(), '复制') !== undefined);
  check('邀请码用等宽字体（l/1、O/0 要能逐字核对）',
    invitePanel()?.querySelector('.code') !== null);

  /* ---------- 18. 撤销邀请：二次确认 ---------- */
  clearToasts();
  buttonIn(invitePanel(), '撤销').click();
  await settle();
  check('点「撤销」→ 先二次确认', openOverlay() !== null);
  check('确认文案说明「立即失效」',
    openOverlay()?.textContent.includes('立即失效') ?? false, openOverlay()?.textContent?.slice(0, 60));
  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发 DELETE', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  buttonIn(invitePanel(), '撤销').click();
  await settle();
  backend.reset();
  buttonIn(openOverlay(), '撤销').click();
  await settle();
  await settle();
  await settle();
  check('确认 → DELETE invitations/{id}', Boolean(backend.find('DELETE', '/interviews/1/invitations/901')),
    backend.calls.map((c) => `${c.method} ${c.path}`).join(' '));
  check('撤销后状态变「已撤销」', invitePanel()?.querySelector('.tag')?.textContent === '已撤销',
    String(invitePanel()?.querySelector('.tag')?.textContent));
  check('已撤销的码不再给「复制」', buttonIn(invitePanel(), '复制') === undefined);
  check('已撤销的码也不再给「撤销」', buttonIn(invitePanel(), '撤销') === undefined);

  /* ---------- 19. 状态机：标记完成 ---------- */
  resetWorld();
  backend.setHandlers(defaultHandlers());
  await go('#/interviews/1');
  clearToasts();
  buttonIn(page().querySelector('.page-head-actions'), '标记完成').click();
  await settle();
  await settle();
  await settle();
  check('标记完成 → POST complete', Boolean(backend.find('POST', '/interviews/1/complete')));
  check('完成后状态轨走到「已完成」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '已完成',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));
  check('完成后输入框变只读（回答锁定）', answerBox().readOnly === true);
  check('完成后不再给「标记完成」', buttonIn(page().querySelector('.page-head-actions'), '标记完成') === undefined);
  check('完成后给「回退到进行中」',
    buttonIn(page().querySelector('.page-head-actions'), '回退到进行中') !== undefined,
    [...page().querySelectorAll('.page-head-actions button')].map((b) => b.textContent).join(','));
  check('只读态说明「需先回退才能修改」',
    page().querySelector('.editor-actions .hint')?.textContent.includes('需先回退') ?? false,
    String(page().querySelector('.editor-actions .hint')?.textContent));
  check('只读态不给「保存回答」', buttonIn(page().querySelector('.editor-actions'), '保存回答') === undefined);

  /* ---------- 20. 状态机：回退清空 completed_at ---------- */
  clearToasts();
  buttonIn(page().querySelector('.page-head-actions'), '回退到进行中').click();
  await settle();
  await settle();
  await settle();
  check('回退 → POST rollback', Boolean(backend.find('POST', '/interviews/1/rollback')));
  check('回退后状态回到「进行中」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '进行中',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));
  check('回退后「完成于」不再显示（completed_at 被清空）',
    !(page().querySelector('.page-head .meta')?.textContent.includes('完成于') ?? false),
    String(page().querySelector('.page-head .meta')?.textContent));
  check('回退后输入框恢复可编辑', answerBox().readOnly === false);

  /* ---------- 21. 状态机：非法迁移用后端文案 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews/:id/complete': () => ({
      status: 409,
      body: { code: 'BUSINESS_ERROR', message: '不允许从「已完成」迁移到「已完成」', detail: { from: 'completed', to: 'completed' } },
    }),
  });
  buttonIn(page().querySelector('.page-head-actions'), '标记完成').click();
  await settle();
  await settle();
  check('状态机拒绝 → 原样展示后端文案',
    toasts().some((t) => t.includes('不允许从「已完成」迁移到「已完成」')), toasts().join(' | '));

  /* ---------- 22. 状态机：evaluating 不给回退 ---------- */
  resetWorld();
  DETAIL[1].status = 'evaluating';
  backend.setHandlers(defaultHandlers());
  await go('#/interviews/1');
  check('evaluating：不给「回退到进行中」（后端也不允许）',
    buttonIn(page().querySelector('.page-head-actions'), '回退到进行中') === undefined,
    [...page().querySelectorAll('.page-head-actions button')].map((b) => b.textContent).join(','));
  check('evaluating：提示语说明「评估结束后才能回退」',
    page().querySelector('.editor-actions .hint')?.textContent.includes('评估进行中') ?? false,
    String(page().querySelector('.editor-actions .hint')?.textContent));

  /* ---------- 23. 返回列表 ---------- */
  buttonIn(page().querySelector('.page-head-actions'), '返回列表').click();
  await settle();
  await settle();
  await settle();
  check('点「返回列表」→ 回到 #/interviews', hash() === '#/interviews', hash());
  check('列表重新渲染', rows().length === 3, `实际 ${rows().length}`);

  /* ---------- 24. 创建面试 ---------- */
  resetWorld();
  backend.setHandlers(defaultHandlers());
  await go('#/interviews');
  clearToasts();
  buttonIn(page().querySelector('.main'), '创建面试').click();
  await settle();
  check('点「创建面试」→ 弹窗；提示会说清会出几道题',
    openOverlay()?.querySelector('.note-box')?.textContent.includes('共 8 道') ?? false,
    String(openOverlay()?.querySelector('.note-box')?.textContent));

  backend.reset();
  buttonIn(openOverlay(), '创建并出题').click();
  await settle();
  check('不填姓名 → 内联报错', (openOverlay()?.textContent.includes('请填写候选人姓名') ?? false));
  check('不填姓名 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  openOverlay().querySelector('#new-interview-name').value = '赵六';
  backend.reset();
  buttonIn(openOverlay(), '创建并出题').click();
  await settle();
  await settle();
  await settle();
  const createCall = backend.find('POST', '/interviews');
  check('创建 → POST /interviews', Boolean(createCall));
  check('提交体：position_id 是数字、联系方式留空传 null（不是空串）',
    createCall?.body?.position_id === 1 && createCall?.body?.candidate_contact === null,
    JSON.stringify(createCall?.body));
  check('创建后提示已生成的题数', toasts().some((t) => t.includes('已生成 8 道题')), toasts().join(' | '));
  check('创建成功 → 直接进这场面试', hash() === `#/interviews/${CREATED.id}`, hash());

  /* ---------- 25. 创建失败：502 保留弹窗可重试 ---------- */
  await go('#/interviews');
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /interviews': () => ({
      status: 502, body: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试', detail: null },
    }),
  });
  buttonIn(page().querySelector('.main'), '创建面试').click();
  await settle();
  openOverlay().querySelector('#new-interview-name').value = '孙七';
  buttonIn(openOverlay(), '创建并出题').click();
  await settle();
  await settle();
  check('出题失败 → 502 文案原样展示', toasts().some((t) => t.includes('AI 服务调用失败')), toasts().join(' | '));
  check('出题失败 → 弹窗保持打开（后端已回滚，可以直接重试）', openOverlay() !== null);
  check('出题失败 → 按钮文字恢复', buttonIn(openOverlay(), '创建并出题') !== undefined,
    [...openOverlay().querySelectorAll('button')].map((b) => b.textContent).join(','));
  await closeAnyModal();

  /* ---------- 26. 没有岗位时不能建面试 ---------- */
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /positions': () => ({ status: 200, body: [] }),
  });
  buttonIn(page().querySelector('.main'), '创建面试').click();
  await settle();
  check('没有岗位 → 「创建并出题」禁用',
    buttonIn(openOverlay(), '创建并出题').disabled === true);
  check('没有岗位 → 指明先去岗位页创建',
    openOverlay().textContent.includes('先到「岗位」页创建一个') ?? false,
    openOverlay().textContent.slice(0, 120));
  await closeAnyModal();
});
