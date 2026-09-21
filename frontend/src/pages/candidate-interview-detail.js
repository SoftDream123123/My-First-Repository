/**
 * pages/candidate-interview-detail.js —— 在线答题
 *
 * 与刷题页刻意不同：那边**整卷铺开**（自己跟自己较劲，可以来回跳），
 * 这边**一题一题**（正式面试是有秩序的，且交卷是一次性动作）。
 * 左侧导航一眼列出「待答 / 已答」—— 交卷前最需要防的是漏答，
 * 核对漏答靠的正是这份清单，而不是把八道题摊在一屏里往上翻。
 *
 * 两条与后端对齐的硬约束（API 文档 §10.5 / §10.6）：
 *   1. 面试非 `ongoing` → 作答通道关闭；
 *   2. **已交卷 → 候选人自己再也不能改**（HR 侧不受影响，但那是另一回事）。
 * 两条都不靠「提交时才拦截」表达 —— 输入框直接只读，并说明为什么。
 */

import { el, clear, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  baseTitle, contextTitle, createShell, dimTag, emptyState, formatDateTime, loadingBlock,
} from '../components/shell.js';
import { navigate } from '../router.js';

const SAVE_LABELS = { idle: '', saving: '保存中…', saved: '已保存', failed: '保存失败' };
const filled = (question) => (question.my_answer ?? '').trim() !== '';
const savedValue = (question) => question.my_answer ?? '';

let activeTitle = null;
export function destroy() { if (activeTitle) document.title = activeTitle; }

