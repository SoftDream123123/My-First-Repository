/**
 * pages/positions.js —— 岗位管理
 *
 * 布局是「列表 + 案卷」而不是表格：JD 是成段的文字、评估维度是一组标签，
 * 两者塞进单元格都只能靠截断与展开行。左侧选，右侧读全文。
 *
 * 维度编辑器做前端即时校验 —— 与后端 position 的规则对齐（API 文档 §6.1），
 * 避免提交必然失败的请求。**校验只是提前告知，不作为唯一防线**：
 * 后端 400 的 `detail.fields` 仍然落到同一个出口。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { confirmModal, openModal } from '../components/modal.js';
import { contextTitle, createShell, emptyState, formatDate, loadingBlock, dimTag } from '../components/shell.js';

const MAX_DIMENSIONS = 10;
const MAX_DIMENSION_LENGTH = 50;
const SEARCH_DEBOUNCE_MS = 200;

/* --------------------------- 维度编辑器 --------------------------- */

function validateDimensions(values) {
  const cleaned = values.map((v) => v.trim());
  if (!cleaned.length) return '至少需要 1 个评估维度';
  if (cleaned.length > MAX_DIMENSIONS) return `评估维度不能超过 ${MAX_DIMENSIONS} 个`;
  if (cleaned.some((v) => !v)) return '评估维度不能为空';
  if (cleaned.some((v) => v.length > MAX_DIMENSION_LENGTH)) {
    return `单个评估维度不能超过 ${MAX_DIMENSION_LENGTH} 个字符`;
  }
  // 后端是 **strip 后不区分大小写**去重，且重复视为 400（不是静默去重）
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
  const list = el('div', {});
  const errorNode = el('p', { class: 'field-error', hidden: true });

  function repaint() {
    clear(list);
    values.forEach((value, index) => {
      const input = el('input', {
        class: 'input',
        value,
        maxlength: String(MAX_DIMENSION_LENGTH),
        'aria-label': `评估维度 ${index + 1}`,
        onInput: (event) => { values[index] = event.target.value; },
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
            onClick: () => { values.splice(index, 1); repaint(); },
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
      if (values.length >= MAX_DIMENSIONS) { toast.error(`最多 ${MAX_DIMENSIONS} 个维度`); return; }
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
      el('p', { class: 'field-note', text: '这些维度决定了 AI 出题的方向，也是评估报告里雷达图的轴。' }),
      errorNode,
    ),
    errorNode,
    /** 校验通过返回维度数组，否则返回 null 并把错误显示出来。 */
    read() {
      const error = validateDimensions(values);
      if (error) { errorNode.textContent = error; errorNode.hidden = false; return null; }
      errorNode.hidden = true;
      return values.map((v) => v.trim());
    },
  };
}

/* ------------------------------ 表单弹窗 ------------------------------ */

function openPositionModal(position, onSaved) {
  const isEdit = Boolean(position);

  const nameInput = el('input', {
    class: 'input', id: 'position-name', value: position?.name ?? '', maxlength: '100',
  });

  const jdInput = el('textarea', {
    class: 'textarea', id: 'position-jd', value: position?.jd ?? '', maxlength: '10000', rows: '7',
    placeholder: '写清职责、要求与团队情况。AI 依据这段文字出题，写得越具体，题目越贴合。',
  });

  const editor = buildDimensionEditor(position?.evaluation_dimensions ?? ['沟通能力', '专业能力']);

  // 错误节点必须先建出来、放进表单里，再登记到映射 —— 登记一个游离节点
  // 等于报错永远不显示。维度错误由编辑器自己持有节点，也接到同一条出口上，
  // 这样后端 400 也能落到维度区而不是弹一句笼统的话。
  const nameError = fieldError();
  const jdError = fieldError();
  const errors = fieldErrors({
    name: nameError,
    jd: jdError,
    evaluation_dimensions: editor.errorNode,
  });

  const submit = el('button', { class: 'btn btn--primary', text: isEdit ? '保存' : '创建岗位' });

  const body = el(
    'div',
    {},
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'position-name', text: '岗位名称' }),
      nameInput,
      nameError),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'position-jd', text: '岗位描述（JD）' }),
      jdInput,
      jdError),
    el('div', { class: 'field' },
      el('span', { class: 'field-label', text: '评估维度' }),
      editor.node),
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
    if (!nameInput.value.trim()) { errors.show('name', '请填写岗位名称'); nameInput.focus(); return; }
    if (!jdInput.value.trim()) { errors.show('jd', '请填写岗位描述'); jdInput.focus(); return; }

    const dimensions = editor.read();
    if (!dimensions) return;

    handle.setBusy(true);
    try {
      // PUT 是**全量替换**：`evaluation_dimensions` 整体覆盖而不是追加（API 文档 §6.4）
      const payload = {
        name: nameInput.value.trim(),
        jd: jdInput.value.trim(),
        evaluation_dimensions: dimensions,
      };
      if (isEdit) await api.put(`/positions/${position.id}`, payload);
      else await api.post('/positions', payload);
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

  let selectedId = positions[0]?.id ?? null;
  let keyword = '';
  let searchTimer = null;

  const listBody = el('div', { class: 'split-list-body' });
  const dossier = el('div', { class: 'panel' });
  const split = el('div', { class: 'split' }, el('div', { class: 'split-list' }, listBody), dossier);
  const emptyPanel = el('div', { class: 'panel' });
  const bodyHost = el('div', {}, split, emptyPanel);

  // 模糊匹配由**服务端**做（API 文档 §6.2）：前端过滤一份可能过期的本地副本，
  // 会让「刚被别处删掉的岗位」继续出现在搜索结果里。
  const searchInput = el('input', {
    class: 'input',
    placeholder: '搜索岗位名称',
    onInput: (event) => {
      const value = event.target.value.trim();
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        if (value === keyword) return;
        keyword = value;
        reload();
      }, SEARCH_DEBOUNCE_MS);
    },
  });

  const listPath = () => (keyword ? `/positions?keyword=${encodeURIComponent(keyword)}` : '/positions');

  function create() { openPositionModal(null, reload); }

  async function reload() {
    try {
      positions = await api.get(listPath());
    } catch (error) {
      toast.error(error.message);
      return;
    }
    if (!positions.some((p) => p.id === selectedId)) selectedId = positions[0]?.id ?? null;
    paint();
  }

  async function removePosition(position) {
    const ok = await confirmModal({
      title: `删除岗位「${position.name}」？`,
      message: '如果这个岗位下已经有题目或面试，删除会被拒绝。',
    });
    if (!ok) return;
    try {
      await api.del(`/positions/${position.id}`);
      toast.success('岗位已删除');
      reload();
    } catch (error) {
      toast.error(error.message); // 409 的文案直接来自后端
    }
  }

  function paintList() {
    clear(listBody);
    if (!positions.length) {
      listBody.append(el('p', { class: 'hint', style: 'padding:var(--s4)' }, '没有匹配的岗位。'));
      return;
    }

    for (const position of positions) {
      listBody.append(
        el('button', {
          class: `split-item${position.id === selectedId ? ' is-active' : ''}`,
          type: 'button',
          'aria-current': position.id === selectedId ? 'true' : null,
          onClick: () => { selectedId = position.id; paintList(); paintDossier(); },
        },
          el('div', { class: 'split-item-name', text: position.name }),
          el('div', {
            class: 'split-item-meta',
            text: `${position.evaluation_dimensions.length} 个评估维度`,
          }),
        ),
      );
    }
  }

  function paintDossier() {
    clear(dossier);
    const position = positions.find((p) => p.id === selectedId);
    if (!position) {
      dossier.append(emptyState('请选择一个岗位', '左侧选中后，这里显示它的 JD 与评估维度。'));
      return;
    }

    dossier.append(
      el('div', { class: 'dossier-head' },
        el('div', {},
          el('h2', { class: 'dossier-title', text: position.name }),
          el('div', { class: 'dossier-meta' },
            el('span', { text: `${position.evaluation_dimensions.length} 个评估维度` }),
            el('span', { text: `创建于 ${formatDate(position.created_at)}` }),
          ),
        ),
        el('div', { class: 'dossier-actions' },
          el('button', { class: 'btn btn--ghost', text: '编辑', onClick: () => openPositionModal(position, reload) }),
          el('button', { class: 'btn btn--ghost', text: '删除', onClick: () => removePosition(position) }),
        ),
      ),
      el('div', { class: 'dossier-section' },
        el('div', { class: 'dossier-label', text: '岗位描述（JD）' }),
        el('p', { class: 'dossier-text', text: position.jd }),
      ),
      el('div', { class: 'dossier-section' },
        el('div', { class: 'dossier-label', text: '评估维度' }),
        el('div', { class: 'tag-row' }, position.evaluation_dimensions.map((d) => dimTag(d))),
      ),
    );
  }

  function paint() {
    // 有搜索词时**保留左栏**，哪怕一条都没匹配上 —— 否则搜到 0 条会把搜索框
    // 一起藏掉，用户既看不到「为什么是空的」，也没有地方改回原来的词。
    const showSplit = positions.length > 0 || Boolean(keyword);
    split.hidden = !showSplit;
    emptyPanel.hidden = showSplit;
    if (!showSplit) {
      clear(emptyPanel);
      emptyPanel.append(
        emptyState('还没有岗位', '先建一个岗位，AI 才知道该按什么方向出题。',
          el('button', { class: 'btn btn--primary', text: '创建岗位', onClick: create })),
      );
      return;
    }
    paintList();
    paintDossier();
  }

  mount(
    main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '岗位' }),
        el('p', { class: 'page-lede' }, '岗位决定了 AI 出题的方向，也决定了评估报告按哪些维度打分。'),
      ),
      el('div', { class: 'page-head-actions' },
        el('button', { class: 'btn btn--primary', text: '创建岗位', onClick: create })),
    ),
    bodyHost,
  );

  // 搜索框只在有条目时才存在（一条岗位都没有时没什么可搜的）
  if (positions.length) split.querySelector('.split-list').prepend(el('div', { class: 'split-list-head' }, searchInput));
  paint();
}
