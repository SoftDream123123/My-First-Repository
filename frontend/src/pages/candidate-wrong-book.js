/**
 * pages/candidate-wrong-book.js —— 错题本
 *
 * 不单独建表：由「判错的作答」派生（API 文档 §12.8），因此同一道题错两次只占一条，
 * 但要把错了几次标出来 —— 那正是「该重点补哪一块」的信号。
 *
 * **筛选走后端**（接口支持 `dimension` / `question_type`），不在前端过滤：
 * 前端过滤的话，「这些下拉里有哪些值」与「筛出来有几道」就各自为政了。
 *
 * ⚠️ **两个下拉的候选值必须取自响应本身**。它们此前是空的 —— `WrongBookItem`
 * 不下发 `dimension` / `question_type`，照原型写会渲染出**两个只有「不限」一项的
 * 下拉 + 一排空标签**（2026-09-21 已把这两个字段补进后端，见 API 文档 §13.24）。
 * 从响应里取值还有一个好处：下拉里给出的值**必然能筛出结果** —— 那是同一列。
 *
 * ⚠️ **未判分的题不进错题本**（`is_correct` 为 `null` 不算错）—— 这条由后端保证，
 * 前端不要自己再筛一遍，也不要把它显示成「答错」。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import {
  PRACTICE_TYPE_LABELS, choiceRecap, contextTitle, createShell, dimTag, emptyState,
  formatDateTime, loadingBlock, panelHead,
} from '../components/shell.js';
import { navigate } from '../router.js';

// 取接口允许的上限：错题本是「该复习哪些题」的清单，少给不如多给。
// 超过这个数时如实说明只列出了最近这些，而不是让「共 N 道」变成一句假话。
const LIMIT = 200;

const isSingleChoice = (row) => row.question_type === 'single_choice';

/** 选项文案由调用方给：维度是中文名可直接用，题型要转成「单选 / 简答」。 */
function makeSelect(placeholder, pairs) {
  return el('select', { class: 'select' },
    el('option', { value: '', text: placeholder }),
    pairs.map(([value, label]) => el('option', { value, text: label })));
}

/**
 * 把一组取值变成下拉选项，**按显示文案排序**。
 *
 * ⚠️ 不能按原始取值排：题型是英文枚举（`single_choice` / `short_answer`），
 * 按它排会得到「简答、单选」—— 一个在中文界面里看不出道理的顺序。
 * 按文案排才与刷题页的题型下拉一致。
 */
function pairsByLabel(values, labelOf) {
  return [...new Set(values.filter(Boolean))]
    .map((value) => [value, labelOf(value)])
    .sort((a, b) => a[1].localeCompare(b[1], 'zh'));
}

function wrongItem(row, index) {
  const single = isSingleChoice(row);
  return el('div', { class: 'practice-item' },
    el('div', { class: 'practice-item-head' },
      el('span', { class: 'score-seq', text: String(index + 1) }),
      dimTag(row.dimension),
      el('span', { class: 'tag tag--off', text: PRACTICE_TYPE_LABELS[row.question_type] ?? '' }),
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

  let all = [];
  try {
    // 先取**不筛**的一遍：它同时供给两件事 —— 空态的判定，以及两个下拉的候选值
    all = await api.get(`/practice/wrong-book?limit=${LIMIT}`);
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

  if (!all.length) {
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

  const dimensions = makeSelect('不限维度',
    pairsByLabel(all.map((row) => row.dimension), (value) => value));
  const types = makeSelect('不限题型',
    pairsByLabel(all.map((row) => row.question_type), (value) => PRACTICE_TYPE_LABELS[value] ?? value));

  const listHolder = el('div', { class: 'panel' });
  const countNode = el('span', { class: 'meta' });

  async function refresh() {
    const query = [];
    if (dimensions.value) query.push(`dimension=${encodeURIComponent(dimensions.value)}`);
    if (types.value) query.push(`question_type=${encodeURIComponent(types.value)}`);
    // 未筛时复用首次那一份，避免一次多余请求
    let rows = all;
    if (query.length) {
      try {
        rows = await api.get(`/practice/wrong-book?limit=${LIMIT}&${query.join('&')}`);
      } catch (error) {
        toast.error(error.message);
        return;
      }
    }
    countNode.textContent = rows.length ? `共 ${rows.length} 道` : '';
    mount(listHolder,
      panelHead('错题', rows.length ? `${rows.length} 道` : null),
      rows.length >= LIMIT
        ? el('p', { class: 'panel-note', style: 'padding:0 var(--s5)',
            text: `已达单次上限，只列出了最近 ${LIMIT} 道。` })
        : null,
      rows.length
        ? el('div', {}, rows.map(wrongItem))
        : el('div', { class: 'panel-body' },
            el('p', { class: 'hint', text: '当前筛选条件下没有错题。' })));
  }

  dimensions.addEventListener('change', refresh);
  types.addEventListener('change', refresh);

  mount(main, head,
    el('div', { class: 'panel' },
      el('div', { class: 'filterbar' }, dimensions, types,
        el('span', { class: 'filterbar-grow' }), countNode)),
    listHolder);

  await refresh();
}
