/**
 * 岗位模块 Mock 联调测试。
 *
 * 重点在「提交出去的东西对不对」：PUT 是全量替换而不是追加、模糊搜索走的是
 * 服务端的 `keyword` 参数、前端校验拦住的是必然会 400 的请求。
 * 这三件事在界面上都看不出来 —— 改错了页面照样能跑。
 *
 * 运行：npm run dev 后打开 /mock/positions-harness.html
 */

import * as positions from '../src/pages/positions.js';
import * as session from '../src/session.js';
import {
  buttonIn, clearToasts, closeAnyModal, createReport, fieldErrorOf,
  installFakeBackend, openOverlay, settle, toasts,
} from './harness.js';

const report = createReport('岗位模块 Mock 测试');
const { check } = report;

session.setSide('hr');
session.save('mock-token', {
  id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
});

/* ---------- 假后端 ---------- */

let POSITIONS = [];

const seed = () => [
  {
    id: 1, name: '后端工程师',
    jd: '负责后端服务的开发与维护，要求熟悉 Python 与数据库设计。',
    evaluation_dimensions: ['沟通能力', '专业能力', '逻辑思维'],
    created_by: 2, created_at: '2026-09-01T10:00:00',
  },
  {
    id: 2, name: '前端工程师',
    jd: '负责 Web 前端开发。',
    evaluation_dimensions: ['沟通能力', '专业能力'],
    created_by: 2, created_at: '2026-09-03T10:00:00',
  },
];

function defaultHandlers() {
  return {
    // 服务端模糊匹配：与 API 文档 §6.2 一致（前端不该自己过滤本地副本）
    'GET /positions': ({ query }) => {
      const params = new URLSearchParams(query);
      const keyword = params.get('keyword');
      return { status: 200, body: keyword ? POSITIONS.filter((p) => p.name.includes(keyword)) : POSITIONS };
    },
    'POST /positions': ({ body }) => {
      const created = { id: POSITIONS.length + 10, ...body, created_by: 2, created_at: '2026-09-18T10:00:00' };
      POSITIONS = [...POSITIONS, created];
      return { status: 201, body: created };
    },
    'PUT /positions/:id': ({ path, body }) => {
      const id = Number(path.split('/')[2]);
      const index = POSITIONS.findIndex((p) => p.id === id);
      if (index === -1) return { status: 404, body: { code: 'NOT_FOUND', message: '岗位不存在', detail: null } };
      // 后端是全量替换：evaluation_dimensions 整体覆盖，不是追加
      POSITIONS[index] = { ...POSITIONS[index], ...body };
      return { status: 200, body: POSITIONS[index] };
    },
    'DELETE /positions/:id': ({ path }) => {
      const id = Number(path.split('/')[2]);
      POSITIONS = POSITIONS.filter((p) => p.id !== id);
      return { status: 204 };
    },
  };
}

const backend = installFakeBackend(defaultHandlers());

/* ---------- DOM 助手 ---------- */

const container = document.getElementById('harness-root');
const listItems = () => [...container.querySelectorAll('.split-item')];
const itemNames = () => listItems().map((n) => n.querySelector('.split-item-name').textContent.trim());
const dossier = () => container.querySelector('.panel .dossier-title')?.textContent ?? null;
const dimInputs = () => [...(openOverlay()?.querySelectorAll('.dim-editor-row .input') ?? [])];
const dimError = () => {
  const node = openOverlay()?.querySelector('.dim-editor-row ~ .field-error')
    ?? [...(openOverlay()?.querySelectorAll('.field-error') ?? [])].at(-1);
  return node && !node.hidden ? node.textContent.trim() : null;
};
const searchBox = () => container.querySelector('.split-list-head .input');

/**
 * 往受控输入里填值。
 *
 * ⚠️ 必须**派发 input 事件**：维度编辑器（与多数表单控件一样）把自己的状态
 * 挂在 `onInput` 监听器上，直接赋 `.value` 只改画面、不改状态 ——
 * 断言会看到「界面上明明填了、提交出去的却是旧的」。
 */
