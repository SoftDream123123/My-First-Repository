/**
 * pages/interview-prep.js —— 面试前准备助手
 *
 * PRD §4.11：一场面试一份，生成即整批落库，重新生成整体覆盖；
 * 与面试状态机正交（只有「完成」及之后才冻结）。
 * 提纲本身是一条时间轴，所以阶段按分钟刻度排；考察重点按维度；
 * 问题预案直接用**本场已经出了的题**，而不是另造一批通用问题 ——
 * HR 要的是「这场该怎么问」，不是一份放之四海皆准的题库。
 *
 * ⚠️ **字段名以后端 schema 为准**（`app/interview/schemas.py` 的
 * `PrepOutlineStageOut` / `PrepFocusPointOut` / `PrepQuestionItemOut`）：
 *
 * | 部分 | 真实字段 | 原型里写错的 |
 * |---|---|---|
 * | `outline[]` | `seq` · `phase` · **`duration_min`** · **`notes`（字符串）** | `minutes` · `points（数组）` |
 * | `focus_points[]` | `dimension` · **`point`** · `reason` | `focus` |
 * | `question_plan[]` | `question` · `intent` · **`follow_ups`** | `followups` |
 *
 * 原型那份是照着自造的 mock 写的，两边一起错所以自洽；照搬会**保存必然 400、
 * 读取全是空白**。另外 `seq` 是后端要求的字段（≥1），PUT 必须带上。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  baseTitle, contextTitle, createShell, dimTag, emptyState, formatDateTime, loadingBlock, panelHead,
} from '../components/shell.js';
import { navigate } from '../router.js';

const FROZEN_HINT = '面试已完成，准备提纲随之定稿；如需修改，请先回退到进行中。';

const STATUS_LABELS = {
  draft: '草稿', ongoing: '进行中', completed: '已完成', evaluating: '评估中', evaluated: '已评估',
};

/** 把「每行一条」的文本域读成数组 —— 比让人维护一个嵌套列表现得多。 */
const linesOf = (value) => String(value ?? '').split('\n').map((line) => line.trim()).filter(Boolean);

/**
 * 累计分钟刻度：提纲的价值有一半在「这段该花多久」。
 * 起点是 0，所以第一段的区间形如 `0–5`。
 */
function cumulativeRanges(stages) {
  let cursor = 0;
  return stages.map((stage) => {
    const minutes = Number(stage.duration_min) || 0;
    const label = `${cursor}–${cursor + minutes}`;
    cursor += minutes;
    return label;
  });
}

/** 按 seq 排 —— `seq` 就是用来定义顺序的，别去假设数组恰好有序。 */
const bySeq = (a, b) => (a.seq ?? 0) - (b.seq ?? 0);

/* ------------------------------ 只读视图 ------------------------------ */

function outlinePanel(prep) {
  const stages = [...(prep.outline ?? [])].sort(bySeq);
  const ranges = cumulativeRanges(stages);
  const total = stages.reduce((sum, stage) => sum + (Number(stage.duration_min) || 0), 0);
  return el('div', { class: 'panel' },
    panelHead('面试提纲', stages.length ? `共约 ${total} 分钟` : null),
    stages.length
      ? el('div', {}, stages.map((stage, index) => el('div', { class: 'prep-stage' },
          el('span', { class: 'prep-time', text: `${ranges[index]} 分` }),
          el('div', {},
            el('p', { class: 'prep-phase', text: stage.phase }),
            stage.notes
              ? el('p', { class: 'prep-focus-text', text: stage.notes })
              : null))))
      : el('div', { class: 'panel-body' }, el('p', { class: 'hint', text: '还没有安排阶段。' })));
}

function focusPanel(prep) {
  const items = prep.focus_points ?? [];
  return el('div', { class: 'panel' },
    panelHead('考察重点', '按岗位的评估维度'),
    items.length
      ? el('div', {}, items.map((item) => el('div', { class: 'prep-focus' },
          // 维度是这一项的题眼，做成标签；正文不再重复一遍维度名
          dimTag(item.dimension),
          el('p', { class: 'prep-focus-text', text: item.point }),
          item.reason ? el('p', { class: 'prep-focus-why', text: item.reason }) : null)))
      : el('div', { class: 'panel-body' }, el('p', { class: 'hint', text: '还没有列出考察重点。' })));
}

