/**
 * pages/candidate-wrong-book.js —— 错题本
 *
 * 不单独建表：由「判错的作答」派生（API 文档 §12.8），因此同一道题错两次只占一条，
 * 但要把错了几次标出来 —— 那正是「该重点补哪一块」的信号。
 *
 * ⚠️ **未判分的题不进错题本**（`is_correct` 为 `null` 不算错）—— 这条由后端保证，
 * 前端不要自己再筛一遍，也不要把它显示成「答错」。
 *
 * ⚠️ **本轮不做维度 / 题型筛选**，原因是一条真实的后端缺口：
 * `WrongBookItem`（`backend/app/practice/schemas.py`）里**没有 `dimension`、
 * 也没有 `question_type`** —— 端点接受这两个筛选参数（§12.8），但响应不下发它们。
 * 于是这里的下拉既取不到候选值、条目上也没法标出维度与题型。
 * 原型 `standalone.html` 直接读了这两个字段，照搬会渲染出一排空标签 + 两个只有
 * 「不限」一项的下拉。**补上这两个字段之后**，筛选与标签都是十几行的增量。
 *
 * 题型仍然可判：简答题的 `options` **必须为空数组**（§7.1 的硬约束），
 * 因此 `options.length > 0` ⟺ 单选题。这不是猜测，是从已有字段推出的结构事实。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import {
  choiceRecap, contextTitle, createShell, emptyState, formatDateTime, loadingBlock, panelHead,
} from '../components/shell.js';
import { navigate } from '../router.js';

// 取接口允许的上限：错题本是「该复习哪些题」的清单，少给不如多给。
// 超过这个数时如实说明只显示了最近这些，而不是让「共 N 道」变成一句假话。
const LIMIT = 200;

const isSingleChoice = (row) => Array.isArray(row.options) && row.options.length > 0;

function wrongItem(row, index) {
  const single = isSingleChoice(row);
  return el('div', { class: 'practice-item' },
    el('div', { class: 'practice-item-head' },
      el('span', { class: 'score-seq', text: String(index + 1) }),
      el('span', { class: 'tag tag--off', text: single ? '单选' : '简答' }),
      el('span', {
        class: 'tag tag--wrong',
        style: 'margin-left:auto',
        text: `错 ${row.wrong_count} 次`,
      })),
    el('p', { class: 'practice-item-question', text: row.content }),

    single
      ? el('div', { class: 'practice-answer' },
          choiceRecap(row.options, row.reference_answer, row.my_wrong_answer))
      : el('div', {},
          el('div', { class: 'practice-answer' },
            el('div', { class: 'dossier-label', text: '我的作答' }),
            el('p', { class: 'answer-quote', text: row.my_wrong_answer || '（空）' })),
          row.reference_answer
            ? el('div', { class: 'practice-answer' },
                el('div', { class: 'dossier-label', text: '参考答案' }),
                el('p', { class: 'answer-quote', text: row.reference_answer }))
            : null),

    row.explanation
      ? el('div', { class: 'practice-answer' },
          el('div', { class: 'dossier-label', text: '解析' }),
          el('p', { class: 'score-comment', style: 'margin-top:0', text: row.explanation }))
      : null,

    el('p', { class: 'meta', style: 'margin-top:var(--s4)',
      text: `最近错于 ${formatDateTime(row.last_wrong_at)}` }));
}

export async function render(container) {
  const { root, main } = createShell(contextTitle('错题本'));
  mount(container, root);
  mount(main, loadingBlock('正在整理错题…'));

  let rows = [];
  try {
    rows = await api.get(`/practice/wrong-book?limit=${LIMIT}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('错题本加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('h1', { text: '错题本' }),
      el('p', { class: 'page-lede' },
        '答错的题都会收在这里。同一道题错几次就记几次，错得多的排在上面。')));

  if (!rows.length) {
    mount(main, head, el('div', { class: 'panel' },
      emptyState('还没有错题',
        '答错的题会自动进这里，附上参考答案与解析。',
        el('button', {
          class: 'btn btn--primary',
          text: '去刷题',
          onClick: () => navigate('/candidate/practice'),
        }))));
    return;
  }

  mount(main, head,
    el('div', { class: 'panel' },
      panelHead('错题', `共 ${rows.length} 道`),
      rows.length >= LIMIT
        ? el('p', { class: 'panel-note', style: 'padding:0 var(--s5)',
            text: `已达单次上限，只列出了最近 ${LIMIT} 道。` })
        : null,
      el('div', {}, rows.map(wrongItem))));
}
