/**
 * pages/candidate-practice-session.js —— 练习作答（整卷铺开、逐题提交、就地判分）
 *
 * 与在线作答页刻意不同：那边是「题目导航 + 单题编辑」（正式面试一题一题走），
 * 这边**整卷铺开** —— 刷题是自己跟自己较劲，可以来回跳、可以先挑没做的那几题。
 *
 * 一处必须小心的实现细节：提交成功后**只重画被提交的那一道**。整卷重画会把
 * 其他题里已经写好、还没提交的作答一起清掉。
 *
 * ⚠️ **`is_correct` 是三态**（`true` / `false` / `null`），`null` 是「未判分」而不是
 * 「答错」—— 它不进错题本、不进正确率的分母，界面上也不能用错误的红色（API 文档 §13.20）。
 *
 * ⚠️ **参考答案按题型二选一**：提交作答与重新判分的响应里，单选把答案放在
 * `correct_answer`、简答放在 `reference_answer`（API 文档 §13.22）。原型只读
 * `reference_answer`，于是**单选题的复盘永远标不出正确答案** —— 这里按契约取
 * 「非空的那个」。注意「练习详情」里的字段名不同（`PracticeItemOut.reference_answer`
 * 单选简答都有），两条路径都要走同一套归一化。
 */

import { el, clear, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  PRACTICE_DIFFICULTY_LABELS, PRACTICE_TYPE_LABELS, baseTitle, choiceRecap, contextTitle,
  createShell, dimTag, emptyState, formatDateTime, loadingBlock, panelHead, percent,
  referenceAnswerOf,
} from '../components/shell.js';
import { navigate } from '../router.js';

function filterSummary(session) {
  const parts = [];
  if (session.category) parts.push(session.category);
  if (session.dimension) parts.push(session.dimension);
  if (session.difficulty) parts.push(PRACTICE_DIFFICULTY_LABELS[session.difficulty] ?? session.difficulty);
  if (session.question_type) parts.push(PRACTICE_TYPE_LABELS[session.question_type] ?? session.question_type);
  return parts.length ? parts.join(' · ') : '全部题目';
}

/** 把两条响应路径（提交作答 / 重新判分）的判分结果并回本地那一条 item 上。 */
function normalizeAnswer(item, result) {
  item.user_answer = result.user_answer ?? item.user_answer;
  item.is_correct = result.is_correct;
  item.score = result.score ?? null;
  item.explanation = result.explanation ?? null;
  // 单选给 `correct_answer`、简答给 `reference_answer`，取「非空的那个」
  const answer = referenceAnswerOf(result);
  if (answer != null) item.reference_answer = answer;
}

/** 判分三态：答对 / 答错 / **未判分**。未判分不是答错，颜色与文案都不能混。 */
function verdictBlock(item) {
  const graded = item.is_correct !== null;
  const cls = !graded ? '' : item.is_correct ? 'is-correct' : 'is-wrong';
  const label = !graded ? '未判分' : item.is_correct ? '答对' : '答错';
  return el('div', { class: `verdict ${cls}`.trim() },
    el('div', { class: 'verdict-head' },
      el('span', { class: 'verdict-label', text: label }),
      typeof item.score === 'number'
        ? el('span', { class: 'verdict-score', text: `${item.score} / 10` })
        : null),
    item.explanation ? el('p', { class: 'verdict-note', text: item.explanation }) : null);
}

const choiceRecapOf = (item) => choiceRecap(item.question.options, item.reference_answer, item.user_answer);

function writtenRecap(item) {
  return el('div', {},
    el('div', { class: 'practice-answer' },
      el('div', { class: 'dossier-label', text: '我的作答' }),
      el('p', { class: 'answer-quote', text: item.user_answer ?? '（空）' })),
    item.reference_answer
      ? el('div', { class: 'practice-answer' },
          el('div', { class: 'dossier-label', text: '参考答案' }),
          el('p', { class: 'answer-quote', text: item.reference_answer }))
      : null);
}

/* --------------------------- 作答控件（未提交） --------------------------- */

const LETTERS = 'ABCDEFGHIJ';

