/**
 * pages/interviews.js —— 面试列表
 *
 * 全站唯一用表格的页面：这里要横向扫很多行、比较状态与进度，表格是对的形状；
 * 岗位与题库是「读一份东西」，所以用案卷。
 *
 * 每行的主操作按状态命名（记录回答 / 去评估 / 查看报告），而不是一律叫「查看」——
 * HR 扫这张表时问的是「这场该我做什么」，按钮直接回答它。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { openModal } from '../components/modal.js';
import { contextTitle, createShell, emptyState, formatDateTime, loadingBlock, statusTag } from '../components/shell.js';
import { navigate } from '../router.js';

/**
 * 主操作的文案按状态分叉，但**目的地暂时都指向详情页**：
 * `/interviews/:id/evaluation` 属于评估模块，尚未落地。
 * 评估页搬进来时把 completed / evaluating / evaluated 三项改指过去即可。
 * （路由表里没有的路由不放在按钮上 —— 点了会「什么都没发生」。）
 */
const NEXT_ACTION = {
  draft:      { label: '查看',     path: (id) => `/interviews/${id}` },
  ongoing:    { label: '记录回答', path: (id) => `/interviews/${id}` },
  completed:  { label: '查看',     path: (id) => `/interviews/${id}` },
  evaluating: { label: '查看',     path: (id) => `/interviews/${id}` },
  evaluated:  { label: '查看',     path: (id) => `/interviews/${id}` },
};

function progressCell(interview) {
  const total = interview.question_count || 0;
  const done = interview.answered_count || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  return el('div', { class: 'progress' },
    el('div', { class: 'progress-track' },
      el('div', { class: 'progress-fill', style: `width:${percent}%` })),
    el('span', { class: 'progress-value', text: `${done} / ${total}` }),
  );
}

function buildRow(interview) {
  const next = NEXT_ACTION[interview.status] ?? NEXT_ACTION.draft;

  return el(
    'tr',
    {},
    el(
      'td',
      {},
      el('strong', { text: interview.candidate_name }),
      // 列表接口不下发 resume_id（API 文档 §8.4），所以联系方式是这里唯一的副信息
      interview.candidate_contact ? el('div', { class: 'meta', text: interview.candidate_contact }) : null,
    ),
    el('td', { text: interview.position_name }),
    el('td', {}, statusTag(interview.status)),
    el('td', {}, progressCell(interview)),
    el('td', { class: 'meta', text: formatDateTime(interview.created_at) }),
    el('td', { class: 'cell-actions' },
      el('button', {
        class: 'btn btn--quiet btn--sm',
        text: next.label,
        onClick: () => navigate(next.path(interview.id)),
      })),
  );
}

/* ------------------------------ 创建弹窗 ------------------------------ */

async function openCreateModal(onCreated) {
  let positions = [];
  let loadFailed = false;
  try {
    positions = await api.get('/positions');
  } catch {
    loadFailed = true;
  }

  const positionSelect = el(
    'select',
    { class: 'select', id: 'new-interview-position' },
    positions.length
      ? positions.map((p) => el('option', { value: String(p.id), text: p.name }))
      : el('option', { value: '', text: '暂无岗位' }),
  );

  const nameInput = el('input', {
    class: 'input', id: 'new-interview-name', maxlength: '100', placeholder: '候选人的姓名',
  });
  const nameError = fieldError();

  const contactInput = el('input', {
    class: 'input', id: 'new-interview-contact', maxlength: '200', placeholder: '邮箱或手机号（可不填）',
  });
  const contactError = fieldError();

  const errors = fieldErrors({ candidate_name: nameError, candidate_contact: contactError });

  const submit = el('button', {
    class: 'btn btn--primary',
    text: '创建并出题',
    disabled: loadFailed || !positions.length,
  });

  const body = el(
    'div',
    {},
    loadFailed
      ? el('p', { class: 'field-error', text: '岗位列表加载失败，请关闭后重试。' })
      : null,
    !loadFailed && !positions.length
      ? el('p', { class: 'hint', text: '还没有岗位。先到「岗位」页创建一个，再回来建面试。' })
      : null,

    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-position', text: '岗位' }),
      positionSelect,
      el('p', { class: 'field-note', text: 'AI 会按这个岗位的 JD 和评估维度出题。' })),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-name', text: '候选人姓名' }),
      nameInput,
      nameError),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-contact', text: '联系方式' }),
      contactInput,
      contactError),
    el('p', { class: 'note-box' },
      '创建后会立刻出题：题库抽 5 道、AI 按 JD 补 3 道，共 8 道，通常需要几秒。'),
  );

  const handle = openModal({
    title: '创建面试',
    body,
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      submit,
    ],
  });

  submit.addEventListener('click', async () => {
    errors.clear();
    if (!nameInput.value.trim()) {
      errors.show('candidate_name', '请填写候选人姓名');
      nameInput.focus();
      return;
    }

    // 同步出题可能耗时数秒 —— 期间锁住整个弹窗，避免重复提交
    handle.setBusy(true);
    submit.textContent = '正在生成面试题…';

    try {
      const detail = await api.post('/interviews', {
        position_id: Number(positionSelect.value),
        candidate_name: nameInput.value.trim(),
        // 联系方式留空传 null（不是空串）：后端把 null 当作「没有」
        candidate_contact: contactInput.value.trim() || null,
      });
      handle.close();
      toast.success(`已生成 ${detail.question_count} 道题`);
      onCreated(detail);
    } catch (error) {
      // AI 出题失败时后端已整体回滚（无残留），可以安全重试 —— 弹窗保持打开
      handle.setBusy(false);
      submit.textContent = '创建并出题';
      // 400 落到字段；502（AI 出题失败）等仍用后端文案
      if (!errors.fromServer(error)) toast.error(error.message);
    }
  });
}

/* -------------------------------- 页面 -------------------------------- */

export async function render(container) {
  const { root, main } = createShell(contextTitle('面试'));
  mount(container, root);
  mount(main, loadingBlock('正在加载面试列表…'));

  let interviews;
  try {
    interviews = await api.get('/interviews');
  } catch (error) {
    // 列表拉不到时给一个「重新加载」的口子 —— 否则只能自己刷新整个页面
    mount(main, el('div', { class: 'panel' }, emptyState('面试列表加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }

  // 出题成功就进这场面试开始记录，而不是留在列表上
  const create = () => openCreateModal((detail) => navigate(`/interviews/${detail.id}`));

  mount(
    main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '面试' }),
        el('p', { class: 'page-lede' }, '一场面试从创建开始：AI 按岗位出题，你逐题记录，完成后一键评估。'),
      ),
      el('div', { class: 'page-head-actions' },
        el('button', { class: 'btn btn--primary', text: '创建面试', onClick: create })),
    ),

    el('div', { class: 'panel' },
      interviews.length
        ? el('table', { class: 'table' },
            el('thead', {},
              el('tr', {},
                el('th', { text: '候选人' }),
                el('th', { text: '岗位' }),
                el('th', { text: '状态' }),
                el('th', { text: '答题进度' }),
                el('th', { text: '创建时间' }),
                el('th', {}),
              )),
            el('tbody', {}, interviews.map(buildRow)),
          )
        : emptyState('还没有面试', '创建一场面试，AI 会按岗位和评估维度出题。',
            el('button', { class: 'btn btn--primary', text: '创建面试', onClick: create })),
    ),
  );
}