function planPanel(prep) {
  const items = prep.question_plan ?? [];
  return el('div', { class: 'panel' },
    panelHead('问题预案', '来自本场已出的题目'),
    items.length
      ? el('div', {}, items.map((item, index) => el('div', { class: 'prep-question' },
          el('div', { class: 'prep-question-head' },
            el('span', { class: 'score-seq', text: String(index + 1) }),
            el('p', { class: 'prep-question-text', text: item.question })),
          el('div', { class: 'prep-question-body' },
            el('div', { class: 'prep-field' },
              el('div', { class: 'dossier-label', text: '考察意图' }),
              el('p', { class: 'score-comment', text: item.intent })),
            (item.follow_ups ?? []).length
              ? el('div', { class: 'prep-field' },
                  el('div', { class: 'dossier-label', text: '可追问' }),
                  el('ul', { class: 'prep-points' }, item.follow_ups.map((text) => el('li', { text }))))
              : null))))
      : el('div', { class: 'panel-body' }, el('p', { class: 'hint', text: '还没有准备问题。' })));
}

/* ------------------------------ 编辑视图 ------------------------------ */
/* 三个部分整体覆盖（后端也是整体替换，不做字段级合并），因此编辑态就是把三块
   内容换成可增删的表单，保存时一次性提交。
   每一块自带一个报错位 —— 后端 schema 里 phase / point / question 都是
   `min_length=1`、`duration_min` 是 `ge=1`，空行提交必然 400；提前指出是哪一条。 */

function removeButton(onClick) {
  return el('button', {
    class: 'btn btn--quiet dim-editor-remove', type: 'button', text: '×', title: '删除这一条', onClick,
  });
}

function blockError() { return el('p', { class: 'field-error', hidden: true }); }

/**
 * 给每条草稿套一个「可增删的块 + 自己的报错位」。
 *
 * `renderBody(draft, index, redraw)` 的第三个参数是重画整列的回调 ——
 * 删除某一条之后下标会变，必须整列重画；把它传进去比让每个编辑器
 * 自己去够 `renderRows` 干净。
 */
function buildEditor({ drafts, renderBody, onAdd, addLabel, validate }) {
  const rows = el('div', {});
  const errors = [];

  function redraw() {
    clear(rows);
    errors.length = 0;
    drafts.forEach((draft, index) => {
      const errorNode = blockError();
      errors.push(errorNode);
      rows.append(el('div', { class: 'prep-edit-block' },
        renderBody(draft, index, redraw),
        errorNode));
    });
  }
  redraw();

  return {
    node: el('div', {},
      rows,
      el('div', { class: 'prep-edit-add' },
        el('button', {
          class: 'btn btn--ghost btn--sm', type: 'button', text: addLabel,
          onClick: () => { onAdd(); redraw(); },
        }))),
    /** 校验通过返回草稿数组，否则把每条的问题显示在自己的块下并返回 null。 */
    read() {
      let ok = true;
      drafts.forEach((draft, index) => {
        const message = validate(draft);
        const node = errors[index];
        if (!node) return;
        if (message) { node.textContent = message; node.hidden = false; ok = false; }
        else { node.textContent = ''; node.hidden = true; }
      });
      return ok ? drafts : null;
    },
  };
}

function outlineEditor(prep) {
  const drafts = [...(prep.outline ?? [])].sort(bySeq).map((stage) => ({
    phase: stage.phase ?? '',
    duration_min: stage.duration_min ?? 5,
    notes: stage.notes ?? '',
  }));

  return buildEditor({
    drafts,
    addLabel: '添加阶段',
    onAdd: () => drafts.push({ phase: '新阶段', duration_min: 5, notes: '' }),
    validate: (draft) => {
      if (!String(draft.phase).trim()) return '阶段名称不能为空';
      if (!Number.isFinite(Number(draft.duration_min)) || Number(draft.duration_min) < 1) return '分钟数至少为 1';
      return null;
    },
    renderBody: (draft, index, redraw) => el('div', {},
      el('div', { class: 'prep-edit-head' },
        el('span', { class: 'prep-edit-tag', text: '阶段' }),
        el('input', {
          class: 'input', value: draft.phase, placeholder: '阶段名称',
          onInput: (event) => { draft.phase = event.target.value; },
        }),
        el('span', { class: 'prep-edit-tag', text: '分钟' }),
        el('input', {
          class: 'input mins', type: 'number', min: '1', max: '600', value: String(draft.duration_min),
          onInput: (event) => { draft.duration_min = Number(event.target.value); },
        }),
        removeButton(() => { drafts.splice(index, 1); redraw(); })),
      el('div', { class: 'field', style: 'margin:var(--s3) 0 0' },
        el('p', { class: 'prep-edit-label', text: '这一段要做什么' }),
        el('textarea', {
          class: 'textarea', rows: '3', value: draft.notes, maxlength: '2000',
          placeholder: '例如：请候选人用三分钟讲清最近一段工作的主要职责',
          onInput: (event) => { draft.notes = event.target.value; },
        }))),
  });
}

