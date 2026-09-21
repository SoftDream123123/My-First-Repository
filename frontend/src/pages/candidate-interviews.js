/**
 * pages/candidate-interviews.js —— 我的面试
 *
 * 候选人端的默认落地页（路由表里排在最前）。这一屏只回答一个问题：
 * **我接下来该做什么。** 因此分两块而不是一张大表 ——
 * 「待你作答」是他要动手的事，「我的记录」是其余（已交卷 / 有反馈 / 已结束）。
 *
 * 状态标签的颜色刻意只有两种：要动手的（待作答 / 有反馈）用品牌靛蓝，其余全灰。
 * 分数色带（`--pass` / `--watch`）在候选人侧一次都不出现 —— 他看不到分数，
 * 颜色就不该暗示分数存在。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import {
  candidateState, candidateStateTag, contextTitle, createShell, emptyState,
  formatDateTime, loadingBlock, panelHead,
} from '../components/shell.js';
import { navigate } from '../router.js';

/**
 * 进度条单元格。与 HR 面试列表里的同名函数是**同一件东西**，两份是刻意留的：
 * HR 那一份属于 module-23，本模块不动 HR 侧任何文件（模块验收要求 HR 零改动）。
 */
function progressCell(item) {
  const total = item.question_count || 0;
  const done = item.answered_count || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  return el('div', { class: 'progress' },
    el('div', { class: 'progress-track' },
      el('div', { class: 'progress-fill', style: `width:${percent}%` })),
    el('span', { class: 'progress-value', text: `${done} / ${total}` }));
}

const positionCell = (item) => el('td', {}, el('strong', { text: item.position_name }));

// 「收到邀请」而不是「创建时间」：`created_at` 是 HR 建这场面试的时刻，
// 对候选人而言它就是邀请进来的那一天
const TIME_HEAD = '收到邀请';

function awaitingTable(items) {
  return el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: '岗位' }),
      el('th', { text: '进度' }),
      el('th', { text: TIME_HEAD }),
      el('th', {}))),
    el('tbody', {}, items.map((item) => el('tr', {},
      positionCell(item),
      el('td', {}, progressCell(item)),
      el('td', { class: 'meta', text: formatDateTime(item.created_at) }),
      el('td', { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--primary btn--sm',
          text: '进入作答',
          onClick: () => navigate(`/candidate/interviews/${item.id}`),
        }))))));
}

function recordTable(items) {
  return el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: '岗位' }),
      el('th', { text: '状态' }),
      el('th', { text: '题数' }),
      el('th', { text: TIME_HEAD }),
      el('th', {}))),
    el('tbody', {}, items.map((item) => {
      const state = candidateState(item);
      return el('tr', {},
        positionCell(item),
        el('td', {}, candidateStateTag(item)),
        el('td', { class: 'cell-num', text: String(item.question_count ?? 0) }),
        el('td', { class: 'meta', text: formatDateTime(item.created_at) }),
        el('td', { class: 'cell-actions' },
          // 有反馈的场次直接给反馈入口：那是候选人在这页上最想看的东西
          state === 'feedback'
            ? el('button', {
                class: 'btn btn--primary btn--sm',
                text: '查看反馈',
                onClick: () => navigate(`/candidate/interviews/${item.id}/feedback`),
              })
            : el('button', {
                class: 'btn btn--quiet btn--sm',
                text: '查看作答',
                onClick: () => navigate(`/candidate/interviews/${item.id}`),
              })));
    })));
}

export async function render(container) {
  const { root, main } = createShell(contextTitle('我的面试'));
  mount(container, root);
  mount(main, loadingBlock('正在加载你的面试…'));

  let items = [];
  try {
    items = await api.get('/candidate/interviews');
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('h1', { text: '我的面试' }),
      el('p', { class: 'page-lede' },
        '招聘方邀请你参加的面试都在这里。交卷前可以随时改，交卷后由招聘方评估，评估完成就能看到反馈。')));

  if (!items.length) {
    mount(main, head, el('div', { class: 'panel' }, emptyState(
      '还没有面试',
      '招聘方发给你的邀请码可以直接进面试；只想先练手的话，去刷题。',
      el('button', {
        class: 'btn btn--primary',
        text: '凭邀请码进入',
        onClick: () => navigate('/candidate/activate'),
      }))));
    return;
  }

  const awaiting = items.filter((item) => candidateState(item) === 'await');
  const records = items.filter((item) => candidateState(item) !== 'await');

  mount(main, head,
    awaiting.length
      ? el('div', { class: 'panel' },
          panelHead('待你作答', awaiting.length > 1 ? `${awaiting.length} 场` : '招聘方在等你交卷'),
          awaitingTable(awaiting))
      : null,
    records.length
      ? el('div', { class: 'panel' },
          panelHead('我的记录', `${records.length} 场`),
          recordTable(records))
      : null);
}
