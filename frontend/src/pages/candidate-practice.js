/**
 * pages/candidate-practice.js —— 刷题（选条件 → 开始练习 + 我的练习）
 *
 * 两处判断：
 *
 * 1. **筛选栏与取题同口径。** 岗位下拉来自 `GET /candidate/positions`（只含有题的
 *    岗位），分类与维度从 `GET /practice/questions` 的实际题池里派生 —— 否则会出现
 *    「下拉里有它，选了却取不到题」。筛选改动时打一次取题接口把「符合条件 N 题」
 *    实时报出来，候选人不必先点了开始才知道是空的。
 * 2. **进行中的练习必须出现在这里。** 它是候选人中途离开后唯一的返回入口
 *    （module-15 §4.3），因此不塞进「历史记录」里，单独给一块。
 *
 * ⚠️ **本页当前不做「按简历推荐」。** 那需要一个简历下拉 + 无简历时的引导链接
 * （指向 `#/candidate/resumes`），而简历页还没落地 —— 挂一个点进去报错的链接
 * 比缺这个入口更难查。module-22 会把这块增量加进来。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import {
  PRACTICE_DIFFICULTY_LABELS, PRACTICE_TYPE_LABELS, contextTitle, createShell, emptyState,
  formatDateTime, loadingBlock, panelHead,
} from '../components/shell.js';
import { navigate } from '../router.js';

const DIFFICULTIES = [['easy', '简单'], ['medium', '中等'], ['hard', '困难']];
const TYPES = [['single_choice', '单选'], ['short_answer', '简答']];
const SIZES = [5, 10, 15, 20];

/** 首项固定为「不限」，因此 value === '' 表示不过滤。 */
function makeSelect(placeholder, pairs) {
  return el('select', { class: 'select' },
    el('option', { value: '', text: placeholder }),
    pairs.map(([value, label]) => el('option', { value: String(value), text: label })));
}

function distinct(values) {
  return [...new Set(values.filter((v) => v != null && v !== ''))].sort((a, b) => a.localeCompare(b, 'zh'));
}

const filterSummary = (session) => {
  const parts = [];
  if (session.category) parts.push(session.category);
  if (session.dimension) parts.push(session.dimension);
  if (session.difficulty) parts.push(PRACTICE_DIFFICULTY_LABELS[session.difficulty] ?? session.difficulty);
  if (session.question_type) parts.push(PRACTICE_TYPE_LABELS[session.question_type] ?? session.question_type);
  return parts.length ? parts.join(' · ') : '全部题目';
};

function progressCell(session) {
  const total = session.total || 0;
  const done = session.answered_count || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  return el('div', { class: 'progress' },
    el('div', { class: 'progress-track' },
      el('div', { class: 'progress-fill', style: `width:${percent}%` })),
    el('span', { class: 'progress-value', text: `${done} / ${total}` }));
}

function sessionTable(rows, actionLabel) {
  return el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: '岗位' }),
      el('th', { text: '进度' }),
      el('th', { text: '答对' }),
      el('th', { text: '开始时间' }),
      el('th', {}))),
    el('tbody', {}, rows.map((session) => el('tr', {},
      el('td', {},
        el('strong', { text: session.position_name ?? '不限岗位' }),
        el('div', { class: 'meta', text: filterSummary(session) })),
      el('td', {}, progressCell(session)),
      el('td', { class: 'cell-num', text: String(session.correct_count ?? 0) }),
      el('td', { class: 'meta', text: formatDateTime(session.started_at) }),
      el('td', { class: 'cell-actions' },
        el('button', {
          class: 'btn btn--quiet btn--sm',
          text: actionLabel,
          onClick: () => navigate(`/candidate/practice/${session.session_id}`),
        }))))));
}