function setInput(node, value) {
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
/** 输入并等过防抖窗口 */
async function search(text) {
  const box = searchBox();
  box.value = text;
  box.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(280);
  await settle();
}

async function openCreate(preset = {}) {
  buttonIn(container.querySelector('.main'), '创建岗位').click();
  await settle();
  const overlay = openOverlay();
  if (preset.name !== undefined) setInput(overlay.querySelector('#position-name'), preset.name);
  if (preset.jd !== undefined) setInput(overlay.querySelector('#position-jd'), preset.jd);
  if (preset.dims) {
    // 先把默认的两行清掉，再按预设逐个加回来。
    // 注意「加回来」不能省 —— 清空之后直接按下标填会拿到 undefined。
    for (const _ of dimInputs()) {
      buttonIn(overlay.querySelector('.dim-editor-row'), '×').click();
      await settle();
    }
    for (const [index, value] of preset.dims.entries()) {
      buttonIn(overlay, '添加维度').click();
      await settle();
      setInput(dimInputs()[index], value);
    }
  }
  return overlay;
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  const renderPage = async () => { await positions.render(container); await settle(); };

  /* ---------- 列表 + 案卷 ---------- */
  POSITIONS = seed();
  backend.setHandlers(defaultHandlers());
  backend.reset(defaultHandlers());
  await renderPage();

  check('左栏列出 2 个岗位', listItems().length === 2, `实际 ${listItems().length}`);
  check('默认选中第一个', listItems()[0].classList.contains('is-active'));
  check('右栏显示第一个岗位的名称', dossier() === '后端工程师', String(dossier()));
  check('右栏显示 JD 原文（含换行保留的 pre-wrap 块）',
    container.querySelector('.dossier-text')?.textContent.includes('熟悉 Python') ?? false);
  check('评估维度渲染成标签', [...container.querySelectorAll('.dossier-section .tag')].map((t) => t.textContent).join(',') ===
    '沟通能力,专业能力,逻辑思维',
    [...container.querySelectorAll('.dossier-section .tag')].map((t) => t.textContent).join(','));
  check('左栏每项显示维度数', listItems()[0].querySelector('.split-item-meta').textContent.trim() === '3 个评估维度',
    listItems()[0].querySelector('.split-item-meta').textContent.trim());

  /* ---------- 切换选中 ---------- */
  listItems()[1].click();
  await settle();
  check('点第二个 → 右栏换成它', dossier() === '前端工程师', String(dossier()));
  check('点第二个 → 高亮跟着走', listItems()[1].classList.contains('is-active') && !listItems()[0].classList.contains('is-active'));

  /* ---------- 模糊搜索走服务端 ---------- */
  backend.reset();
  await search('前端');
  const searchCall = backend.calls.find((c) => c.path === '/positions');
  check('搜索发出的是 GET /positions?keyword=前端', searchCall?.query === 'keyword=%E5%89%8D%E7%AB%AF', String(searchCall?.query));
  check('搜索结果只剩 1 个', listItems().length === 1, `实际 ${listItems().length}`);
  check('选中项被自动修正到结果里的第一个', dossier() === '前端工程师', String(dossier()));

  /* ---------- 搜到 0 条：搜索框必须还在 ---------- */
  backend.reset();
  await search('不存在的岗位');
  check('搜不到 → 左栏提示没有匹配', container.querySelector('.split-list-body')?.textContent.includes('没有匹配的岗位') ?? false,
    container.querySelector('.split-list-body')?.textContent?.slice(0, 40));
  check('搜不到 → 搜索框仍在（否则改不回原来的词）', searchBox() !== null);
  check('搜不到 → 右栏回到「请选择一个岗位」', dossier() === null && container.textContent.includes('请选择一个岗位'));

  /* ---------- 清空搜索词 → 不再带 keyword 参数 ---------- */
  backend.reset();
  await search('');
  check('清空搜索词 → 请求不带 keyword 参数', backend.calls.find((c) => c.path === '/positions')?.query === '',
    String(backend.calls.find((c) => c.path === '/positions')?.query));
  check('清空后恢复全量', listItems().length === 2, `实际 ${listItems().length}`);

  /* ---------- 创建：本地校验 ---------- */
  clearToasts();
  await openCreate({ name: '', jd: '随便写点', dims: ['沟通能力'] });
  backend.reset();
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('空岗位名 → 内联报错', fieldErrorOf('岗位名称') === '请填写岗位名称', String(fieldErrorOf('岗位名称')));
  check('空岗位名 → 不发请求', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  await closeAnyModal();

  await openCreate({ name: '测试岗', jd: '', dims: ['沟通能力'] });
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('空 JD → 内联报错', fieldErrorOf('岗位描述（JD）') === '请填写岗位描述', String(fieldErrorOf('岗位描述（JD）')));
  await closeAnyModal();

  await openCreate({ name: '测试岗', jd: '一段描述', dims: [] });
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('0 个维度 → 报错', dimError() === '至少需要 1 个评估维度', String(dimError()));
  await closeAnyModal();

  await openCreate({ name: '测试岗', jd: '一段描述', dims: ['沟通能力', '沟通能力'] });
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('维度重复 → 报错', dimError()?.includes('评估维度重复') ?? false, String(dimError()));
  await closeAnyModal();

  await openCreate({ name: '测试岗', jd: '一段描述', dims: [' Communication ', 'communication'] });
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('维度重复判定不区分大小写、忽略首尾空白', dimError()?.includes('评估维度重复') ?? false, String(dimError()));
  await closeAnyModal();

  await openCreate({ name: '测试岗', jd: '一段描述', dims: ['x'.repeat(51)] });
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  check('单个维度超 50 字 → 报错', dimError()?.includes('不能超过 50 个字符') ?? false, String(dimError()));
  await closeAnyModal();

  /* ---------- 创建：成功 ---------- */
  clearToasts();
  const beforeCount = POSITIONS.length;
  await openCreate({ name: '数据工程师', jd: '负责数据管道。', dims: ['沟通能力', '数据处理'] });
  backend.reset();
  buttonIn(openOverlay(), '创建岗位').click();
  await settle();
  await settle();

  const postCall = backend.find('POST', '/positions');
  check('创建成功 → POST /positions', Boolean(postCall));
  check('创建成功 → 维度已 strip（提交的是干净值）',
    JSON.stringify(postCall?.body?.evaluation_dimensions) === '["沟通能力","数据处理"]',
    JSON.stringify(postCall?.body?.evaluation_dimensions));
  check('创建成功 → 弹窗关闭', openOverlay() === null);
  check('创建成功 → 列表重新拉取', POSITIONS.length === beforeCount + 1 && listItems().length === beforeCount + 1,
    `${POSITIONS.length} / ${listItems().length}`);
  check('创建成功 → 提示「岗位已创建」', toasts().some((t) => t.includes('岗位已创建')), toasts().join(' | '));

  /* ---------- 编辑：全量替换而不是追加 ---------- */
  backend.reset(defaultHandlers());
  POSITIONS = seed();
  await renderPage();
  buttonIn(container.querySelector('.dossier-actions'), '编辑').click();
  await settle();
  check('编辑弹窗预填了原值', openOverlay().querySelector('#position-name').value === '后端工程师',
    openOverlay().querySelector('#position-name').value);
  check('编辑弹窗预填了 3 个维度', dimInputs().length === 3, `实际 ${dimInputs().length}`);

  setInput(dimInputs()[1], '改写后的维度');
  backend.reset();
  buttonIn(openOverlay(), '保存').click();
  await settle();
  await settle();

  const putCall = backend.find('PUT', '/positions/1');
  check('编辑发出的是 PUT /positions/1', Boolean(putCall), JSON.stringify(backend.calls.map((c) => c.path)));
  check('维度整体替换，不是追加',
    JSON.stringify(putCall?.body?.evaluation_dimensions) === '["沟通能力","改写后的维度","逻辑思维"]',
    JSON.stringify(putCall?.body?.evaluation_dimensions));

  /* ---------- 编辑：撞名 409 用后端文案 ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'PUT /positions/:id': () => ({ status: 409, body: { code: 'BUSINESS_ERROR', message: '该岗位名称已存在', detail: null } }),
  });
  buttonIn(container.querySelector('.dossier-actions'), '编辑').click();
  await settle();
  buttonIn(openOverlay(), '保存').click();
  await settle();
  await settle();
  check('409 撞名 → toast 用后端文案', toasts().includes('该岗位名称已存在'), toasts().join(' | '));
  check('409 撞名 → 弹窗保持打开（改个名字还能再提交）', openOverlay() !== null);
  await closeAnyModal();

  /* ---------- 删除：二次确认 + 409 保护 ---------- */
  backend.setHandlers(defaultHandlers());
  POSITIONS = seed();
  await renderPage();
  clearToasts();

  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  check('点「删除」→ 先二次确认', openOverlay() !== null);
  check('确认文案说明「被引用会拒绝」',
    openOverlay()?.textContent.includes('题目或面试') ?? false, openOverlay()?.textContent.slice(0, 60));

  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发 DELETE', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  check('取消 → 岗位还在', POSITIONS.length === 2);

  backend.setHandlers({
    ...defaultHandlers(),
    'DELETE /positions/:id': () => ({
      status: 409, body: { code: 'BUSINESS_ERROR', message: '该岗位已被题库或面试引用，无法删除', detail: null },
    }),
  });
  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  buttonIn(openOverlay(), '删除').click();
  await settle();
  await settle();
  check('被引用 → 409 文案原样展示',
    toasts().some((t) => t.includes('已被题库或面试引用')), toasts().join(' | '));
  check('删除失败 → 两条仍在', listItems().length === 2, `实际 ${listItems().length}`);

  /* ---------- 删除成功 ---------- */
  clearToasts();
  backend.setHandlers(defaultHandlers());
  buttonIn(container.querySelector('.dossier-actions'), '删除').click();
  await settle();
  buttonIn(openOverlay(), '删除').click();
  await settle();
  await settle();
  check('删除成功 → DELETE /positions/1', Boolean(backend.find('DELETE', '/positions/1')));
  check('删除成功 → 提示已删除', toasts().some((t) => t.includes('岗位已删除')), toasts().join(' | '));
  check('删除成功 → 列表重新拉取后少一条', POSITIONS.length === 1, String(POSITIONS.length));

  /* ---------- 一条都没有时的空态 ---------- */
  POSITIONS = [];
  await renderPage();
  check('没有任何岗位 → 空态而不是空列表', container.textContent.includes('还没有岗位'));
  check('空态里有「创建岗位」按钮', Boolean(buttonIn(container.querySelector('.empty'), '创建岗位')));
  check('空态下不显示搜索框', searchBox() === null);

  /* ---------- 加载失败 ---------- */
  backend.setHandlers({
    'GET /positions': () => ({ status: 403, body: { code: 'FORBIDDEN', message: '无权限访问该岗位', detail: null } }),
  });
  await renderPage();
  check('加载失败 → 错误空态', container.textContent.includes('岗位加载失败'), container.textContent.slice(0, 60));
  check('加载失败 → 展示后端 message', container.textContent.includes('无权限访问该岗位'));
});
