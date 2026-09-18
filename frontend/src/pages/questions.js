/**
 * 题库管理（module-07 §5.6）。
 *
 * 筛选栏对应 PRD §4.3 的「按岗位 / 分类 / 维度筛选」，多个条件为 AND。
 * 表单里选岗位后，维度字段变成该岗位维度的下拉 —— 否则提交必然被后端拒绝。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { confirmModal, openModal } from '../components/modal.js';
import {
  contextTitle,
  createShell,
  dimTag,
  emptyState,
  loadingBlock,
  sourceTag,
} from '../components/shell.js';

const DIFFICULTY_LABELS = { easy: '易', medium: '中', hard: '难' };

const MAX_TAGS = 10;
const MAX_TAG_LENGTH = 20;

/** 标签用顿号或逗号分隔 —— 与后端 tags 数组对应。 */
function parseTags(raw) {
  return raw
    .split(/[、,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/* ------------------------------ 表单弹窗 ------------------------------ */

function openQuestionModal(positions, question, onSaved) {
  const isEdit = Boolean(question);

  const positionSelect = el(
    'select',
    { class: 'select', id: 'question-position' },
    positions.map((p) =>
      el('option', {
        value: p.id,
        text: p.name,
        selected: question ? p.id === question.position_id : false,
      }),
    ),
  );

  // 维度随岗位联动为下拉 —— 候选值就是该岗位的评估维度
  const dimensionSelect = el('select', { class: 'select', id: 'question-dimension' });

  function syncDimensions() {
    const position = positions.find((p) => p.id === Number(positionSelect.value));
    clear(dimensionSelect);

    if (!position) {
      dimensionSelect.append(el('option', { value: '', text: '请先选择岗位' }));
      dimensionSelect.disabled = true;
      return;
    }

    dimensionSelect.disabled = false;
    position.evaluation_dimensions.forEach((dimension) => {
      dimensionSelect.append(
        el('option', {
          value: dimension,
          text: dimension,
          selected: question ? dimension === question.dimension : false,
        }),
      );
    });
  }

  positionSelect.addEventListener('change', syncDimensions);
  syncDimensions();

  const contentInput = el('textarea', {
    class: 'textarea',
    id: 'question-content',
    value: question?.content ?? '',
    maxlength: '2000',
    placeholder: '写具体一点。好的面试题通常指向一个真实场景，而不是让人背诵定义。',
  });
  const contentError = fieldError();

  const categoryInput = el('input', {
    class: 'input',
    id: 'question-category',
    value: question?.category ?? '通用',
    maxlength: '50',
  });
  const categoryError = fieldError();

  const difficultySelect = el(
    'select',
    { class: 'select', id: 'question-difficulty' },
    ['easy', 'medium', 'hard'].map((value) =>
      el('option', {
        value,
        text: DIFFICULTY_LABELS[value],
        selected: question ? question.difficulty === value : value === 'medium',
      }),
    ),
  );

  const tagsInput = el('input', {
    class: 'input',
    id: 'question-tags',
    value: (question?.tags ?? []).join('、'),
    placeholder: '用顿号或逗号分隔，最多 10 个',
  });
  const tagsError = fieldError();

  // 键名与后端 detail.fields[].field 一致
  const errors = fieldErrors({
    content: contentError,
    category: categoryError,
    tags: tagsError,
  });

  const body = el(
    'div',
    {},
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-position', text: '所属岗位' }),
      positionSelect,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-dimension', text: '考察维度' }),
      dimensionSelect,
      el('p', { class: 'field-note', text: '维度只能从所属岗位的评估维度里选。' }),
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-content', text: '题干' }),
      contentInput,
      el('p', { class: 'field-note', text: '5–2000 字。' }),
      contentError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-category', text: '分类' }),
      categoryInput,
      categoryError,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-difficulty', text: '难度' }),
      difficultySelect,
    ),
    el(
      'div',
      { class: 'field' },
      el('label', { class: 'field-label', for: 'question-tags', text: '标签' }),
      tagsInput,
      el('p', { class: 'field-note', text: '用顿号或逗号分隔。最多 10 个，每个不超过 20 字。' }),
      tagsError,
    ),
  );

  const submit = el('button', { class: 'btn btn--primary', text: isEdit ? '保存' : '创建题目' });

  const handle = openModal({
    title: isEdit ? '编辑题目' : '创建题目',
    body,
    wide: true,
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      submit,
    ],
  });

  submit.addEventListener('click', async () => {
    errors.clear();

    const content = contentInput.value.trim();
    if (content.length < 5) {
      errors.show('content', '题干至少 5 个字');
      contentInput.focus();
      return;
    }

    const tags = parseTags(tagsInput.value);
    if (tags.length > MAX_TAGS) {
      errors.show('tags', `标签最多 ${MAX_TAGS} 个，当前 ${tags.length} 个`);
      tagsInput.focus();
      return;
    }
    const tooLong = tags.find((tag) => tag.length > MAX_TAG_LENGTH);
    if (tooLong) {
      errors.show('tags', `单个标签不能超过 ${MAX_TAG_LENGTH} 个字符：${tooLong}`);
      tagsInput.focus();
      return;
    }

    handle.setBusy(true);
    try {
      const payload = {
        position_id: Number(positionSelect.value),
        dimension: dimensionSelect.value,
        content,
        category: categoryInput.value.trim() || '通用',
        difficulty: difficultySelect.value,
        tags,
      };
      if (isEdit) {
        await api.put(`/questions/${question.id}`, payload);
      } else {
        await api.post('/questions', payload);
      }
      handle.close();
      toast.success(isEdit ? '题目已保存' : '题目已创建');
      onSaved();
    } catch (error) {
      handle.setBusy(false);
      // 字段格式类 400（content 越界等）走 detail.fields，落到字段下方；
      // 维度不属岗位返回的是 detail.{dimension,allowed}，不含 fields，
      // 所以落到 else 分支，用后端那句「该维度不属于岗位的评估维度」提示。
      if (!errors.fromServer(error)) toast.error(error.message);
    }
  });
}

/* -------------------------------- 页面 -------------------------------- */

export async function render(container) {
  const { root, main } = createShell(contextTitle('题库'));
  mount(container, root);
  mount(main, loadingBlock('正在加载题库…'));

  let positions;
  try {
    positions = await api.get('/positions');
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('题库加载失败', error.message)));
    return;
  }

  const filters = {
    position_id: '',
    category: '',
    dimension: '',
    source: '',
    keyword: '',
  };

  const tableBody = el('tbody', {});
  const countNode = el('span', { class: 'meta' });

  function query() {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const qs = params.toString();
    return `/questions${qs ? `?${qs}` : ''}`;
  }

  async function reload() {
    clear(tableBody);
    let questions = [];
    try {
      questions = await api.get(query());
    } catch (error) {
      toast.error(error.message);
      return;
    }

    countNode.textContent = `${questions.length} 道题`;

    if (!questions.length) {
      clear(tableBody);
      tableBody.append(
        el(
          'tr',
          {},
          el(
            'td',
            { colspan: '6' },
            emptyState('没有匹配的题目', '换个筛选条件，或者新建一道。'),
          ),
        ),
      );
      return;
    }

    questions.forEach((question) => tableBody.append(buildRow(question)));
  }

  function buildRow(question) {
    const position = positions.find((p) => p.id === question.position_id);

    return el(
      'tr',
      {},
      el(
        'td',
        {},
        el('span', {
          class: 'truncate',
          style: 'max-width:38ch',
          text: question.content,
          title: question.content,
        }),
      ),
      el('td', { class: 'meta', text: position?.name ?? '—' }),
      el('td', {}, dimTag(question.dimension)),
      el('td', { class: 'meta', text: question.category }),
      el('td', { class: 'meta', text: DIFFICULTY_LABELS[question.difficulty] ?? question.difficulty }),
      el('td', {}, sourceTag(question.source)),
      el(
        'td',
        { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: '编辑',
          onClick: () => openQuestionModal(positions, question, reload),
        }),
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: '删除',
          onClick: async () => {
            const ok = await confirmModal({
              title: '删除这道题？',
              message: '如果它已经被某场面试引用，删除会被拒绝。',
            });
            if (!ok) return;
            try {
              await api.del(`/questions/${question.id}`);
              toast.success('题目已删除');
              reload();
            } catch (error) {
              toast.error(error.message);
            }
          },
        }),
      ),
    );
  }

  /* ---------------------------- 筛选栏 ---------------------------- */

  const positionFilter = el(
    'select',
    {
      class: 'select',
      'aria-label': '按岗位筛选',
      onChange: (event) => {
        filters.position_id = event.target.value;
        reload();
      },
    },
    el('option', { value: '', text: '全部岗位' }),
    positions.map((p) => el('option', { value: p.id, text: p.name })),
  );

  const dimensionFilter = el('input', {
    class: 'input',
    placeholder: '维度',
    'aria-label': '按维度筛选',
    onInput: (event) => {
      filters.dimension = event.target.value.trim();
      reload();
    },
  });

  const categoryFilter = el('input', {
    class: 'input',
    placeholder: '分类',
    'aria-label': '按分类筛选',
    onInput: (event) => {
      filters.category = event.target.value.trim();
      reload();
    },
  });

  const sourceFilter = el(
    'select',
    {
      class: 'select',
      'aria-label': '按来源筛选',
      onChange: (event) => {
        filters.source = event.target.value;
        reload();
      },
    },
    el('option', { value: '', text: '全部来源' }),
    el('option', { value: 'bank', text: '手工' }),
    el('option', { value: 'ai', text: 'AI' }),
  );

  const keywordFilter = el('input', {
    class: 'input',
    placeholder: '搜索题干',
    style: 'min-width:200px',
    'aria-label': '搜索题干',
    onInput: (event) => {
      filters.keyword = event.target.value.trim();
      reload();
    },
  });

  const canCreate = positions.length > 0;

  mount(
    main,
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', { class: 'h-page', text: '题库' }),
        el('p', { class: 'page-lede' }, '手工维护的题会优先被抽中；AI 在面试创建时补充的题也会收录到这里。'),
      ),
      el(
        'div',
        { class: 'page-head-actions' },
        el('button', {
          class: 'btn btn--primary',
          text: '创建题目',
          disabled: !canCreate,
          title: canCreate ? '' : '请先创建岗位',
          onClick: () => openQuestionModal(positions, null, reload),
        }),
      ),
    ),

    el(
      'div',
      { class: 'panel' },
      el(
        'div',
        { class: 'filterbar' },
        positionFilter,
        dimensionFilter,
        categoryFilter,
        sourceFilter,
        keywordFilter,
        el('span', { class: 'filterbar-spacer' }),
        countNode,
      ),
      el(
        'table',
        { class: 'table' },
        el(
          'thead',
          {},
          el(
            'tr',
            {},
            el('th', { text: '题干' }),
            el('th', { text: '岗位' }),
            el('th', { text: '维度' }),
            el('th', { text: '分类' }),
            el('th', { text: '难度' }),
            el('th', { text: '来源' }),
            el('th', {}),
          ),
        ),
        tableBody,
      ),
    ),
  );

  await reload();
}
