/**
 * 题库模块 Mock 联调测试。
 *
 * 重点在「提交出去的东西对不对」和「筛选真的发对参数了吗」：
 * 简答题必须传 `options: []`、参考答案留空要传 null、`source` 不由客户端决定、
 * 维度必须跟着岗位走、六个筛选参数名一字不差。这些在界面上都看不出来。
 *
 * 运行：npm run dev 后打开 /mock/questions-harness.html
 */

import * as questions from '../src/pages/questions.js';
import * as session from '../src/session.js';
import {
  buttonIn, clearToasts, closeAnyModal, createReport, fieldErrorOf,
  installFakeBackend, openOverlay, settle, toasts,
} from './harness.js';

const report = createReport('题库模块 Mock 测试');
const { check } = report;

session.setSide('hr');
session.save('mock-token', {
  id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
});

/* ---------- 假后端 ---------- */

const POSITIONS = [
  { id: 1, name: '后端工程师', jd: '……', evaluation_dimensions: ['专业能力', '沟通能力'], created_by: 2, created_at: '2026-09-01T10:00:00' },
  { id: 2, name: '产品经理', jd: '……', evaluation_dimensions: ['沟通能力'], created_by: 2, created_at: '2026-09-03T10:00:00' },
];

const seed = () => [
  {
    id: 1, position_id: 1, category: '线上排查', dimension: '专业能力',
    content: '线上接口的 P99 延迟从 80ms 突然涨到 900ms，你会先做哪一步？',
    difficulty: 'hard', question_type: 'single_choice',
    options: ['先看监控面板，定位耗时集中在哪个环节', '立刻重启服务恢复可用性', '先回滚最近一次上线', '先扩大实例数量扛住流量'],
    reference_answer: '先看监控面板，定位耗时集中在哪个环节',
    explanation: '排查要先定位再动手。',
    tags: ['性能', '排查'], source: 'bank', created_by: 2, created_at: '2026-09-02T10:00:00',
  },
  {
    id: 2, position_id: 1, category: '基础', dimension: '沟通能力',
    content: '说一下你是怎么理解数据库事务隔离级别的。',
    difficulty: 'medium', question_type: 'short_answer',
    options: [], reference_answer: null, explanation: null,
    tags: [], source: 'ai', created_by: 2, created_at: '2026-09-03T10:00:00',
  },
  {
    id: 3, position_id: 2, category: '需求', dimension: '沟通能力',
    content: '研发说这个需求做不了，你会怎么推进？',
    difficulty: 'easy', question_type: 'short_answer',
    options: [], reference_answer: '先问清楚是哪一部分做不了。', explanation: null,
    tags: ['协作'], source: 'resume_match', created_by: 2, created_at: '2026-09-04T10:00:00',
  },
];

let QUESTIONS = [];
let nextId = 100;

function defaultHandlers() {
  return {
    'GET /positions': () => ({ status: 200, body: POSITIONS }),
    // 按 API 文档 §7.2：这些都是**精确/SQL LIKE** 过滤，AND 关系，无 difficulty 参数
    'GET /questions': ({ query }) => {
      const params = new URLSearchParams(query);
      let rows = QUESTIONS;
      const eq = (key, field) => {
        const value = params.get(key);
        if (value) rows = rows.filter((q) => String(q[field]) === value);
      };
      eq('position_id', 'position_id');
      eq('category', 'category');
      eq('dimension', 'dimension');
      eq('source', 'source');
      eq('question_type', 'question_type');
      const keyword = params.get('keyword');
      if (keyword) rows = rows.filter((q) => q.content.includes(keyword));
      return { status: 200, body: rows };
    },
    'POST /questions': ({ body }) => {
      const created = { id: (nextId += 1), ...body, source: 'bank', created_by: 2, created_at: '2026-09-18T10:00:00' };
      QUESTIONS = [...QUESTIONS, created];
      return { status: 201, body: created };
    },
    'PUT /questions/:id': ({ path, body }) => {
      const id = Number(path.split('/')[2]);
      const index = QUESTIONS.findIndex((q) => q.id === id);
      if (index === -1) return { status: 404, body: { code: 'NOT_FOUND', message: '题目不存在', detail: null } };
      QUESTIONS[index] = { ...QUESTIONS[index], ...body };
      return { status: 200, body: QUESTIONS[index] };
    },
    'DELETE /questions/:id': ({ path }) => {
      const id = Number(path.split('/')[2]);
      QUESTIONS = QUESTIONS.filter((q) => q.id !== id);
      return { status: 204 };
    },
    'POST /questions/:id/reference-answer': ({ path }) => {
      const id = Number(path.split('/')[2]);
      const index = QUESTIONS.findIndex((q) => q.id === id);
      if (index === -1) return { status: 404, body: { code: 'NOT_FOUND', message: '题目不存在', detail: null } };
      const target = QUESTIONS[index];
      const reference = target.question_type === 'single_choice' ? target.options[1] : 'AI 写的参考答案。';
      QUESTIONS[index] = { ...target, reference_answer: reference, explanation: 'AI 写的解析。' };
      return { status: 200, body: QUESTIONS[index] };
    },
  };
}