function focusEditor(prep, dims) {
  const drafts = (prep.focus_points ?? []).map((item) => ({
    dimension: item.dimension ?? dims[0] ?? '',
    point: item.point ?? '',
    reason: item.reason ?? '',
  }));

  return buildEditor({
    drafts,
    addLabel: '添加一项',
    onAdd: () => drafts.push({ dimension: dims[0] ?? '', point: '', reason: '' }),
    validate: (draft) => {
      if (!String(draft.dimension).trim()) return '请选择维度';
      if (!String(draft.point).trim()) return '「重点验证什么」不能为空';
      return null;
    },
    renderBody: (draft, index, redraw) => el('div', {},
      el('div', { class: 'prep-edit-head' },
        el('span', { class: 'prep-edit-tag', text: '维度' }),
        el('select', { class: 'select', onChange: (event) => { draft.dimension = event.target.value; } },
          // 维度集合由岗位给出；不在集合里的历史值也要留一个选项，否则一保存就被改掉
          [...new Set([...dims, draft.dimension].filter(Boolean))].map((dim) =>
            el('option', { value: dim, text: dim, selected: dim === draft.dimension }))),
        removeButton(() => { drafts.splice(index, 1); redraw(); })),
      el('div', { class: 'field', style: 'margin:var(--s3) 0 0' },
        el('p', { class: 'prep-edit-label', text: '重点验证什么' }),
        el('textarea', {
          class: 'textarea', rows: '2', value: draft.point, maxlength: '2000',
          placeholder: '例如：把本场题目追问到具体做法与结果，而不是停在概念上',
          onInput: (event) => { draft.point = event.target.value; },
        })),
      el('div', { class: 'field', style: 'margin:var(--s2) 0 0' },
        el('p', { class: 'prep-edit-label', text: '为什么是这一项（可不填）' }),
        el('textarea', {
          class: 'textarea', rows: '2', value: draft.reason, maxlength: '2000',
          placeholder: '例如：简历里有可交叉核实的经历，需确认表述与事实一致',
          onInput: (event) => { draft.reason = event.target.value; },
        }))),
  });
}

function planEditor(prep) {
  const drafts = (prep.question_plan ?? []).map((item) => ({
    question: item.question ?? '',
    intent: item.intent ?? '',
    follow_ups: (item.follow_ups ?? []).join('\n'),
  }));

  return buildEditor({
    drafts,
    addLabel: '添加问题',
    onAdd: () => drafts.push({ question: '', intent: '', follow_ups: '' }),
    validate: (draft) => (String(draft.question).trim() ? null : '问题不能为空'),
    renderBody: (draft, index, redraw) => el('div', {},
      el('div', { class: 'prep-edit-head' },
        el('span', { class: 'prep-edit-tag', text: '问题' }),
        el('input', {
          class: 'input', value: draft.question, placeholder: '准备问的问题', maxlength: '2000',
          onInput: (event) => { draft.question = event.target.value; },
        }),
        removeButton(() => { drafts.splice(index, 1); redraw(); })),
      el('div', { class: 'field', style: 'margin:var(--s3) 0 0' },
        el('p', { class: 'prep-edit-label', text: '考察意图' }),
        el('textarea', {
          class: 'textarea', rows: '2', value: draft.intent, maxlength: '2000',
          placeholder: '例如：看他能不能讲清自己实际做了什么，而不是给出一个通用答案',
          onInput: (event) => { draft.intent = event.target.value; },
        })),
      el('div', { class: 'field', style: 'margin:var(--s2) 0 0' },
        el('p', { class: 'prep-edit-label', text: '可追问 · 每行一条' }),
        el('textarea', {
          class: 'textarea', rows: '2', value: draft.follow_ups, maxlength: '2000',
          placeholder: '例如：当时有没有别的方案？你为什么没选那个？',
          onInput: (event) => { draft.follow_ups = event.target.value; },
        }))),
  });
}

