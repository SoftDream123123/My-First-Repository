/**
 * pages/questions.js —— 题库管理
 *
 * 同样是「列表 + 案卷」：题干、选项、参考答案、解析都是成段内容，
 * 表格里放不下，而 HR 维护题库时恰恰要通读这几块。
 *
 * 筛选条只放**后端真的支持**的六项（position_id / category / dimension /
 * source / question_type / keyword）。PRD §4.3 提到「按难度筛选」，但
 * HR 的列表端点**并没有这个参数**（传了会被 FastAPI 静默忽略，见 API 文档 §7.2
 * 与测试报告 §8.3）—— 按接口来，不为没实现的能力造控件。
 */

import { el, mount, clear, append } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { fieldError, fieldErrors } from '../components/form.js';
import { confirmModal, openModal } from '../components/modal.js';
import { contextTitle, createShell, emptyState, loadingBlock, dimTag, sourceTag } from '../components/shell.js';

const DIFFICULTY_LABELS = { easy: '易', medium: '中', hard: '难' };
const TYPE_LABELS = { single_choice: '单选题', short_answer: '简答题' };

const MAX_TAGS = 10;
const MAX_TAG_LENGTH = 20;
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 10;
const MAX_OPTION_LENGTH = 200;
const MIN_CONTENT = 5;

/** 标签用顿号或逗号分隔 —— 与后端 tags 数组对应。 */
function parseTags(raw) {
  return raw.split(/[、,，]/).map((tag) => tag.trim()).filter(Boolean);
}

/** 选项的显示记号 A / B / C…（答案文本本身不含字母，这里只做索引） */
function letter(index) { return String.fromCharCode(65 + index); }

/* --------------------------- 选项编辑器 --------------------------- */

/**
 * 参考答案在编辑期用**选项下标**表示，而不是选项文本。
 * 用文本的话，用户改一个错别字就会让已选中的答案悄无声息地失效。
 */
function buildChoiceEditor(initialOptions, initialAnswer) {
  const options = [...initialOptions];
  let answerIndex = initialOptions.indexOf(initialAnswer);
  if (answerIndex < 0) answerIndex = null;

  const list = el('div', {});
  const errorNode = el('p', { class: 'field-error', hidden: true });
  const answerSelect = el('select', {
    class: 'select',
    id: 'question-answer',
    onChange: (event) => { answerIndex = event.target.value === '' ? null : Number(event.target.value); },
  });

  function repaintList() {
    clear(list);
    options.forEach((text, index) => {
      list.append(
        el('div', { class: 'choice-row' },
          el('span', { class: 'choice-key', text: letter(index) }),
          el('input', {
            class: 'input',
            value: text,
            maxlength: String(MAX_OPTION_LENGTH),
            'aria-label': `选项 ${letter(index)}`,
            onInput: (event) => {
              options[index] = event.target.value;
              // 只改下拉里那一项的文字，不重建 —— 重建会把已选中的答案冲掉
              const node = answerSelect.options[index + 1]; // 0 号是「请选择」
              if (node) node.textContent = options[index] || `选项 ${letter(index)}`;
            },
          }),
          el('button', {
            class: 'btn btn--quiet dim-editor-remove',
            type: 'button',
            text: '×',
            title: '删除这一项',
            'aria-label': `删除选项 ${letter(index)}`,
            onClick: () => {
              options.splice(index, 1);
              // 删掉的那一项就是答案时清空；排在答案前面的项会让答案下标左移一位
              if (answerIndex === index) answerIndex = null;
              else if (answerIndex !== null && answerIndex > index) answerIndex -= 1;
              repaint();
            },
          }),
        ),
      );
    });
  }

  function repaintAnswer() {
    if (answerIndex !== null && answerIndex >= options.length) answerIndex = null;
    clear(answerSelect);
    answerSelect.append(el('option', { value: '', text: '请选择' }));
    options.forEach((text, index) => {
      answerSelect.append(el('option', { value: String(index), text: text || `选项 ${letter(index)}` }));
    });
    answerSelect.value = answerIndex === null ? '' : String(answerIndex);
  }

  function repaint() { repaintList(); repaintAnswer(); }
  repaint();

  const addButton = el('button', {
    class: 'btn btn--ghost btn--sm',
    type: 'button',
    text: '添加选项',
    onClick: () => {
      if (options.length >= MAX_OPTIONS) { toast.error(`最多 ${MAX_OPTIONS} 个选项`); return; }
      options.push('');
      repaint();
      list.querySelector('.choice-row:last-child .input')?.focus();
    },
  });

  return {
    node: el('div', {}, list, el('div', { style: 'margin-top:8px' }, addButton), errorNode),
    errorNode,
    answerSelect,
    /** 由「AI 生成参考答案」写回时用 —— 传进来的是选项文本。 */
    setAnswer(text) {
      answerIndex = options.indexOf(text);
      if (answerIndex < 0) answerIndex = null;
      repaintAnswer();
    },
    /** 校验通过返回 { options, reference_answer }，否则显示错误并返回 null。 */
    read() {
      const cleaned = options.map((o) => o.trim());
      let error = null;
      if (cleaned.length < MIN_OPTIONS) error = `单选题至少需要 ${MIN_OPTIONS} 个选项`;
      else if (cleaned.length > MAX_OPTIONS) error = `单选题最多 ${MAX_OPTIONS} 个选项`;
      else if (cleaned.some((o) => !o)) error = '选项不能为空';
      else if (cleaned.some((o) => o.length > MAX_OPTION_LENGTH)) error = `单个选项不能超过 ${MAX_OPTION_LENGTH} 个字符`;
      else if (new Set(cleaned).size !== cleaned.length) error = '选项不能重复';
      else if (answerIndex === null) error = '单选题必须提供参考答案';

      if (error) { errorNode.textContent = error; errorNode.hidden = false; return null; }
      errorNode.hidden = true;
      return { options: cleaned, reference_answer: cleaned[answerIndex] };
    },
  };
}

