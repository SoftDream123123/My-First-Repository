/**
 * 面试列表（module-07 §5.2）。
 *
 * 默认落地页。创建面试是**同步出题**（PRD §5.3 ①），可能耗时数秒，
 * 因此加载态与失败重试是这个页面最需要处理好的两件事。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';
import {
  createShell,
  contextTitle,
  emptyState,
  formatDateTime,
  loadingBlock,
  navigate,
  statusTag,
} from '../components/shell.js';

function buildRow(interview) {
  const actions = [
    el('button', {
      class: 'btn btn--quiet btn--sm',
      text: '查看',
      onClick: () => navigate(`/interviews/${interview.id}`),
    }),
  ];

  if (interview.status === 'evaluated') {
    actions.push(
      el('button', {
        class: 'btn btn--quiet btn--sm',
        text: '查看报告',
        onClick: () => navigate(`/interviews/${interview.id}/evaluation`),
      }),
    );
  }

  return el(
    'tr',
    {},
    el('td', {}, el('strong', { text: interview.candidate_name })),
    el('td', { text: interview.position_name }),
    el('td', {}, statusTag(interview.status)),
    el(
      'td',
      { class: 'score--cell' },
      `${interview.answered_count} / ${interview.question_count}`,
    ),
    el('td', { class: 'meta', text: formatDateTime(interview.created_at) }),
    el('td', { class: 'cell-actions' }, actions),
  );
}

function buildTable(interviews) {
  return el(
    'table',
    { class: 'table' },
    el(
      'thead',
      {},
      el(
        'tr',
        {},
        el('th', { text: '候选人' }),
        el('th', { text: '岗位' }),
        el('th', { text: '状态' }),
        el('th', { text: '已回答' }),
        el('th', { text: '创建时间' }),
        el('th', {}),
      ),
    ),
    el('tbody', {}, interviews.map(buildRow)),
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
      ? positions.map((p) => el('option', { value: p.id, text: p.name }))
      : el('option', { value: '', text: '暂无岗位' }),
  );

  const nameInput = el('input', {
    class: 'input',
    id: 'new-interview-name',
    placeholder: '候选人的姓名',
  });

  const contactInput = el('input', {
    class: 'input',
    id: 'new-interview-contact',
    placeholder: '邮箱或手机号（可不填）',
  });

  const submit = el('button', { class: 'btn btn--primary', text: '创建并出题', disabled: loadFailed || !positions.length });

  const form = el(
    'form',
    {
      id: 'create-interview-form',
      onSubmit: (event) => event.preventDefault(),
    },
    loadFailed
      ? el('p', { class: 'field-error', text: '岗位列表加载失败，请关闭后重试。' })
      : null,
    !loadFailed && !positions.length
      ? el('p', { class: 'hint', text: '还没有岗位。先到「岗位」页创建一个，再回来建面试。' })
      : null,

    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-position', text: '岗位' }),
      positionSelect,
      el('p', { class: 'field-note', text: 'AI 会按这个岗位的 JD 和评估维度出题。' }),
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-name', text: '候选人姓名' }),
      nameInput,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'new-interview-contact', text: '联系方式' }),
      contactInput,
    ),
  );

  const handle = openModal({
    title: '创建面试',
    body: form,
    footer: [
      el('button', {
        class: 'btn btn--ghost',
        text: '取消',
        onClick: () => handle.close(),
      }),
      submit,
    ],
  });

  submit.addEventListener('click', async () => {
    if (!nameInput.value.trim()) {
      toast.error('请填写候选人姓名');
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
        candidate_contact: contactInput.value.trim() || null,
      });
      handle.close();
      toast.success(`已生成 ${detail.question_count} 道题`);
      onCreated(detail.id);
    } catch (error) {
      // 后端已整体回滚，可以安全重试 —— 弹窗保持打开
      handle.setBusy(false);
      submit.textContent = '创建并出题';
      toast.error(error.message);
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
    mount(
      main,
      el(
        'div',
        { class: 'panel' },
        emptyState('面试列表加载失败', error.message, el('button', {
          class: 'btn btn--primary',
          text: '重新加载',
          onClick: () => render(container),
        })),
      ),
    );
    return;
  }

  const createButton = el('button', {
    class: 'btn btn--primary',
    text: '创建面试',
    onClick: () => openCreateModal((id) => navigate(`/interviews/${id}`)),
  });

  const reload = () => render(container);

  mount(
    main,
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', { class: 'h-page', text: '面试' }),
        el('p', { class: 'page-lede' }, '一场面试从创建开始：AI 按岗位出题，你逐题记录，完成后一键评估。'),
      ),
      el('div', { class: 'page-head-actions' }, createButton),
    ),

    el(
      'div',
      { class: 'panel' },
      interviews.length
        ? buildTable(interviews)
        : emptyState(
            '还没有面试',
            '创建一场面试，AI 会按岗位和评估维度出题。',
            el('button', {
              class: 'btn btn--primary',
              text: '创建面试',
              onClick: () => openCreateModal((id) => navigate(`/interviews/${id}`)),
            }),
          ),
    ),
  );
}