/* -------------------------------- 页面 -------------------------------- */

/** 离开页面时把标签页标题还原（打印 PDF 用的就是它）。 */
export function destroy() { document.title = baseTitle(); }

export async function render(container, params) {
  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('面试', '面试准备'));
  // 提纲是一份要读的东西：把正文收在 1000px 内，别让它横跨 1240px
  main.classList.add('prep-page');
  mount(container, root);
  mount(main, loadingBlock('正在加载…'));

  let detail;
  let prep = null;
  let prepFailed = null;
  try {
    detail = await api.get(`/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '返回列表', onClick: () => navigate('/interviews') }))));
    return;
  }
  try {
    prep = await api.get(`/interviews/${interviewId}/prep`);
  } catch (error) {
    prepFailed = error; // 404 = 还没生成，不是故障；其余才是
  }

  document.title = `${detail.candidate_name} · 面试准备`;

  const dims = detail.evaluation_dimensions || [];
  // 准备助手与面试状态机正交，但「完成」及之后冻结（后端 409）
  const editable = detail.status === 'draft' || detail.status === 'ongoing';
  const missing = prepFailed && prepFailed.status === 404;
  let editing = false;

  async function generate(button) {
    if (prep) {
      const ok = await confirmModal({
        title: '重新生成准备提纲？',
        message: '新的提纲会整体覆盖当前这一份，包括你手工改过的内容。这一步无法撤销。',
        confirmLabel: '重新生成',
        danger: false,
      });
      if (!ok) return;
    }
    button.disabled = true;
    button.textContent = '正在生成…';
    try {
      // 准备助手的产出是整批一次给全的，不做流式（PRD §4.11）
      await api.post(`/interviews/${interviewId}/prep`);
      render(container, params);
    } catch (error) {
      // AI 失败（502）时后端不动旧内容 —— 页面上原来那份还在
      toast.error(error.message);
      button.disabled = false;
      button.textContent = prep ? '重新生成' : '生成准备提纲';
    }
  }

  /* ---- 只读态 ---- */
  function renderView() {
    // 还没生成时，「生成」这个动作只留在空态面板里 —— 同一个动作不摆两处
    const actions = [];
    if (prep) {
      actions.push(
        el('button', {
          class: 'btn btn--quiet',
          text: '重新生成',
          disabled: !editable,
          title: editable ? '' : FROZEN_HINT,
          onClick: (event) => generate(event.currentTarget),
        }),
        el('button', {
          class: 'btn btn--ghost', text: '编辑',
          disabled: !editable,
          title: editable ? '' : FROZEN_HINT,
          onClick: () => { editing = true; renderEditor(); },
        }),
        el('button', {
          class: 'btn btn--primary', text: '导出 PDF',
          title: '走浏览器打印。候选人脱敏反馈不提供导出，准备提纲与报告才提供。',
          onClick: () => window.print(),
        }),
      );
    }

    mount(main,
      el('div', { class: 'page-head' },
        el('div', {},
          el('h1', { text: detail.candidate_name }),
          el('p', { class: 'page-lede' },
            detail.candidate_contact
              ? `${detail.position_name} · ${detail.candidate_contact}`
              : detail.position_name),
          el('p', { class: 'meta' }, prep
            ? `生成于 ${formatDateTime(prep.generated_at)}${prep.edited_at ? `，最后编辑 ${formatDateTime(prep.edited_at)}` : ''}`
            : '尚未生成')),
        el('div', { class: 'page-head-actions' },
          el('button', { class: 'btn btn--ghost', text: '返回详情', onClick: () => navigate(`/interviews/${interviewId}`) }),
          actions)),

      // 准备助手与面试状态机正交，因此这里用一句话交代能不能改，而不是画状态轨
      el('div', { class: 'prep-note' },
        el('span', { text: editable
          ? '准备提纲是面试前的工作稿，不影响面试本身的进度。'
          : FROZEN_HINT }),
        el('span', { text: `面试当前：${STATUS_LABELS[detail.status] ?? detail.status}` })),

      prep
        ? el('div', { style: 'margin-top:var(--s5)' }, outlinePanel(prep), focusPanel(prep), planPanel(prep))
        : el('div', { style: 'margin-top:var(--s5)' },
            el('div', { class: 'panel' },
              panelHead('尚未生成'),
              el('div', { class: 'panel-body' },
                prepFailed && !missing
                  ? el('p', { class: 'field-error', text: prepFailed.message })
                  : el('div', {},
                      el('p', { class: 'prose', text: '开始前先生成一份准备提纲：按时间排好的面试流程、需要重点验证的能力项，以及每个问题该往哪个方向追问。' }),
                      el('p', { class: 'prose', style: 'margin-top:var(--s3)', text: editable
                        ? `AI 会读岗位的 JD 与评估维度、本场已有的题目${detail.resume_id != null ? '，以及候选人关联的简历' : ''}来生成这份提纲。`
                        : FROZEN_HINT }),
                      editable
                        ? el('div', { class: 'editor-actions' },
                            el('button', {
                              class: 'btn btn--primary', text: '生成准备提纲',
                              onClick: (event) => generate(event.currentTarget),
                            }))
                        : null)))));
  }

  /* ---- 编辑态：整页换成表单，保存时把三块一起交上去 ---- */
  function renderEditor() {
    if (!prep) return;
    const outline = outlineEditor(prep);
    const focus = focusEditor(prep, dims);
    const plan = planEditor(prep);

    const save = el('button', { class: 'btn btn--primary', text: '保存' });
    save.addEventListener('click', async () => {
      const outlineDrafts = outline.read();
      const focusDrafts = focus.read();
      const planDrafts = plan.read();
      if (!outlineDrafts || !focusDrafts || !planDrafts) {
        toast.error('有几处还没填完，已在对应位置标出');
        return;
      }

      save.disabled = true;
      save.textContent = '保存中…';
      try {
        await api.put(`/interviews/${interviewId}/prep`, {
          // seq 是后端要求字段（≥1），按当前顺序重编 —— 删掉中间一条之后不能留空洞
          outline: outlineDrafts.map((draft, index) => ({
            seq: index + 1,
            phase: String(draft.phase).trim(),
            duration_min: Number(draft.duration_min),
            notes: String(draft.notes ?? ''),
          })),
          focus_points: focusDrafts.map((draft) => ({
            dimension: draft.dimension,
            point: String(draft.point).trim(),
            reason: String(draft.reason ?? ''),
          })),
          question_plan: planDrafts.map((draft) => ({
            question: String(draft.question).trim(),
            intent: String(draft.intent ?? ''),
            follow_ups: linesOf(draft.follow_ups),
          })),
        });
        toast.success('准备提纲已保存');
        render(container, params);
      } catch (error) {
        toast.error(error.message);
        save.disabled = false;
        save.textContent = '保存';
      }
    });

    mount(main,
      el('div', { class: 'page-head' },
        el('div', {},
          el('h1', { text: detail.candidate_name }),
          el('p', { class: 'page-lede', text: '编辑准备提纲' }),
          el('p', { class: 'meta', text: '三个部分会一起提交，保存后立即覆盖原来的内容。' })),
        el('div', { class: 'page-head-actions' },
          el('button', {
            class: 'btn btn--ghost', text: '取消',
            onClick: () => { editing = false; render(container, params); },
          }),
          save)),
      el('div', { class: 'panel', style: 'margin-top:var(--s5)' },
        panelHead('面试提纲', '分钟数与要点'),
        el('div', { class: 'panel-body' }, outline.node)),
      el('div', { class: 'panel' },
        panelHead('考察重点', '按岗位的评估维度'),
        el('div', { class: 'panel-body' }, focus.node)),
      el('div', { class: 'panel' },
        panelHead('问题预案', '来自本场已出的题目'),
        el('div', { class: 'panel-body' }, plan.node)));
  }

  renderView();
}