const backend = installFakeBackend(defaultHandlers());

/* ---------- DOM 助手 ---------- */

const container = document.getElementById('harness-root');
const listItems = () => [...container.querySelectorAll('.split-item')];
const dossierTitle = () => container.querySelector('.dossier-question')?.textContent ?? null;
const dossierSections = () =>
  [...container.querySelectorAll('.dossier-section')].map((s) => s.querySelector('.dossier-label').textContent.trim());
const sectionNode = (label) =>
  [...container.querySelectorAll('.dossier-section')].find((s) => s.querySelector('.dossier-label').textContent.trim() === label);
const countText = () => container.querySelector('.filterbar-count')?.textContent;
const filterSelect = (ariaLabel) => container.querySelector(`.filterbar select[aria-label="${ariaLabel}"]`);
const filterInput = () => container.querySelector('.filterbar input');

/** 填受控输入 —— 必须派发 input 事件，否则页面里的状态不会更新。 */
function setInput(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
}
function setSelect(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('change', { bubbles: true }));
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function openCreate() {
  buttonIn(container.querySelector('.main'), '创建题目').click();
  await settle();
  return openOverlay();
}

function modalInput(selector) { return openOverlay().querySelector(selector); }

/** 从弹窗里读某个字段下方的报错。 */
const modalFieldError = (label) => fieldErrorOf(label);