export async function render(container) {
  const { root, main } = createShell(contextTitle('刷题'));
  mount(container, root);
  mount(main, loadingBlock('正在加载题库与练习记录…'));

  let positions = [];
  let sessions = [];
  let pool = [];
  try {
    [positions, sessions, pool] = await Promise.all([
      api.get('/candidate/positions'),
      api.get('/practice/sessions'),
      api.get('/practice/questions'),
    ]);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }

  /* ---------------------------- 筛选栏 ---------------------------- */

  const controls = {
    position_id: makeSelect('不限岗位', positions.map((p) => [p.id, `${p.name}（${p.question_count} 题）`])),
    category: makeSelect('不限分类', distinct(pool.map((q) => q.category)).map((v) => [v, v])),
    dimension: makeSelect('不限维度', distinct(pool.map((q) => q.dimension)).map((v) => [v, v])),
    difficulty: makeSelect('不限难度', DIFFICULTIES),
    question_type: makeSelect('不限题型', TYPES),
  };
  const size = makeSelect('题量', SIZES.map((n) => [n, `${n} 题`]));
  size.value = String(SIZES[0]);

  const count = el('span', { class: 'practice-count' });
  const start = el('button', { class: 'btn btn--primary', text: '开始练习' });
  // 「开始练习」在页面上有**两颗**（筛选栏一颗、历史记录空态一颗）。两者必须是
  // 同一个动作、**也必须共享同一个可用状态** —— 后端题库为空时筛选栏那颗会被禁掉，
  // 若空态那颗不同步，点下去就是「按了没反应」，而原因写在页面上另一处。
  const startButtons = [start];
  const setStartEnabled = (enabled) => { for (const node of startButtons) node.disabled = !enabled; };

  function currentFilters() {
    const out = {};
    for (const [key, node] of Object.entries(controls)) {
      if (!node.value) continue;
      out[key] = key === 'position_id' ? Number(node.value) : node.value;
    }
    return out;
  }

  // 候选条件变化时会连打几次取题接口，晚到的旧响应不能覆盖新结果
  let countToken = 0;
  async function refreshCount() {
    const token = (countToken += 1);
    const filters = currentFilters();
    const query = Object.entries(filters)
      .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
      .join('&');
    try {
      const rows = await api.get(`/practice/questions${query ? `?${query}` : ''}`);
      if (token !== countToken) return;
      count.textContent = rows.length
        ? `符合条件 ${rows.length} 题`
        : '没有符合条件的题目，换一组筛选条件';
      count.className = `practice-count${rows.length ? '' : ' is-none'}`;
      setStartEnabled(rows.length > 0);
    } catch {
      if (token !== countToken) return;
      count.textContent = '';
      setStartEnabled(false);
    }
  }
  for (const node of Object.values(controls)) node.addEventListener('change', refreshCount);

  /** 取题并进入练习。`trigger` 是被点的那颗按钮 —— 载入文案要落在它自己身上。 */
  async function startPractice(trigger) {
    setStartEnabled(false);
    const original = trigger.textContent;
    trigger.textContent = '正在取题…';
    try {
      // 不传 `resume_id`：本轮还没有简历相关的能力，省略比传 null 更干净
      // （后端对「不传」与「传 null」等价处理，都走普通筛选）
      const detail = await api.post('/practice/sessions', {
        ...currentFilters(),
        size: Number(size.value) || SIZES[0],
      });
      navigate(`/candidate/practice/${detail.session.id}`);
    } catch (error) {
      // 409 = 取不到题 / 触发限流。**筛选条件保留不重置** —— 让人看到自己选的是什么
      toast.error(error.message);
      setStartEnabled(true);
      trigger.textContent = original;
    }
  }
  start.addEventListener('click', () => startPractice(start));

  const filterBar = el('div', { class: 'filterbar' },
    Object.values(controls),
    size,
    el('span', { class: 'filterbar-grow' }),
    count,
    start);

  /* -------------------------- 我的练习 -------------------------- */

  const ongoing = sessions.filter((s) => s.status === 'ongoing');
  const history = sessions.filter((s) => s.status !== 'ongoing');

  mount(main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '刷题' }),
        el('p', { class: 'page-lede' },
          '选好条件开始一次练习。题目提交即判分，答错的会自动进错题本。'))),

    el('div', { class: 'panel' }, filterBar),

    ongoing.length
      ? el('div', { class: 'panel' },
          panelHead('继续练习', '没做完的都在这里'),
          sessionTable(ongoing, '继续'))
      : null,

    el('div', { class: 'panel' },
      panelHead('历史记录', history.length ? `${history.length} 次` : null),
      history.length
        ? sessionTable(history, '查看')
        : emptyState('还没有练习记录',
            '选好上面的条件，开始第一次练习。',
            (() => {
              // 与筛选栏那颗**同一个动作、同一份可用状态**（见 startButtons 的说明）
              const button = el('button', {
                class: 'btn btn--primary',
                text: '开始练习',
                disabled: start.disabled,
                onClick: () => startPractice(button),
              });
              startButtons.push(button);
              return button;
            })())),
  );

  refreshCount();
}