export async function render(container, params) {
  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('在线作答'));
  mount(container, root);
  mount(main, loadingBlock('正在加载面试…'));

  let detail;
  try {
    detail = await api.get(`/candidate/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message,
      el('button', {
        class: 'btn btn--primary',
        text: '返回我的面试',
        onClick: () => navigate('/candidate/interviews'),
      }))));
    return;
  }

  const questions = detail.questions || [];
  let submitted = detail.submitted;
  let submittedAt = detail.submitted_at;
  let currentIndex = 0;
  const saveStates = {};

  const canAnswer = () => !submitted && detail.status === 'ongoing';

  activeTitle = baseTitle();
  document.title = `${detail.position_name} · 在线作答`;

  const lede = el('p', { class: 'page-lede' });
  const barHolder = el('div', {});
  const navColumn = el('div', {});
  const editorHolder = el('div', {});
  // 交卷前要 flush 当前输入框，因此持有这两个节点的引用，不去查 DOM
  let editorTextarea = null;
  let editorStateNode = null;
  // 交卷是异步的：flush 期间交卷条可能被重画（保存成功要刷新「已答 N / N」），
  // 因此不持有按钮引用，每次现查；防连点交给这个标志
  let submitting = false;

  if (!questions.length) {
    mount(main,
      el('div', { class: 'page-head' }, el('div', {}, el('h1', { text: detail.position_name }))),
      el('div', { class: 'panel' }, emptyState(
        '这场面试还没有题目',
        '招聘方可能还在准备题目，过一阵再来看看。',
        el('button', {
          class: 'btn btn--ghost',
          text: '返回我的面试',
          onClick: () => navigate('/candidate/interviews'),
        }))));
    return;
  }

  /* ------------------------------ 交卷条 ------------------------------ */

  function buildBar() {
    if (submitted) {
      return el('div', { class: 'submit-bar is-frozen' },
        el('span', { class: 'submit-bar-text', text: `已于 ${formatDateTime(submittedAt)} 交卷` }),
        detail.status === 'evaluated'
          ? el('button', {
              class: 'btn btn--primary',
              text: '查看反馈',
              onClick: () => navigate(`/candidate/interviews/${interviewId}/feedback`),
            })
          : el('span', { class: 'meta', text: '招聘方评估完成后，这里会出现反馈入口' }));
    }

    // 没有交卷、面试却被收口了：这页只剩「回看」一个用途，
    // 也就没有「还差多少 / 交卷」可讲 —— 不摆这条，免得和上面的说明说同一句话
    if (!canAnswer()) return null;

    const total = questions.length;
    const done = questions.filter(filled).length;
    const percent = total ? Math.round((done / total) * 100) : 0;
    const submit = el('button', { class: 'btn btn--primary', text: '交卷' });
    submit.addEventListener('click', () => askSubmit());

    return el('div', { class: 'submit-bar' },
      el('span', { class: 'submit-bar-text', text: `已答 ${done} / ${total}` }),
      el('div', { class: 'submit-bar-track' },
        el('div', { class: 'submit-bar-fill', style: `width:${percent}%` })),
      submit);
  }

  /** 交卷条上那颗按钮。每次现查 —— 保存成功会重画这条，旧引用会失效。 */
  const barButton = () => barHolder.querySelector('.btn');

  function paintBar() {
    clear(barHolder);
    const bar = buildBar();
    // 原生 append 会把 null 变成字符串 "null"，必须自己判一下（`dom.append` 才跳过空值）
    if (bar) barHolder.append(bar);
  }

  function paintNav() {
    clear(navColumn);
    navColumn.append(buildNav());
  }

  /* ------------------------------ 单题 ------------------------------ */

  function saveAnswer(question, textarea, stateNode) {
    saveStates[question.interview_question_id] = 'saving';
    stateNode.className = 'save-state is-saving';
    stateNode.textContent = SAVE_LABELS.saving;

    return api.post(`/candidate/interviews/${interviewId}/answers`, {
      interview_question_id: question.interview_question_id,
      content: textarea.value,
    })
      .then((saved) => {
        question.my_answer = saved.content;
        saveStates[question.interview_question_id] = 'saved';
        stateNode.className = 'save-state is-saved';
        stateNode.textContent = SAVE_LABELS.saved;
        // 交卷条的「已答 N / N」与导航的「已答 / 待答」都变了，两处都要重画。
        // **不重画编辑区** —— 那会把光标从输入框里踢出去
        paintBar();
        paintNav();
        return true;
      })
      .catch((error) => {
        saveStates[question.interview_question_id] = 'failed';
        stateNode.className = 'save-state is-failed';
        stateNode.textContent = SAVE_LABELS.failed;
        toast.error(error.message);
        return false;
      });
  }

  function buildEditor() {
    const question = questions[currentIndex];
    const state = saveStates[question.interview_question_id] || 'idle';
    editorStateNode = el('span', {
      class: `save-state${state === 'saved' ? ' is-saved' : ''}`,
      text: SAVE_LABELS[state],
    });

    const editable = canAnswer();
    editorTextarea = el('textarea', {
      class: 'textarea',
      id: 'candidate-answer',
      maxlength: '10000', // 与后端 content ≤ 10000 对齐
      placeholder: editable ? '写下你的回答。离开输入框会自动保存。' : '',
      readOnly: !editable,
      value: savedValue(question),
    });

    if (editable) {
      // 失焦保存即可 —— 不做输入防抖，避免高频请求（与 HR 详情页同一手法）
      editorTextarea.addEventListener('blur', () => {
        if (editorTextarea.value === savedValue(question)) return; // 没改就不发请求
        saveAnswer(question, editorTextarea, editorStateNode);
      });
    }

    return el('section', { class: 'editor' },
      el('div', { class: 'editor-head' },
        el('span', { class: 'editor-seq', text: String(question.seq) }),
        dimTag(question.dimension)),

      el('p', { class: 'editor-question', text: question.content }),

      el('div', { class: 'editor-answer-head' },
        el('label', { class: 'field-label', for: 'candidate-answer', text: '我的回答' }),
        el('span', { class: 'hint', text: editable ? '离开输入框时会自动保存' : '' })),
      editorTextarea,
      el('div', { class: 'editor-actions' },
        el('span', { style: 'margin-left:auto' }, editorStateNode)),

      el('div', { class: 'editor-pager' },
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '上一题',
          disabled: currentIndex === 0,
          onClick: () => { currentIndex -= 1; paint(); },
        }),
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '下一题',
          disabled: currentIndex === questions.length - 1,
          onClick: () => { currentIndex += 1; paint(); },
        })));
  }

  function buildNav() {
    return el('div', { class: 'qnav' },
      el('div', { class: 'qnav-head' },
        el('span', { text: '题目' }),
        el('span', {
          class: 'qnav-count',
          text: `${questions.filter(filled).length} / ${questions.length}`,
        })),
      el('ol', { class: 'qnav-list' }, questions.map((question, index) => {
        const done = filled(question);
        // 答不了的时候（已交卷 / 通道已关闭）剩下的那些题**不是「待答」**——
        // 「待答」意味着还能动手，那是句假话
        const mark = done ? '已答' : (canAnswer() ? '待答' : '未答');
        return el('li', {},
          el('button', {
            class: ['qnav-item',
              index === currentIndex ? 'is-current' : '',
              done ? 'is-answered' : ''].filter(Boolean).join(' '),
            type: 'button',
            'aria-current': index === currentIndex ? 'true' : null,
            title: question.content,
            onClick: () => { currentIndex = index; paint(); },
          },
            el('span', { class: 'qnav-num', text: String(question.seq) }),
            el('span', { class: 'qnav-dim', text: question.dimension }),
            el('span', { class: 'qnav-mark', text: mark }),
          ));
      })));
  }

  /**
   * 把当前输入框里还没保存的内容落下去。
   * 存不下就返回 false —— 调用方据此**中止交卷**：交卷后这段作答再也改不了，
   * 与其丢掉它，不如让当事人先看到「保存失败」。
   */
  async function flushCurrent() {
    const question = questions[currentIndex];
    if (!editorTextarea || editorTextarea.value === savedValue(question)) return true;
    return saveAnswer(question, editorTextarea, editorStateNode);
  }

  async function askSubmit() {
    if (submitting) return; // 防连点：flush 与确认弹窗都是异步的
    submitting = true;
    barButton().disabled = true;

    // 先落盘再问 —— 见 flushCurrent 的说明
    const flushed = await flushCurrent();
    if (!flushed) {
      submitting = false;
      barButton().disabled = false;
      return;
    }
    barButton().disabled = false;

    const blank = questions.length - questions.filter(filled).length;
    const ok = await confirmModal({
      title: '交卷？',
      message: blank
        ? `还有 ${blank} 题没有作答。交卷后你不能再修改作答，招聘方会按已提交的内容评估。`
        : '全部题目都已作答。交卷后不能再修改。',
      confirmLabel: '交卷',
      danger: false,
    });
    if (!ok) {
      submitting = false;
      return;
    }

    barButton().disabled = true;
    barButton().textContent = '交卷中…';
    try {
      const result = await api.post(`/candidate/interviews/${interviewId}/submit`, {});
      submitted = true;
      submittedAt = result.submitted_at;
      submitting = false;
      paint();
      toast.success(`已交卷，提交了 ${result.answered_count} 题作答`);
    } catch (error) {
      submitting = false;
      toast.error(error.message);
      barButton().disabled = false;
      barButton().textContent = '交卷';
    }
  }

  function paint() {
    lede.textContent = submitted
      ? '你已交卷，作答已锁定。下面是这场面试的题目与你提交的内容。'
      : canAnswer()
        ? '一题一题往下答，离开输入框会自动保存。'
        : '招聘方已结束这场面试，作答通道已关闭。下面是题目与你当时的作答。';
    paintBar();
    paintNav();
    clear(editorHolder);
    editorHolder.append(buildEditor());
  }

  mount(main,
    el('div', { class: 'page-head' }, el('div', {},
      el('h1', { text: detail.position_name }),
      lede)),
    barHolder,
    el('div', { class: 'detail-layout' }, navColumn, editorHolder));
  paint();
}