function answerControl(item, onSubmit) {
  const single = item.question.question_type === 'single_choice';

  if (!single) {
    const textarea = el('textarea', {
      class: 'textarea', maxlength: '10000',
      placeholder: '写下你的回答。提交后会给出得分、参考答案与解析。',
    });
    const submit = el('button', { class: 'btn btn--primary btn--sm', text: '提交' });
    submit.addEventListener('click', () => {
      if (!textarea.value.trim()) { toast.error('请先写下回答'); textarea.focus(); return; }
      onSubmit(textarea.value);
    });
    return el('div', { class: 'practice-answer' }, textarea,
      el('div', { class: 'practice-actions' }, submit));
  }

  let picked = '';
  const submit = el('button', { class: 'btn btn--primary btn--sm', text: '提交', disabled: true });
  const list = el('div', {});
  (item.question.options || []).forEach((text, index) => {
    list.append(el('label', { class: 'choice-option' },
      el('input', { type: 'radio', name: `practice-${item.item_id}`, value: text }),
      el('span', { class: 'option-key', text: LETTERS[index] ?? '' }),
      el('span', { text })));
  });
  list.addEventListener('change', (event) => {
    picked = event.target.value;
    submit.disabled = false;
    for (const node of list.querySelectorAll('.choice-option')) {
      node.classList.toggle('is-picked', node.contains(event.target));
    }
  });
  submit.addEventListener('click', () => { if (picked) onSubmit(picked); });

  return el('div', { class: 'practice-answer' }, list,
    el('div', { class: 'practice-actions' }, submit));
}

/* -------------------------------- 页面 -------------------------------- */

let activeTitle = null;
export function destroy() { if (activeTitle) document.title = activeTitle; }

