/**
 * 面试详情（module-07 §5.3）—— 核心屏。
 *
 * 布局上做了一处明确的判断：不用"8 道题的长滚动列表"，而是
 * 「题目导航 + 单题编辑」。真实面试是一题一题走的，HR 需要随时知道
 * "问到第几题了"，而不是在长页面里滚动找位置。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  contextTitle,
  createShell,
  dimTag,
  emptyState,
  formatDateTime,
  loadingBlock,
  navigate,
  sourceTag,
  statusRail,
} from '../components/shell.js';

const SAVE_LABELS = {
  idle: '未修改',
  saving: '保存中…',
  saved: '已保存',
  failed: '保存失败',
};

export async function render(container, params) {
  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('面试'));
  mount(container, root);
  mount(main, loadingBlock('正在加载面试…'));

  let detail;
  try {
    detail = await api.get(`/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message)));
    return;
  }

  const editable = detail.status === 'ongoing';
  let currentIndex = pickInitialIndex(detail.questions);
  const saveStates = {};

  /* --------------------------- 操作按钮 --------------------------- */

  async function transition(path, successMessage) {
    try {
      await api.post(`/interviews/${interviewId}/${path}`);
      toast.success(successMessage);
      render(container, params);
    } catch (error) {
      toast.error(error.message);
    }
  }

  function buildActions() {
    const buttons = [];

    if (detail.status === 'ongoing') {
      buttons.push(
        el('button', {
          class: 'btn btn--primary',
          text: '标记完成',
          onClick: () => transition('complete', '已标记完成'),
        }),
      );
    }

    if (detail.status === 'completed') {
      buttons.push(
        el('button', {
          class: 'btn btn--ghost',
          text: '回退到进行中',
          onClick: () => transition('rollback', '已回退到进行中'),
        }),
        el('button', {
          class: 'btn btn--primary',
          text: '开始评估',
          onClick: () => startEvaluation(),
        }),
      );
    }

    if (detail.status === 'evaluating') {
      buttons.push(
        el('button', {
          class: 'btn btn--primary',
          text: '查看评估进度',
          onClick: () => navigate(`/interviews/${interviewId}/evaluation`),
        }),
      );
    }

    if (detail.status === 'evaluated') {
      buttons.push(
        el('button', {
          class: 'btn btn--ghost',
          text: '回退到进行中',
          onClick: () => transition('rollback', '已回退到进行中'),
        }),
        el('button', {
          class: 'btn btn--primary',
          text: '查看报告',
          onClick: () => navigate(`/interviews/${interviewId}/evaluation`),
        }),
        el('button', {
          class: 'btn btn--ghost',
          text: '重新评估',
          onClick: () => startEvaluation(),
        }),
      );
    }

    return buttons;
  }

  async function startEvaluation() {
    try {
      await api.post(`/interviews/${interviewId}/evaluate`);
      navigate(`/interviews/${interviewId}/evaluation`);
    } catch (error) {
      toast.error(error.message);
    }
  }

  /* ---------------------------- 题目导航 ---------------------------- */

  function buildNav() {
    const answered = detail.questions.filter((q) => q.answer).length;

    return el(
      'aside',
      { class: 'qnav', 'aria-label': '题目导航' },
      el(
        'div',
        { class: 'qnav-head' },
        el('span', { text: '题目' }),
        el('span', { class: 'qnav-count', text: `${answered} / ${detail.questions.length}` }),
      ),
      el(
        'ol',
        { class: 'qnav-list' },
        detail.questions.map((question, index) =>
          el(
            'li',
            {},
            el(
              'button',
              {
                class: [
                  'qnav-item',
                  index === currentIndex ? 'is-current' : '',
                  question.answer ? 'is-answered' : '',
                ]
                  .filter(Boolean)
                  .join(' '),
                onClick: () => {
                  currentIndex = index;
                  repaint();
                },
              },
              el('span', { class: 'qnav-num', text: String(question.seq) }),
              el('span', { class: 'qnav-dim', text: question.dimension }),
              el('span', {
                class: 'qnav-mark',
                text: question.answer ? '已答' : '待答',
              }),
            ),
          ),
        ),
      ),
    );
  }

  /* ---------------------------- 单题编辑 ---------------------------- */

  function saveAnswer(question, textarea, stateNode) {
    saveStates[question.interview_question_id] = 'saving';
    stateNode.className = 'save-state is-saving';
    stateNode.textContent = SAVE_LABELS.saving;

    api
      .post(`/interviews/${interviewId}/answers`, {
        interview_question_id: question.interview_question_id,
        content: textarea.value,
      })
      .then((updated) => {
        question.answer = updated.answer;
        question.recorded_at = updated.recorded_at;
        saveStates[question.interview_question_id] = 'saved';
        stateNode.className = 'save-state is-saved';
        stateNode.textContent = SAVE_LABELS.saved;
        repaintNavCount();
      })
      .catch((error) => {
        saveStates[question.interview_question_id] = 'failed';
        stateNode.className = 'save-state is-failed';
        stateNode.textContent = SAVE_LABELS.failed;
        toast.error(error.message);
      });
  }

  function repaintNavCount() {
    const answered = detail.questions.filter((q) => q.answer).length;
    const countNode = main.querySelector('.qnav-count');
    if (countNode) countNode.textContent = `${answered} / ${detail.questions.length}`;
    const currentNavItem = main.querySelectorAll('.qnav-item')[currentIndex];
    if (currentNavItem) {
      currentNavItem.classList.toggle('is-answered', Boolean(detail.questions[currentIndex].answer));
      const mark = currentNavItem.querySelector('.qnav-mark');
      if (mark) mark.textContent = detail.questions[currentIndex].answer ? '已答' : '待答';
    }
  }

  function buildEditor() {
    const question = detail.questions[currentIndex];
    const state = saveStates[question.interview_question_id] || 'idle';

    const stateNode = el('span', {
      class: `save-state${state === 'saved' ? ' is-saved' : ''}`,
      text: SAVE_LABELS[state],
    });

    const textarea = el('textarea', {
      class: 'textarea',
      id: 'answer-input',
      placeholder: editable ? '边听边记。留空表示候选人未作答，评估时按 0 分处理。' : '',
      readOnly: !editable,
      value: question.answer ?? '',
    });

    if (editable) {
      // 失焦保存即可 —— 不做输入防抖，避免高频请求
      textarea.addEventListener('blur', () => {
        if (textarea.value === (question.answer ?? '')) {
          return; // 没改就不发请求
        }
        saveAnswer(question, textarea, stateNode);
      });
    }

    const actions = editable
      ? el(
          'div',
          { class: 'editor-actions' },
          el('button', {
            class: 'btn btn--ghost',
            text: '保存回答',
            onClick: () => saveAnswer(question, textarea, stateNode),
          }),
          el('button', {
            class: 'btn btn--quiet',
            text: '清空',
            onClick: () => {
              textarea.value = '';
              saveAnswer(question, textarea, stateNode);
            },
          }),
          el('span', { class: 'hint', text: '离开输入框时会自动保存' }),
        )
      : el(
          'div',
          { class: 'editor-actions' },
          el('span', {
            class: 'hint',
            text: '需先回退到进行中才能修改回答',
          }),
        );

    return el(
      'section',
      { class: 'editor' },

      el(
        'div',
        { class: 'editor-head' },
        el('span', { class: 'editor-seq', text: String(question.seq).padStart(2, '0') }),
        dimTag(question.dimension),
        sourceTag(question.source),
      ),

      el('p', { class: 'editor-question', text: question.content }),

      el(
        'div',
        { class: 'editor-answer-label' },
        el('label', { class: 'field-label', for: 'answer-input', text: '候选人回答' }),
        stateNode,
      ),
      textarea,
      actions,

      el(
        'div',
        { class: 'editor-pager' },
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '上一题',
          disabled: currentIndex === 0,
          onClick: () => {
            currentIndex -= 1;
            repaint();
          },
        }),
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '下一题',
          disabled: currentIndex === detail.questions.length - 1,
          onClick: () => {
            currentIndex += 1;
            repaint();
          },
        }),
      ),
    );
  }

  /* ------------------------------- 组装 ------------------------------- */

  const navColumn = el('div', {});
  const editorColumn = el('div', {});

  function repaint() {
    clear(navColumn);
    clear(editorColumn);
    navColumn.append(buildNav());
    editorColumn.append(buildEditor());
  }

  mount(
    main,
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', { class: 'h-page', text: detail.candidate_name }),
        el('p', { class: 'page-lede', text: detail.position_name }),
        el('p', {
          class: 'meta',
          text: detail.completed_at
            ? `创建于 ${formatDateTime(detail.created_at)}，完成于 ${formatDateTime(detail.completed_at)}`
            : `创建于 ${formatDateTime(detail.created_at)}`,
        }),
      ),
      el('div', { class: 'page-head-actions' }, buildActions()),
    ),

    // 状态由状态轨表达，不再另加一个状态标签 —— 那会重复同样的信息
    statusRail(detail.status),

    el('div', { class: 'detail-layout' }, navColumn, editorColumn),
  );

  repaint();
}

/** 打开时定位到第一道未答的题 —— HR 关心的永远是"下一题是什么"。 */
function pickInitialIndex(questions) {
  const index = questions.findIndex((q) => !q.answer);
  return index === -1 ? 0 : index;
}
