/**
 * 岗位管理（module-07 §5.5）。
 *
 * 维度编辑器做前端即时校验 —— 与后端 position §3.3 的规则对齐，
 * 避免提交必然失败的请求。
 */

import { el, mount, clear, append } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { confirmModal, openModal } from '../components/modal.js';
import {
  contextTitle,
  createShell,
  emptyState,
  formatDate,
  loadingBlock,
} from '../components/shell.js';

const MAX_DIMENSIONS = 10;
const MAX_DIMENSION_LENGTH = 50;

/* --------------------------- 维度编辑器 --------------------------- */

function validateDimensions(values) {
  const cleaned = values.map((v) => v.trim());
  if (!cleaned.length) return '至少需要 1 个评估维度';
  if (cleaned.length > MAX_DIMENSIONS) return `评估维度不能超过 ${MAX_DIMENSIONS} 个`;
  if (cleaned.some((v) => !v)) return '评估维度不能为空';
  if (cleaned.some((v) => v.length > MAX_DIMENSION_LENGTH)) {
    return `单个评估维度不能超过 ${MAX_DIMENSION_LENGTH} 个字符`;
  }

  const seen = new Set();
  for (const value of cleaned) {
    const key = value.toLowerCase();
    if (seen.has(key)) return `评估维度重复：${value}`;
    seen.add(key);
  }

  return null;
}

function buildDimensionEditor(initial) {
  const values = [...initial];
  const list = el('div', { class: 'dim-editor' });
  const errorNode = el('p', { class: 'field-error', hidden: true });

  function repaint() {
    clear(list);
    values.forEach((value, index) => {
      const input = el('input', {
        class: 'input',
        value,
        maxlength: String(MAX_DIMENSION_LENGTH),
        'aria-label': `评估维度 ${index + 1}`,
        onInput: (event) => {
          values[index] = event.target.value;
        },
      });

      list.append(
        el(
          'div',
          { class: 'dim-editor-row' },
          input,
          el('button', {
            class: 'btn btn--quiet dim-editor-remove',
            type: 'button',
            text: '×',
            title: '删除这一项',
            'aria-label': `删除维度 ${index + 1}`,
            onClick: () => {
              values.splice(index, 1);
              repaint();
            },
          }),
        ),
      );
    });
  }

  repaint();

  const addButton = el('button', {
    class: 'btn btn--ghost btn--sm',
    type: 'button',
    text: '添加维度',
    onClick: () => {
      if (values.length >= MAX_DIMENSIONS) {
        toast.error(`最多 ${MAX_DIMENSIONS} 个维度`);
        return;
      }
      values.push('');
      repaint();
      list.querySelector('.dim-editor-row:last-child .input')?.focus();
    },
  });

  return {
    node: el(
      'div',
      {},
      list,
      el('div', { style: 'margin-top:8px' }, addButton),
      el('p', {
        class: 'field-note',
        text: '这些维度决定了 AI 出题的方向，也是评估报告里雷达图的轴。',
      }),
      errorNode,
    ),
    /** 校验通过返回维度数组，否则返回 null 并把错误显示出来。 */
    read() {
      const error = validateDimensions(values);
      if (error) {
        errorNode.textContent = error;
        errorNode.hidden = false;
        return null;
      }
      errorNode.hidden = true;
      return values.map((v) => v.trim());
    },
  };
}

/* ------------------------------ 表单弹窗 ------------------------------ */

function openPositionModal(position, onSaved) {
  const isEdit = Boolean(position);

  const nameInput = el('input', {
    class: 'input',
    id: 'position-name',
    value: position?.name ?? '',
    maxlength: '100',
  });

  const jdInput = el('textarea', {
    class: 'textarea',
    id: 'position-jd',
    value: position?.jd ?? '',
    maxlength: '10000',
    placeholder: '写清职责、要求与团队情况。AI 依据这段文字出题，写得越具体，题目越贴合。',
  });

  // 键名与后端 detail.fields[].field 一致
  const nameError = fieldError();
  const jdError = fieldError();
  const errors = fieldErrors({ name: nameError, jd: jdError });

  const editor = buildDimensionEditor(position?.evaluation_dimensions ?? ['沟通能力', '专业能力']);

  const submit = el('button', { class: 'btn btn--primary', text: isEdit ? '保存' : '创建岗位' });

  const body = el(
    'div',
    {},
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'position-name', text: '岗位名称' }),
      nameInput,
      nameError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'position-jd', text: '岗位描述（JD）' }),
      jdInput,
      jdError,
    ),
    el('div', { class: 'field' }, el('span', { class: 'field-label', text: '评估维度' }), editor.node),
  );

  const handle = openModal({
    title: isEdit ? '编辑岗位' : '创建岗位',
    body,
    wide: true,
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      submit,
    ],
  });

  submit.addEventListener('click', async () => {
    errors.clear();

    if (!nameInput.value.trim()) {
      errors.show('name', '请填写岗位名称');
      nameInput.focus();
      return;
    }
    if (!jdInput.value.trim()) {
      errors.show('jd', '请填写岗位描述');
      jdInput.focus();
      return;
    }

    const dimensions = editor.read();
    if (!dimensions) return;

    handle.setBusy(true);
    try {
      const payload = {
        name: nameInput.value.trim(),
        jd: jdInput.value.trim(),
        evaluation_dimensions: dimensions,
      };
      if (isEdit) {
        await api.put(`/positions/${position.id}`, payload);
      } else {
        await api.post('/positions', payload);
      }
      handle.close();
      toast.success(isEdit ? '岗位已保存' : '岗位已创建');
      onSaved();
    } catch (error) {
      handle.setBusy(false);
      // 400 落到字段；409（岗位名已存在）等仍用后端文案提示
      if (!errors.fromServer(error)) toast.error(error.message);
    }
  });
}