/* ------------------------------ 表单弹窗 ------------------------------ */

function openQuestionModal(positions, question, onSaved) {
  const isEdit = Boolean(question);

  const positionSelect = el(
    'select',
    { class: 'select', id: 'question-position' },
    positions.map((p) => el('option', { value: String(p.id), text: p.name })),
  );
  if (question) positionSelect.value = String(question.position_id);

  // 维度随岗位联动为下拉 —— 候选值就是该岗位的评估维度，否则提交必然被拒绝
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
      dimensionSelect.append(el('option', { value: dimension, text: dimension }));
    });
    // 编辑时只有「岗位没被改过」才回填原维度 —— 换岗位后旧维度已经不属于它了
    if (question && position.id === question.position_id) dimensionSelect.value = question.dimension;
  }
  positionSelect.addEventListener('change', syncDimensions);

  const contentInput = el('textarea', {
    class: 'textarea', id: 'question-content', rows: '4', maxlength: '2000',
    value: question?.content ?? '',
    placeholder: '写具体一点。好的面试题通常指向一个真实场景，而不是让人背诵定义。',
  });
  const contentError = fieldError();

  const choiceEditor = buildChoiceEditor(question?.options ?? ['', ''], question?.reference_answer ?? null);

  const shortAnswerInput = el('textarea', {
    class: 'textarea', id: 'question-reference', rows: '3', maxlength: '2000',
    value: question && question.question_type === 'short_answer' ? (question.reference_answer ?? '') : '',
    placeholder: '可选。留空表示还没有标准答案，之后可以用 AI 生成再改。',
  });

  const explanationInput = el('textarea', {
    class: 'textarea', id: 'question-explanation', rows: '3', maxlength: '2000',
    value: question?.explanation ?? '',
    placeholder: '可选。写清这道题在考什么、可追问哪些方向，评估时也用得上。',
  });

  const categoryInput = el('input', {
    class: 'input', id: 'question-category', maxlength: '50', value: question?.category ?? '通用',
  });
  const categoryError = fieldError();

  const difficultySelect = el(
    'select',
    { class: 'select', id: 'question-difficulty' },
    ['easy', 'medium', 'hard'].map((value) => el('option', { value, text: DIFFICULTY_LABELS[value] })),
  );
  difficultySelect.value = question?.difficulty ?? 'medium';

  const tagsInput = el('input', {
    class: 'input', id: 'question-tags', value: (question?.tags ?? []).join('、'),
    placeholder: '用顿号或逗号分隔，最多 10 个',
  });
  const tagsError = fieldError();

  const errors = fieldErrors({
    content: contentError,
    category: categoryError,
    tags: tagsError,
    options: choiceEditor.errorNode,
  });

  /* ---- 题型：二选一，且它会改变表单结构，所以做成醒目的分段控件 ---- */
  // 默认是**简答**：存量题库里的题没有选项，按简答理解才符合事实（API 文档 §7.1）
  let type = question?.question_type ?? 'short_answer';

  const choiceBlock = el('div', { class: 'field' },
    el('span', { class: 'field-label', text: '选项' }),
    choiceEditor.node);

  const choiceAnswerBlock = el('div', { class: 'field' },
    el('span', { class: 'field-label', text: '参考答案' }),
    el('p', { class: 'field-note', style: 'margin-bottom:8px' }, '单选题的参考答案必须是其中一个选项 —— 判分时就按它比对。'),
    choiceEditor.answerSelect);

  const shortAnswerBlock = el('div', { class: 'field' },
    el('label', { class: 'field-label', for: 'question-reference', text: '参考答案' }),
    shortAnswerInput);

  const segButtons = {
    single_choice: el('button', { class: 'seg-btn', type: 'button', text: TYPE_LABELS.single_choice }),
    short_answer: el('button', { class: 'seg-btn', type: 'button', text: TYPE_LABELS.short_answer }),
  };

  function paintType() {
    for (const [key, button] of Object.entries(segButtons)) {
      button.className = `seg-btn${key === type ? ' is-on' : ''}`;
    }
    const isSingle = type === 'single_choice';
    choiceBlock.hidden = !isSingle;
    choiceAnswerBlock.hidden = !isSingle;
    shortAnswerBlock.hidden = isSingle;
  }
  for (const [key, button] of Object.entries(segButtons)) {
    button.addEventListener('click', () => { type = key; paintType(); });
  }

  const typeBlock = el('div', { class: 'field' },
    el('span', { class: 'field-label', text: '题型' }),
    el('div', { class: 'seg' }, segButtons.single_choice, segButtons.short_answer));

  const body = el(
    'div',
    {},
    el('div', { class: 'form-grid' },
      el('div', { class: 'field' },
        el('label', { class: 'field-label', for: 'question-position', text: '所属岗位' }),
        positionSelect),
      el('div', { class: 'field' },
        el('label', { class: 'field-label', for: 'question-dimension', text: '考察维度' }),
        dimensionSelect),
    ),
    typeBlock,
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'question-content', text: '题干' }),
      contentInput,
      el('p', { class: 'field-note', text: '5–2000 字。' }),
      contentError),
    choiceBlock,
    choiceAnswerBlock,
    shortAnswerBlock,
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'question-explanation', text: '解析' }),
      explanationInput),
    el('div', { class: 'form-grid' },
      el('div', { class: 'field' },
        el('label', { class: 'field-label', for: 'question-category', text: '分类' }),
        categoryInput, categoryError),
      el('div', { class: 'field' },
        el('label', { class: 'field-label', for: 'question-difficulty', text: '难度' }),
        difficultySelect),
    ),
    el('div', { class: 'field' },
      el('label', { class: 'field-label', for: 'question-tags', text: '标签' }),
      tagsInput,
      el('p', { class: 'field-note', text: '用顿号或逗号分隔。最多 10 个，每个不超过 20 字。' }),
      tagsError),
  );

  const submit = el('button', { class: 'btn btn--primary', text: isEdit ? '保存' : '创建题目' });

  // AI 生成参考答案：端点按题目 id 工作，所以只有已保存的题才能用
  const aiButton = el('button', {
    class: 'btn btn--ghost',
    type: 'button',
    text: 'AI 生成参考答案',
    disabled: !isEdit,
    title: isEdit ? '由 AI 写出参考答案与解析，写回后可继续手工修改' : '先保存这道题，才能用 AI 生成参考答案',
    onClick: async () => {
      aiButton.disabled = true;
      const before = aiButton.textContent;
      aiButton.textContent = '生成中…';
      try {
        const updated = await api.post(`/questions/${question.id}/reference-answer`);
        if (updated.question_type === 'single_choice') {
          choiceEditor.setAnswer(updated.reference_answer);
        } else {
          shortAnswerInput.value = updated.reference_answer ?? '';
        }
        explanationInput.value = updated.explanation ?? '';
        toast.success('已生成，可直接修改后保存');
      } catch (error) {
        // 后端文案，例如「AI 生成的答案不在选项中，请手工确认」
        toast.error(error.message);
      } finally {
        aiButton.disabled = false;
        aiButton.textContent = before;
      }
    },
  });

  const handle = openModal({
    title: isEdit ? '编辑题目' : '创建题目',
    body,
    wide: true,
    footer: [aiButton, el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }), submit],
  });

  syncDimensions();
  paintType();

  submit.addEventListener('click', async () => {
    errors.clear();

    const content = contentInput.value.trim();
    if (content.length < MIN_CONTENT) { errors.show('content', `题干至少 ${MIN_CONTENT} 个字`); contentInput.focus(); return; }

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

    let options = [];
    let referenceAnswer;
    if (type === 'single_choice') {
      const choice = choiceEditor.read();
      if (!choice) return;
      options = choice.options;
      referenceAnswer = choice.reference_answer;
    } else {
      referenceAnswer = shortAnswerInput.value.trim() || null;
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
        question_type: type,
        options,
        reference_answer: referenceAnswer,
        explanation: explanationInput.value.trim() || null,
      };
      if (isEdit) await api.put(`/questions/${question.id}`, payload);
      else await api.post('/questions', payload);
      handle.close();
      toast.success(isEdit ? '题目已保存' : '题目已创建');
      onSaved();
    } catch (error) {
      handle.setBusy(false);
      // 字段格式类 400（content / tags 越界）带 detail.fields，落到字段下方；
      // 选项与答案类规则、维度不属岗位返回的是别的 detail 形状（不含 fields），
      // 所以落到 else 分支，用后端原话提示。
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

  let questions = [];
  let selectedId = null;
  let reloadNo = 0; // 并发请求的序号，用来丢弃过期响应
  const filters = { position_id: '', question_type: '', dimension: '', category: '', source: '', keyword: '' };

  const listBody = el('div', { class: 'split-list-body' });
  const dossier = el('div', { class: 'panel' });
  const split = el('div', { class: 'split split--wide' }, el('div', { class: 'split-list' }, listBody), dossier);
  const emptyPanel = el('div', { class: 'panel' });
  const bodyHost = el('div', {}, split, emptyPanel);
  const countNode = el('span', { class: 'filterbar-count' });

  function create() { openQuestionModal(positions, null, reload); }

  function query() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
    const qs = params.toString();
    return `/questions${qs ? `?${qs}` : ''}`;
  }

  async function reload() {
    // 筛选栏每次改动都会发一次请求（关键词还是逐键触发），请求会并发。
    // 没有这个序号守卫时，先发的请求可能后返回，把新筛选的结果覆盖成旧的。
    const requestNo = ++reloadNo;
    let rows;
    try {
      rows = await api.get(query());
    } catch (error) {
      if (requestNo === reloadNo) toast.error(error.message);
      return;
    }
    if (requestNo !== reloadNo) return; // 已经有更新的请求发出，这次的结果作废

    questions = rows;
    if (!questions.some((q) => q.id === selectedId)) selectedId = questions[0]?.id ?? null;
    syncCategoryOptions();
    paint();
  }

  async function removeQuestion(question) {
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
      toast.error(error.message); // 409 的文案直接来自后端
    }
  }

  function paintList() {
    clear(listBody);
    if (!questions.length) {
      listBody.append(el('p', { class: 'hint', style: 'padding:var(--s4)' }, '没有匹配的题目。'));
      return;
    }
    for (const question of questions) {
      const position = positions.find((p) => p.id === question.position_id);
      listBody.append(
        el('button', {
          class: `split-item${question.id === selectedId ? ' is-active' : ''}`,
          type: 'button',
          'aria-current': question.id === selectedId ? 'true' : null,
          onClick: () => { selectedId = question.id; paintList(); paintDossier(); },
        },
          el('div', { class: 'split-item-text', text: question.content }),
          el('div', { class: 'split-item-tags' },
            el('span', { class: 'tag tag--dim', text: TYPE_LABELS[question.question_type] ?? question.question_type }),
            el('span', { class: 'tag tag--dim', text: DIFFICULTY_LABELS[question.difficulty] ?? question.difficulty }),
            el('span', { class: 'split-item-pos', text: position?.name ?? '—' }),
          ),
        ),
      );
    }
  }

  function section(label, node) {
    return el('div', { class: 'dossier-section' },
      el('div', { class: 'dossier-label', text: label }),
      node);
  }

  function paintDossier() {
    clear(dossier);
    const question = questions.find((q) => q.id === selectedId);
    if (!question) {
      dossier.append(emptyState('请选择一道题', '左侧选中后，这里显示题干、选项、参考答案与解析。'));
      return;
    }

    const position = positions.find((p) => p.id === question.position_id);
    const isChoice = question.question_type === 'single_choice';
    const answer = question.reference_answer;

    // ⚠️ 必须用 dom.js 的 append，**不是**原生 `dossier.append`：
    // 下面几个分区是条件渲染的，为假时传的是 null；原生 append 会把它
    // 转成字面量文本 "null" 塞进页面（短答题上肉眼可见）。
    append(dossier, [
      el('div', { class: 'dossier-head' },
        el('div', {},
          el('h2', { class: 'dossier-question', text: question.content }),
          el('div', { class: 'meta-row' },
            sourceTag(question.source),
            el('span', { class: 'tag tag--dim', text: TYPE_LABELS[question.question_type] ?? question.question_type }),
            dimTag(question.dimension),
            el('span', { class: 'tag tag--dim', text: `难度 ${DIFFICULTY_LABELS[question.difficulty] ?? question.difficulty}` }),
            // 位置信息合并成一句：几个裸词并排时，「线上排查」到底是分类还是
            // 岗位名的一部分，读起来要猜
            el('span', { text: `${position?.name ?? '—'}／${question.category}` }),
          ),
        ),
        el('div', { class: 'dossier-actions' },
          el('button', {
            class: 'btn btn--ghost',
            text: 'AI 生成参考答案',
            onClick: () => generateAnswer(question),
          }),
          el('button', { class: 'btn btn--ghost', text: '编辑', onClick: () => openQuestionModal(positions, question, reload) }),
          el('button', { class: 'btn btn--ghost', text: '删除', onClick: () => removeQuestion(question) }),
        ),
      ),

      isChoice && question.options.length
        ? section('选项', el('ol', { class: 'option-list' },
            question.options.map((text, index) =>
              el('li', { class: `option-item${text === answer ? ' is-correct' : ''}` },
                el('span', { class: 'option-key', text: letter(index) }),
                el('span', { text }),
                text === answer ? el('span', { class: 'option-flag', text: '参考答案' }) : null,
              ),
            ),
          ))
        : null,

      answer
        ? section('参考答案', el('p', { class: 'dossier-text', text: answer }))
        : section('参考答案', el('p', { class: 'hint' }, isChoice
            ? '这道单选题还没有参考答案。'
            : '还没有参考答案。可以用上面的「AI 生成参考答案」起草，再手工修改。')),

      question.explanation ? section('解析', el('p', { class: 'dossier-text', text: question.explanation })) : null,

      question.tags.length
        ? section('标签', el('div', { class: 'tag-row' }, question.tags.map((tag) => dimTag(tag))))
        : null,
    ]);
  }

  async function generateAnswer(question) {
    if (question.reference_answer) {
      const ok = await confirmModal({
        title: '重新生成参考答案？',
        message: '生成会覆盖这道题现有的参考答案与解析，且不可撤销。',
        confirmLabel: '重新生成',
        danger: false,
      });
      if (!ok) return;
    }
    try {
      const updated = await api.post(`/questions/${question.id}/reference-answer`);
      Object.assign(question, updated);
      paintDossier();
      toast.success('参考答案已更新');
    } catch (error) {
      toast.error(error.message);
    }
  }

  function paint() {
    countNode.textContent = `${questions.length} 道题`;
    const hasAny = questions.length > 0;
    split.hidden = !hasAny;
    emptyPanel.hidden = hasAny;
    if (!hasAny) {
      clear(emptyPanel);
      emptyPanel.append(
        emptyState('没有匹配的题目', '换个筛选条件，或者新建一道。',
          el('button', { class: 'btn btn--primary', text: '创建题目', onClick: create })),
      );
      return;
    }
    paintList();
    paintDossier();
  }

  /* ---------------------------- 筛选栏 ---------------------------- */

  function selectFilter(node, key) {
    node.addEventListener('change', (event) => { filters[key] = event.target.value; reload(); });
    return node;
  }

  function textFilter(key, placeholder, grow) {
    return el('input', {
      class: `input${grow ? ' filterbar-grow' : ''}`,
      placeholder,
      'aria-label': placeholder,
      onInput: (event) => { filters[key] = event.target.value.trim(); reload(); },
    });
  }

  // 维度与分类都是**精确匹配**（后端 == 比较），所以给下拉而不是自由输入 ——
  // 自由输入要求用户一字不差地敲对，否则筛出来是空的却看不出为什么。
  const dimensionOptions = [['', '全部维度']];
  const seenDimensions = new Set();
  for (const position of positions) {
    for (const dimension of position.evaluation_dimensions) {
      if (!seenDimensions.has(dimension)) { seenDimensions.add(dimension); dimensionOptions.push([dimension, dimension]); }
    }
  }

  const categorySelect = selectFilter(
    el('select', { class: 'select', 'aria-label': '按分类筛选' },
      el('option', { value: '', text: '全部分类' })),
    'category',
  );
  // 分类是自由文本，唯一可用的取值来源就是已加载的题目。因此**每次拉取后都要重算** ——
  // 只在渲染开始时算一次的话，那时 questions 还是空的，这个下拉永远只有「全部分类」一项。
  // 当前选中的分类必须保留，否则重算会让下拉悄悄跳回「全部」。
  let categorySignature = '';
  function syncCategoryOptions() {
    const values = [];
    for (const question of questions) {
      if (!values.includes(question.category)) values.push(question.category);
    }
    if (filters.category && !values.includes(filters.category)) values.push(filters.category);

    const signature = values.join('\u0000');
    if (signature === categorySignature) return;
    categorySignature = signature;

    clear(categorySelect);
    categorySelect.append(el('option', { value: '', text: '全部分类' }));
    for (const value of values) categorySelect.append(el('option', { value, text: value }));
    categorySelect.value = filters.category;
  }

  const filterbar = el('div', { class: 'filterbar' },
    selectFilter(
      el('select', { class: 'select', 'aria-label': '按岗位筛选' },
        el('option', { value: '', text: '全部岗位' }),
        positions.map((p) => el('option', { value: String(p.id), text: p.name }))),
      'position_id'),
    selectFilter(
      el('select', { class: 'select', 'aria-label': '按题型筛选' },
        el('option', { value: '', text: '全部题型' }),
        el('option', { value: 'single_choice', text: TYPE_LABELS.single_choice }),
        el('option', { value: 'short_answer', text: TYPE_LABELS.short_answer })),
      'question_type'),
    selectFilter(
      el('select', { class: 'select', 'aria-label': '按维度筛选' },
        dimensionOptions.map(([value, text]) => el('option', { value, text }))),
      'dimension'),
    categorySelect,
    selectFilter(
      el('select', { class: 'select', 'aria-label': '按来源筛选' },
        el('option', { value: '', text: '全部来源' }),
        el('option', { value: 'bank', text: '手工' }),
        el('option', { value: 'ai', text: 'AI' })),
      'source'),
    textFilter('keyword', '搜索题干', true),
    countNode,
  );

  mount(
    main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '题库' }),
        el('p', { class: 'page-lede' }, '手工维护的题会优先被抽中；AI 在面试创建时补充的题也会收录到这里。'),
      ),
      el('div', { class: 'page-head-actions' },
        el('button', {
          class: 'btn btn--primary',
          text: '创建题目',
          // 题目必须挂在岗位上，没有岗位时创建必然被拒 —— 提前禁用并说明原因
          disabled: !positions.length,
          title: positions.length ? '' : '请先创建岗位',
          onClick: create,
        })),
    ),
    el('div', { class: 'panel' }, filterbar, bodyHost),
  );

  await reload();
}