export async function render(container, params) {
  const sessionId = params.id;
  const { root, main } = createShell(contextTitle('刷题', '练习'));
  mount(container, root);
  mount(main, loadingBlock('正在加载练习…'));

  let detail;
  let positionName = null;
  try {
    detail = await api.get(`/practice/sessions/${sessionId}`);
    // `PracticeSessionOut` 里只有 `position_id`（后端 schema 就是这样，没有岗位名），
    // 因此岗位名要向候选人侧的岗位接口换一次 —— 那是他有权访问的那一个
    if (detail.session.position_id != null) {
      const positions = await api.get('/candidate/positions');
      positionName = positions.find((p) => p.id === detail.session.position_id)?.name ?? null;
    }
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('练习加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '返回刷题', onClick: () => navigate('/candidate/practice') }))));
    return;
  }

  const session = detail.session;
  const items = detail.items || [];
  const title = positionName ?? '练习';
  // 本地结束后要立刻锁住作答，因此这是变量不是常量
  let finished = session.status !== 'ongoing';
  let summary = null;
  let finishedLocally = false;

  activeTitle = baseTitle();
  document.title = `${title} · 刷题`;

  const progressHolder = el('div', { class: 'practice-progress' });
  const summaryHolder = el('div', {});
  const listHolder = el('div', { class: 'panel' });
  const actionsHolder = el('div', { class: 'page-head-actions' });

  function counters() {
    const answered = items.filter((i) => i.user_answer != null);
    const scored = answered.filter((i) => i.is_correct !== null);
    return {
      answered: answered.length,
      scored: scored.length,
      correct: scored.filter((i) => i.is_correct).length,
      total: items.length,
    };
  }

  function paintProgress() {
    const c = counters();
    const percentWidth = c.total ? Math.round((c.answered / c.total) * 100) : 0;
    clear(progressHolder);
    progressHolder.append(
      el('span', { class: 'practice-progress-text', text: `已答 ${c.answered} / ${c.total}` }),
      el('div', { class: 'practice-progress-track' },
        el('div', { class: 'practice-progress-fill', style: `width:${percentWidth}%` })),
      el('span', { class: 'practice-progress-text', text: `答对 ${c.correct}` }),
    );
  }

  /** 提交一道题。成功后**只重画这一道**，别把别的题里写了一半的作答清掉。 */
  async function submitItem(item, holder, userAnswer) {
    try {
      const result = await api.post(`/practice/sessions/${sessionId}/items`, {
        item_id: item.item_id,
        user_answer: userAnswer,
      });
      normalizeAnswer(item, result);
      paintItem(holder, item);
      paintProgress();
    } catch (error) {
      toast.error(error.message);
    }
  }

  async function rescore(item, holder) {
    try {
      const result = await api.post(`/practice/items/${item.item_id}/rescore`, {});
      normalizeAnswer(item, result);
      paintItem(holder, item);
      paintProgress();
    } catch (error) {
      toast.error(error.message);
    }
  }

  function paintItem(holder, item) {
    clear(holder);
    const answered = item.user_answer != null;
    holder.append(
      el('div', { class: 'practice-item-head' },
        el('span', { class: 'score-seq', text: String(item.seq) }),
        dimTag(item.question.dimension),
        // 题型用中性灰标签，与维度标签区分开
        el('span', { class: 'tag tag--off', text: PRACTICE_TYPE_LABELS[item.question.question_type] ?? '' })),
      el('p', { class: 'practice-item-question', text: item.question.content }),
    );

    if (!answered) {
      // 已结束的练习不再接受作答（后端同样拒绝），因此这里只呈现「未作答」
      holder.append(finished
        ? el('p', { class: 'hint', style: 'margin-top:var(--s4)', text: '未作答（本次练习已结束）' })
        : answerControl(item, (value) => submitItem(item, holder, value)));
      return;
    }

    holder.append(verdictBlock(item));
    holder.append(item.question.question_type === 'single_choice'
      // 选项列表也要收在同一条阅读宽度里，否则它会横到面板最右边
      ? el('div', { class: 'practice-answer' }, choiceRecapOf(item))
      : writtenRecap(item));

    // 未判分给一条重判的路（AI 不可用时后端就是这么标的，不是判错）
    if (item.is_correct === null && !finished) {
      holder.append(el('div', { class: 'practice-actions' },
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '重判',
          onClick: () => rescore(item, holder),
        })));
    }
  }

  function summaryBlock(data) {
    const cells = [
      [String(data.total), '题目'],
      [String(data.answered_count), '已作答'],
      [String(data.correct_count), '答对'],
      [percent(data.accuracy), '正确率'],
    ];
    return el('div', { class: 'panel' },
      panelHead('练习小结', finishedLocally ? '本次练习已结束' : null),
      el('div', { class: 'panel-body' },
        el('div', { class: 'summary-grid' }, cells.map(([value, label]) =>
          el('div', { class: 'summary-cell' },
            el('div', { class: 'summary-value', text: value }),
            el('div', { class: 'summary-label', text: label })))),
        // 未判分的题必须单独说清楚，否则会被读成答错
        data.unscored_count
          ? el('p', { class: 'hint', style: 'margin-top:var(--s4)',
              text: `有 ${data.unscored_count} 题未判分，不计入正确率。` })
          : null,
        data.by_dimension?.length
          ? el('div', { class: 'summary-bars' }, data.by_dimension.map((row) =>
              el('div', {},
                el('div', { class: 'summary-bar-top' },
                  el('span', { text: row.dimension }),
                  // 只报正确率，不报「对 / 答」—— DimensionAccuracy 里没有已判分数，
                  // 用已答数当分母会和上面的总正确率对不上（未判分的题被算进了分母）
                  el('span', {
                    class: 'summary-bar-value',
                    text: row.accuracy == null ? '未判分' : percent(row.accuracy),
                  })),
                el('div', { class: 'summary-bar-track' },
                  el('div', {
                    class: 'summary-bar-fill',
                    style: `width:${row.accuracy == null ? 0 : Math.round(row.accuracy * 100)}%`,
                  })))))
          : null));
  }

  function paintActions() {
    clear(actionsHolder);
    actionsHolder.append(el('button', {
      class: 'btn btn--ghost', text: '返回刷题', onClick: () => navigate('/candidate/practice'),
    }));
    if (finished) return;
    actionsHolder.append(el('button', {
      class: 'btn btn--primary',
      text: '结束练习',
      onClick: async () => {
        const c = counters();
        const ok = await confirmModal({
          title: '结束这次练习？',
          message: c.answered < c.total
            ? `还有 ${c.total - c.answered} 题没有作答。结束后本次练习不能再作答，小结会按已回答的部分给出。`
            : '结束后本次练习不能再作答，会给出这次小结。',
          confirmLabel: '结束练习',
          danger: false,
        });
        if (!ok) return;
        try {
          summary = await api.post(`/practice/sessions/${sessionId}/finish`);
          finishedLocally = true;
          finished = true;
          session.status = 'finished';
          mount(summaryHolder, summaryBlock(summary));
          paintProgress();
          paintActions();
          repaintItems();
        } catch (error) {
          toast.error(error.message);
        }
      },
    }));
  }

  function repaintItems() {
    clear(listHolder);
    listHolder.append(
      panelHead('题目', `${items.length} 题`),
      el('div', {}, items.map((item) => {
        const holder = el('div', { class: 'practice-item' });
        paintItem(holder, item);
        return holder;
      })));
  }

  mount(main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: title }),
        el('p', { class: 'page-lede', text: filterSummary(session) }),
        el('p', { class: 'meta', text: finished
          ? `开始于 ${formatDateTime(session.started_at)}，已结束`
          : '提交即判分，可以随时离开，回来接着做。' })),
      actionsHolder),
    progressHolder,
    summaryHolder,
    el('div', { style: 'margin-top:var(--s5)' }, listHolder),
  );

  paintActions();
  paintProgress();
  repaintItems();
}