/** 把题型切到单选。 */
async function chooseType(label) {
  buttonIn(openOverlay(), label).click();
  await settle();
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  const renderPage = async () => { await questions.render(container); await settle(); await settle(); };

  /* ---------- 列表 + 案卷（含三种来源标签） ---------- */
  QUESTIONS = seed();
  backend.setHandlers(defaultHandlers());
  backend.reset(defaultHandlers());
  await renderPage();

  check('左栏列出 3 道题', listItems().length === 3, `实际 ${listItems().length}`);
  check('默认选中第一道', listItems()[0].classList.contains('is-active'));
  check('计数显示「3 道题」', countText() === '3 道题', String(countText()));
  check('左栏每项显示题型与难度标签',
    [...listItems()[0].querySelectorAll('.tag')].map((t) => t.textContent).join(',') === '单选题,难',
    [...listItems()[0].querySelectorAll('.tag')].map((t) => t.textContent).join(','));
  check('左栏每项显示所属岗位名', listItems()[0].querySelector('.split-item-pos')?.textContent === '后端工程师',
    String(listItems()[0].querySelector('.split-item-pos')?.textContent));

  check('右栏显示题干', (dossierTitle() ?? '').startsWith('线上接口的 P99'), String(dossierTitle()));
  check('右栏分区含「选项 / 参考答案 / 解析 / 标签」',
    dossierSections().join(',') === '选项,参考答案,解析,标签', dossierSections().join(','));
  check('单选：选项按 A/B/C/D 编号列出',
    [...sectionNode('选项').querySelectorAll('.option-key')].map((n) => n.textContent).join('') === 'ABCD',
    [...sectionNode('选项').querySelectorAll('.option-key')].map((n) => n.textContent).join(''));
  check('单选：标出哪一项是参考答案，其余不标',
    sectionNode('选项').querySelectorAll('.option-item.is-correct').length === 1 &&
      sectionNode('选项').querySelector('.option-item.is-correct .option-flag')?.textContent === '参考答案',
    String(sectionNode('选项').querySelectorAll('.option-item.is-correct').length));

  // meta-row 里第一个 .tag 就是来源标签（其后依次是题型、维度、难度）。
  // 种子顺序：id1 = bank（默认已选中）、id2 = ai、id3 = resume_match。
  const sourceOf = () => container.querySelector('.dossier-head .tag');

  check('来源 bank → 显示「手工」', sourceOf()?.textContent === '手工', String(sourceOf()?.textContent));
  check('来源标签带说明性 title', sourceOf()?.title === '手工录入题库', String(sourceOf()?.title));

  listItems()[1].click();
  await settle();
  check('来源 ai → 显示「AI」', sourceOf()?.textContent === 'AI', String(sourceOf()?.textContent));
  check('ai 的提示文案是三分支里的那一条',
    sourceOf()?.title === '由 AI 生成并收录进题库', String(sourceOf()?.title));
  check('简答：不渲染选项分区', !dossierSections().includes('选项'), dossierSections().join(','));
  check('简答无参考答案 → 提示可用 AI 起草',
    sectionNode('参考答案')?.textContent.includes('AI 生成参考答案') ?? false,
    sectionNode('参考答案')?.textContent?.slice(0, 40));
  check('无标签的题不渲染「标签」分区', !dossierSections().includes('标签'), dossierSections().join(','));
  // 条件分区为假时传的是 null；用原生 append 会把它变成字面量文本 "null"。
  // 稀疏的题（无解析/无标签）最容易露出来，所以就在这里断言。
  const dossierText = container.querySelector('.dossier-question')?.closest('.panel')?.textContent ?? '';
  check('右栏不出现字面量 null', !dossierText.includes('null'), dossierText.slice(0, 80));

  listItems()[2].click();
  await settle();
  check('来源 resume_match → 显示「简历匹配」（不能把英文枚举值透出去）',
    sourceOf()?.textContent === '简历匹配', String(sourceOf()?.textContent));
  check('resume_match 的提示文案是三分支里的那一条',
    sourceOf()?.title === '按候选人简历从题库匹配而来', String(sourceOf()?.title));

  /* ---------- 分类下拉：首次加载后就必须有值 ---------- */
  const categoryValues = [...filterSelect('按分类筛选').options].map((o) => o.value);
  check('分类下拉带上了已加载题目的分类（不能只有「全部分类」）',
    categoryValues.join(',') === ',线上排查,基础,需求', categoryValues.join(','));

  const dimensionValues = [...filterSelect('按维度筛选').options].map((o) => o.value);
  check('维度下拉由岗位维度去重而来', dimensionValues.join(',') === ',专业能力,沟通能力', dimensionValues.join(','));

  /* ---------- 筛选：参数名与 AND 关系 ---------- */
  backend.reset();
  setSelect(filterSelect('按岗位筛选'), '1');
  await settle();
  const call1 = backend.calls.filter((c) => c.path === '/questions').at(-1);
  check('按岗位筛选 → 发出 position_id 参数', call1?.query === 'position_id=1', String(call1?.query));
  check('筛选后只剩该岗位的 2 道题', listItems().length === 2, `实际 ${listItems().length}`);

  backend.reset();
  setSelect(filterSelect('按题型筛选'), 'single_choice');
  await settle();
  const call2 = backend.calls.filter((c) => c.path === '/questions').at(-1);
  check('按题型筛选 → 与前一个条件是 AND（两个参数同时带上）',
    new URLSearchParams(call2?.query).get('position_id') === '1' &&
      new URLSearchParams(call2?.query).get('question_type') === 'single_choice',
    String(call2?.query));
  check('筛选后只剩 1 道题', listItems().length === 1, `实际 ${listItems().length}`);

  backend.reset();
  setSelect(filterSelect('按维度筛选'), '沟通能力');
  await settle();
  check('筛到 0 条 → 空态而不是空列表', container.textContent.includes('没有匹配的题目'),
    container.textContent.slice(container.textContent.indexOf('题库'), container.textContent.indexOf('题库') + 40));

  // 复位，再验关键词
  setSelect(filterSelect('按岗位筛选'), '');
  setSelect(filterSelect('按题型筛选'), '');
  setSelect(filterSelect('按维度筛选'), '');
  await settle();
  backend.reset();
  setInput(filterInput(), '事务');
  await settle();
  const call3 = backend.calls.filter((c) => c.path === '/questions').at(-1);
  check('搜索题干 → 发出 keyword 参数', call3?.query === 'keyword=%E4%BA%8B%E5%8A%A1', String(call3?.query));
  check('搜索后只剩 1 道题', listItems().length === 1, `实际 ${listItems().length}`);

  backend.reset();
  setInput(filterInput(), '');
  await settle();
  const call4 = backend.calls.filter((c) => c.path === '/questions').at(-1);
  check('清空搜索词 → 不带任何参数', call4?.query === '', String(call4?.query));
  check('恢复全量 3 道题', listItems().length === 3, `实际 ${listItems().length}`);

  /* ---------- 创建：题型切换改变表单结构 ---------- */
  let overlay = await openCreate();
  // 被隐藏的字段块**仍在 DOM 里**（只是带了 hidden），所以不能只查存在性
  const fieldVisible = (label) => [...overlay.querySelectorAll('.field')]
    .some((f) => !f.hidden && f.querySelector('.field-label')?.textContent.trim() === label);

  check('默认题型是简答（存量题没有选项，按简答理解才符合事实）',
    buttonIn(overlay.querySelector('.seg'), '简答题').classList.contains('is-on'));
  check('简答态：不显示「选项」字段', fieldVisible('选项') === false);
  check('简答态：显示简答的「参考答案」文本框', overlay.querySelector('#question-reference') !== null);
  check('未保存的题不能用 AI 生成（端点按题目 id 工作）',
    buttonIn(overlay, 'AI 生成参考答案').disabled === true);

  await chooseType('单选题');
  check('切到单选：出现「选项」字段', fieldVisible('选项') === true);
  check('切到单选：选项默认给两行空输入', overlay.querySelectorAll('.choice-row').length === 2,
    `实际 ${overlay.querySelectorAll('.choice-row').length}`);

  /* ---------- 创建：维度跟随岗位 ---------- */
  const dimSelect = () => modalInput('#question-dimension');
  check('维度下拉跟着岗位走（后端工程师 → 专业能力 / 沟通能力）',
    [...dimSelect().options].map((o) => o.value).join(',') === '专业能力,沟通能力',
    [...dimSelect().options].map((o) => o.value).join(','));
  setSelect(modalInput('#question-position'), '2');
  await settle();
  check('换岗位后维度下拉跟着换（产品经理只有一个维度）',
    [...dimSelect().options].map((o) => o.value).join(',') === '沟通能力',
    [...dimSelect().options].map((o) => o.value).join(','));
  setSelect(modalInput('#question-position'), '1');
  await settle();
  await closeAnyModal();

  /* ---------- 创建：本地校验 ---------- */
  clearToasts();
  overlay = await openCreate();
  await chooseType('单选题');
  backend.reset();
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('题干不足 5 字 → 内联报错', modalFieldError('题干') === '题干至少 5 个字', String(modalFieldError('题干')));
  check('题干不足 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  await closeAnyModal();

  overlay = await openCreate();
  await chooseType('单选题');
  setInput(modalInput('#question-content'), '这是一道足够长的题干内容。');
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('选项为空 → 报错落在「选项」下', modalFieldError('选项') === '选项不能为空', String(modalFieldError('选项')));
  await closeAnyModal();

  overlay = await openCreate();
  await chooseType('单选题');
  setInput(modalInput('#question-content'), '这是一道足够长的题干内容。');
  const choiceInputs = () => [...overlay.querySelectorAll('.choice-row .input')];
  setInput(choiceInputs()[0], '选项一');
  setInput(choiceInputs()[1], '选项一');
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('选项重复 → 报错', modalFieldError('选项') === '选项不能重复', String(modalFieldError('选项')));
  await closeAnyModal();

  overlay = await openCreate();
  await chooseType('单选题');
  setInput(modalInput('#question-content'), '这是一道足够长的题干内容。');
  setInput(choiceInputs()[0], '选项一');
  setInput(choiceInputs()[1], '选项二');
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('没选参考答案 → 报错', modalFieldError('选项') === '单选题必须提供参考答案', String(modalFieldError('选项')));
  await closeAnyModal();

  overlay = await openCreate();
  setInput(modalInput('#question-content'), '这是一道足够长的题干内容。');
  setInput(modalInput('#question-tags'), new Array(11).fill('x').join('、'));
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('标签超过 10 个 → 报错', (modalFieldError('标签') ?? '').includes('标签最多 10 个'), String(modalFieldError('标签')));
  await closeAnyModal();

  overlay = await openCreate();
  setInput(modalInput('#question-content'), '这是一道足够长的题干内容。');
  setInput(modalInput('#question-tags'), 'x'.repeat(21));
  buttonIn(overlay, '创建题目').click();
  await settle();
  check('单个标签超过 20 字 → 报错', (modalFieldError('标签') ?? '').includes('单个标签不能超过 20 个字符'),
    String(modalFieldError('标签')));
  await closeAnyModal();

  /* ---------- 创建：单选的提交体 ---------- */
  clearToasts();
  const before = QUESTIONS.length;
  overlay = await openCreate();
  await chooseType('单选题');
  setSelect(modalInput('#question-position'), '1');
  await settle();
  setSelect(modalInput('#question-dimension'), '沟通能力');
  setInput(modalInput('#question-content'), 'HTTP 状态码 401 表示什么？');
  setInput(choiceInputs()[0], '未认证');
  setInput(choiceInputs()[1], '未授权');
  setSelect(modalInput('#question-answer'), '0');
  setInput(modalInput('#question-tags'), '网络、基础、网络');
  setSelect(modalInput('#question-difficulty'), 'easy');
  backend.reset();
  buttonIn(overlay, '创建题目').click();
  await settle();
  await settle();

  const postCall = backend.find('POST', '/questions');
  check('创建成功 → POST /questions', Boolean(postCall));
  check('提交体：题干已 trim、题型为 single_choice',
    postCall?.body?.content === 'HTTP 状态码 401 表示什么？' && postCall?.body?.question_type === 'single_choice',
    JSON.stringify(postCall?.body?.question_type));
  check('提交体：选项是数组、参考答案是选中那一项的**文本**',
    JSON.stringify(postCall?.body?.options) === '["未认证","未授权"]' && postCall?.body?.reference_answer === '未认证',
    JSON.stringify([postCall?.body?.options, postCall?.body?.reference_answer]));
  check('提交体：难度与分类按所选提交', postCall?.body?.difficulty === 'easy' && postCall?.body?.category === '通用',
    `${postCall?.body?.difficulty} / ${postCall?.body?.category}`);
  check('提交体：标签按顿号拆开（重复交给后端去重）',
    JSON.stringify(postCall?.body?.tags) === '["网络","基础","网络"]', JSON.stringify(postCall?.body?.tags));
  check('提交体**不含 source**（该字段只由服务端写）', !('source' in (postCall?.body ?? {})),
    JSON.stringify(Object.keys(postCall?.body ?? {})));
  check('创建成功 → 弹窗关闭', openOverlay() === null);
  check('创建成功 → 列表重新拉取（多一道）',
    QUESTIONS.length === before + 1 && listItems().length === before + 1, `${QUESTIONS.length} / ${listItems().length}`);

  /* ---------- 创建：简答的提交体 ---------- */
  overlay = await openCreate();
  setSelect(modalInput('#question-position'), '1');
  await settle();
  setInput(modalInput('#question-content'), '描述一次你主导的技术改造。');
  backend.reset();
  buttonIn(overlay, '创建题目').click();
  await settle();
  await settle();
  const postShort = backend.find('POST', '/questions');
  check('简答：options 传空数组（不是省略）',
    JSON.stringify(postShort?.body?.options) === '[]', JSON.stringify(postShort?.body?.options));
  check('简答：参考答案留空传 null',
    postShort?.body?.reference_answer === null, JSON.stringify(postShort?.body?.reference_answer));
  check('简答：question_type 为 short_answer', postShort?.body?.question_type === 'short_answer');

  /* ---------- 编辑：预填 + PUT ---------- */
  clearToasts();
  QUESTIONS = seed();
  await renderPage();
  buttonIn(container.querySelector('.dossier-actions'), '编辑').click();
  await settle();
  check('编辑预填题干', modalInput('#question-content').value.startsWith('线上接口的 P99'));
  check('编辑预填岗位', modalInput('#question-position').value === '1');
  check('编辑预填维度', modalInput('#question-dimension').value === '专业能力');
  check('编辑预填选项（4 个）', openOverlay().querySelectorAll('.choice-row').length === 4,
    `实际 ${openOverlay().querySelectorAll('.choice-row').length}`);
  check('编辑时 AI 按钮可用（题已保存）', buttonIn(openOverlay(), 'AI 生成参考答案').disabled === false);

  setInput(modalInput('#question-content'), '改过的题干内容，长度足够。');
  backend.reset();
  buttonIn(openOverlay(), '保存').click();
  await settle();
  await settle();
  const putCall = backend.find('PUT', '/questions/1');
  check('编辑 → PUT /questions/1', Boolean(putCall));
  check('编辑提交的是全量字段（PUT 是全量替换）',
    ['position_id', 'dimension', 'content', 'difficulty', 'tags', 'question_type', 'options', 'reference_answer']
      .every((key) => key in (putCall?.body ?? {})),
    JSON.stringify(Object.keys(putCall?.body ?? {})));

  /* ---------- AI 生成参考答案：成功后写回表单 ---------- */
  clearToasts();
  QUESTIONS = seed();
  await renderPage();
  buttonIn(container.querySelector('.dossier-actions'), '编辑').click();
  await settle();
  backend.reset();
  buttonIn(openOverlay(), 'AI 生成参考答案').click();
  await settle();
  await settle();
  check('AI 生成 → POST 到 reference-answer 端点',
    Boolean(backend.find('POST', '/questions/1/reference-answer')),
    JSON.stringify(backend.calls.map((c) => c.path)));
  check('AI 生成 → 结果写回参考答案下拉（单选按下标选中）',
    modalInput('#question-answer').value === '1', modalInput('#question-answer').value);
  check('AI 生成 → 解析也一并写回', modalInput('#question-explanation').value === 'AI 写的解析。',
    modalInput('#question-explanation').value);
  check('AI 生成 → 提示「可继续修改」', toasts().some((t) => t.includes('已生成')), toasts().join(' | '));
  await closeAnyModal();

  /* ---------- AI 失败：502 不改动题目 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /questions/:id/reference-answer': () => ({
      status: 502, body: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试', detail: null },
    }),
  });
  await renderPage();
  const answerBefore = sectionNode('参考答案')?.textContent ?? '';
  buttonIn(container.querySelector('.dossier-actions'), 'AI 生成参考答案').click();
  await settle();
  // 这道题已有参考答案 → 先过一道二次确认
  buttonIn(openOverlay(), '重新生成').click();
  await settle();
  await settle();
  check('AI 失败 → 502 文案原样展示',
    toasts().some((t) => t.includes('AI 服务调用失败')), toasts().join(' | '));
  check('AI 失败 → 页面上的参考答案**没有被改动**',
    (sectionNode('参考答案')?.textContent ?? '') === answerBefore, String(sectionNode('参考答案')?.textContent));

  /* ---------- AI 越界（409）：不写库、只提示 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'POST /questions/:id/reference-answer': () => ({
      status: 409,
      body: { code: 'BUSINESS_ERROR', message: 'AI 生成的答案不在选项中，请手工确认', detail: null },
    }),
  });
  await renderPage();
  buttonIn(container.querySelector('.dossier-actions'), 'AI 生成参考答案').click();
  await settle();
  buttonIn(openOverlay(), '重新生成').click();
  await settle();
  await settle();
  check('单选 AI 越界 → 409 文案原样展示（宁可让 HR 手工填）',
    toasts().some((t) => t.includes('不在选项中')), toasts().join(' | '));

  /* ---------- 已有参考答案时先二次确认 ---------- */
  backend.setHandlers(defaultHandlers());
  QUESTIONS = seed();
  await renderPage();
  clearToasts();
  buttonIn(container.querySelector('.dossier-actions'), 'AI 生成参考答案').click();
  await settle();
  check('已有参考答案 → 先二次确认（生成会覆盖且不可撤销）',
    openOverlay()?.textContent.includes('覆盖') ?? false, openOverlay()?.textContent?.slice(0, 50));
  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发请求、参考答案不变', backend.calls.length === 0 &&
    sectionNode('参考答案')?.querySelector('.dossier-text')?.textContent.startsWith('先看监控面板'),
    String(backend.calls.length));

  buttonIn(container.querySelector('.dossier-actions'), 'AI 生成参考答案').click();
  await settle();
  backend.reset();
  buttonIn(openOverlay(), '重新生成').click();
  await settle();
  await settle();
  check('确认后 → 发出请求并刷新右栏',
    Boolean(backend.find('POST', '/questions/1/reference-answer')) &&
      sectionNode('参考答案')?.querySelector('.dossier-text')?.textContent === '立刻重启服务恢复可用性',
    String(sectionNode('参考答案')?.querySelector('.dossier-text')?.textContent));

  /* ---------- 删除 ---------- */
  clearToasts();
  QUESTIONS = seed();
  backend.setHandlers(defaultHandlers());
  await renderPage();
  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  check('点「删除」→ 先二次确认', openOverlay() !== null);
  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发 DELETE', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);

  backend.setHandlers({
    ...defaultHandlers(),
    'DELETE /questions/:id': () => ({
      status: 409, body: { code: 'BUSINESS_ERROR', message: '该题目已被面试引用，无法删除', detail: null },
    }),
  });
  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  buttonIn(openOverlay(), '删除').click();
  await settle();
  await settle();
  check('被面试引用 → 409 文案原样展示',
    toasts().some((t) => t.includes('已被面试引用')), toasts().join(' | '));
  check('删除失败 → 列表仍为 3 道', listItems().length === 3, `实际 ${listItems().length}`);

  clearToasts();
  backend.setHandlers(defaultHandlers());
  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  buttonIn(openOverlay(), '删除').click();
  await settle();
  await settle();
  check('删除成功 → DELETE /questions/1', Boolean(backend.find('DELETE', '/questions/1')));
  check('删除成功 → 列表少一道', QUESTIONS.length === 2 && listItems().length === 2,
    `${QUESTIONS.length} / ${listItems().length}`);

  /* ---------- 没有岗位时不能建题 ---------- */
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /positions': () => ({ status: 200, body: [] }),
  });
  QUESTIONS = [];
  await renderPage();
  const createButton = buttonIn(container.querySelector('.main'), '创建题目');
  check('一个岗位都没有 → 「创建题目」禁用', createButton.disabled === true);
  check('并说明原因（题目必须挂在岗位上）', createButton.title === '请先创建岗位', createButton.title);

  /* ---------- 加载失败 ---------- */
  backend.setHandlers({
    'GET /positions': () => ({ status: 403, body: { code: 'FORBIDDEN', message: '无权限访问该岗位', detail: null } }),
  });
  await renderPage();
  check('岗位加载失败 → 错误空态', container.textContent.includes('题库加载失败'),
    container.textContent.slice(container.textContent.indexOf('题库'), container.textContent.indexOf('题库') + 40));
  check('加载失败 → 展示后端 message', container.textContent.includes('无权限访问该岗位'));
});