/* -------------------------------- 页面 -------------------------------- */

export async function render(container) {
  const { root, main } = createShell(contextTitle('岗位'));
  mount(container, root);
  mount(main, loadingBlock('正在加载岗位…'));

  let positions;
  try {
    positions = await api.get('/positions');
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('岗位加载失败', error.message)));
    return;
  }

  const keyword = el('input', {
    class: 'input',
    placeholder: '搜索岗位名称',
    style: 'min-width:200px',
    onInput: (event) => filter(event.target.value.trim()),
  });

  const tableBody = el('tbody', {});

  function filter(text) {
    clear(tableBody);
    const matched = positions.filter((p) => !text || p.name.includes(text));

    // buildRow 返回 [主行, JD 展开行]，交给 dom.js 的 append 展开
    // —— 原生 append 会把数组字符串化成 "[object HTMLTableRowElement]"
    matched.forEach((position) => append(tableBody, buildRow(position)));

    if (!matched.length) {
      clear(tableBody);
      tableBody.append(
        el('tr', {}, el('td', { colspan: '5' }, emptyState('没有匹配的岗位', '换个关键词试试。'))),
      );
    }
  }

  function buildRow(position) {
    const jdRow = el('tr', { hidden: true }, el('td', { colspan: '5', class: 'jd-expand', text: position.jd }));
    let expanded = false;

    const row = el(
      'tr',
      {},
      el('td', {}, el('strong', { text: position.name })),
      el(
        'td',
        {},
        el('span', { class: 'meta truncate', text: position.jd, title: position.jd }),
      ),
      el(
        'td',
        {},
        el('span', { class: 'tag tag--dim', text: `${position.evaluation_dimensions.length} 个维度` }),
        el('span', {
          class: 'meta truncate',
          style: 'margin-top:4px;max-width:22ch',
          text: position.evaluation_dimensions.join('、'),
          title: position.evaluation_dimensions.join('、'),
        }),
      ),
      el('td', { class: 'meta', text: formatDate(position.created_at) }),
      el(
        'td',
        { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: 'JD',
          onClick: () => {
            expanded = !expanded;
            jdRow.hidden = !expanded;
          },
        }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: '编辑',
          onClick: () => openPositionModal(position, () => render(container)),
        }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: '删除',
          onClick: async () => {
            const ok = await confirmModal({
              title: `删除岗位「${position.name}」？`,
              message: '如果这个岗位下已经有题目或面试，删除会被拒绝。',
            });
            if (!ok) return;
            try {
              await api.del(`/positions/${position.id}`);
              toast.success('岗位已删除');
              render(container);
            } catch (error) {
              // 409 的文案直接来自后端
              toast.error(error.message);
            }
          },
        }),
      ),
    );

    return [row, jdRow];
  }

  mount(
    main,
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', { class: 'h-page', text: '岗位' }),
        el('p', { class: 'page-lede' }, '岗位决定了 AI 出题的方向，也决定了评估报告按哪些维度打分。'),
      ),
      el(
        'div',
        { class: 'page-head-actions' },
        el('button', {
          class: 'btn btn--primary',
          text: '创建岗位',
          onClick: () => openPositionModal(null, () => render(container)),
        }),
      ),
    ),

    el(
      'div',
      { class: 'panel' },
      el('div', { class: 'filterbar' }, keyword),
      el(
        'table',
        { class: 'table' },
        el(
          'thead',
          {},
          el(
            'tr',
            {},
            el('th', { text: '岗位名称' }),
            el('th', { text: '岗位描述' }),
            el('th', { text: '评估维度' }),
            el('th', { text: '创建时间' }),
            el('th', {}),
          ),
        ),
        tableBody,
      ),
    ),
  );

  if (positions.length) {
    filter('');
  } else {
    clear(tableBody);
    tableBody.append(
      el(
        'tr',
        {},
        el(
          'td',
          { colspan: '5' },
          emptyState(
            '还没有岗位',
            '先建一个岗位，AI 才知道该按什么方向出题。',
            el('button', {
              class: 'btn btn--primary',
              text: '创建岗位',
              onClick: () => openPositionModal(null, () => render(container)),
            }),
          ),
        ),
      ),
    );
  }
}
