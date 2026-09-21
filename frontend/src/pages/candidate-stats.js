/**
 * pages/candidate-stats.js —— 练习统计
 *
 * 按维度与题型各给一组正确率条，**不画雷达图** —— PRD §1.3 明确候选人看不到
 * 雷达图（那是 HR 侧多维评分的表达）。这里要的是「哪一块该补」，条形足够。
 *
 * ⚠️ **正确率的分母是「已判分」数，不是「已作答」数**（API 文档 §12.9）。
 * 未判分的题与候选人水平无关（是 AI 没判出来，或题目还没有参考答案），
 * 放进分母会系统性低估正确率 —— 所以界面上必须把未判分的题**单独报出来**，
 * 否则候选人看到 60% 却数不出自己错了哪几道。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import {
  PRACTICE_TYPE_LABELS, contextTitle, createShell, emptyState, loadingBlock, panelHead, percent,
} from '../components/shell.js';
import { navigate } from '../router.js';

function barGroup(title, note, rows, labelOf) {
  return el('div', { class: 'panel' },
    panelHead(title, note),
    el('div', { class: 'panel-body' },
      rows.some((row) => row.answered > 0)
        ? el('div', { class: 'summary-bars', style: 'margin-top:0' }, rows.map((row) =>
            el('div', {},
              el('div', { class: 'summary-bar-top' },
                el('span', { text: labelOf(row) }),
                el('span', {
                  class: 'summary-bar-value',
                  // 已判分为 0 时不报 0%，报「未判分」—— 0% 会被读成「全错」
                  text: row.accuracy == null ? '未判分' : percent(row.accuracy),
                })),
              el('div', { class: 'summary-bar-track' },
                el('div', {
                  class: 'summary-bar-fill',
                  style: `width:${row.accuracy == null ? 0 : Math.round(row.accuracy * 100)}%`,
                })))))
        : el('p', { class: 'hint', text: '还没有可统计的作答。' })));
}

export async function render(container) {
  const { root, main } = createShell(contextTitle('练习统计'));
  mount(container, root);
  mount(main, loadingBlock('正在统计…'));

  let stats;
  try {
    stats = await api.get('/practice/stats');
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('统计加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }

  if (!stats.total_answered) {
    mount(main,
      el('div', { class: 'page-head' },
        el('div', {},
          el('h1', { text: '练习统计' }),
          el('p', { class: 'page-lede', text: '做过的题这里都会有记录。' }))),
      el('div', { class: 'panel' },
        emptyState('还没有练习记录',
          '开始刷题之后，正确率与薄弱维度会显示在这里。',
          el('button', {
            class: 'btn btn--primary',
            text: '去刷题',
            onClick: () => navigate('/candidate/practice'),
          }))));
    return;
  }

  const cells = [
    [String(stats.total_answered), '已作答'],
    [String(stats.scored_count), '已判分'],
    [percent(stats.accuracy), '正确率'],
    [String(stats.session_count), '练习次数'],
  ];

  mount(main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '练习统计' }),
        el('p', { class: 'page-lede', text: '正确率只按已判分的作答算。' }))),

    el('div', { class: 'panel' },
      el('div', { class: 'panel-body' },
        el('div', { class: 'summary-grid' }, cells.map(([value, label]) =>
          el('div', { class: 'summary-cell' },
            el('div', { class: 'summary-value', text: value }),
            el('div', { class: 'summary-label', text: label })))),
        stats.unscored_count
          ? el('p', { class: 'hint', style: 'margin-top:var(--s4)',
              text: `还有 ${stats.unscored_count} 题未判分，它们不计入正确率。` })
          : null,
        stats.accuracy == null
          ? el('p', { class: 'hint', style: 'margin-top:var(--s2)', text: '还没有已判分的作答。' })
          : null)),

    barGroup('按维度', '哪一块该补', stats.by_dimension, (row) => row.dimension),
    barGroup('按题型', null, stats.by_type,
      (row) => PRACTICE_TYPE_LABELS[row.question_type] ?? row.question_type));
}
