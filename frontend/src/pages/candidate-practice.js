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
 * ⚠️ **「按简历推荐」是取题方式，不是筛选条件。** 它不缩小题目池，只改变「从符合
 * 条件的题里挑哪些、怎么排」。因此它与其余六个筛选**分行**放，并且与「题量」同组 ——
 * 同排会让人以为多了一项过滤（module-22 §5.3）。
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
  // 预览响应是 `{total, items}`：total 是符合条件的真实题量（不受截断），
  // items 按 limit 截断、只用来派生分类/维度的下拉候选值
  let preview = { total: 0, items: [] };
  let resumes = [];
  try {
    [positions, sessions, preview, resumes] = await Promise.all([
      api.get('/candidate/positions'),
      api.get('/practice/sessions'),
      api.get('/practice/questions'),
      api.get('/candidate/resumes'),
    ]);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container) }))));
    return;
  }
  const pool = preview.items;

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

  // 简历**不是筛选条件**（它不缩小题目池），而是取题方式：选了之后由 AI 从符合
  // 筛选条件的题里按相关度挑选排序（PRD §4.7）。因此与「题量」同组、另起一行。
  const resume = makeSelect('不使用简历', resumes.map((r) => [r.id, r.title]));
  resume.title = '选一份自己的简历后，取题会按与它的相关度挑选排序；不选就按原有筛选取题。';
  if (!resumes.length) {
    // 没有简历时**只留「不使用」并禁用** —— 下拉里没有任何可选项，留着可点会让人
    // 以为「选一下就有了」。旁边直接把「去哪录」指出来。
    resume.disabled = true;
  }

  const count = el('span', { class: 'practice-count' });
  const start = el('button', { class: 'btn btn--primary', text: '开始练习' });
  // 「开始练习」在页面上有**两颗**（筛选栏一颗、历史记录空态一颗）。两者必须是
  // 同一个动作、**也必须共享同一个可用状态** —— 后端题库为空时筛选栏那颗会被禁掉，
  // 若空态那颗不同步，点下去就是「按了没反应」，而原因写在页面上另一处。
  const startButtons = [start];
  const setStartEnabled = (enabled) => { for (const node of startButtons) node.disabled = !enabled; };

  // 「开始练习」的创建请求在飞时为真。**必须挡住晚到的计数响应**：
  // refreshCount 的 token 只保证「不用旧结果覆盖新文案」，它仍会执行
  // setStartEnabled(total > 0) 把按钮重新点亮 —— 于是用户能在创建请求返回前
  // 再点一次，服务端各建一场会话，其中一场是空壳。
  let starting = false;

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
      const result = await api.get(`/practice/questions${query ? `?${query}` : ''}`);
      if (token !== countToken) return;
      // 报的是 `total`（真实题量），不是 `items.length`（按 limit 截断过的）——
      // 拿后者当计数会在题库大时把题量说少
      const total = result.total;
      count.textContent = total
        ? `符合条件 ${total} 题`
        : '没有符合条件的题目，换一组筛选条件';
      count.className = `practice-count${total ? '' : ' is-none'}`;
      if (!starting) setStartEnabled(total > 0);
    } catch {
      if (token !== countToken) return;
      count.textContent = '';
      if (!starting) setStartEnabled(false);
    }
  }
  for (const node of Object.values(controls)) node.addEventListener('change', refreshCount);

  /** 取题并进入练习。`trigger` 是被点的那颗按钮 —— 载入文案要落在它自己身上。 */
  async function startPractice(trigger) {
    starting = true;
    setStartEnabled(false);
    const original = trigger.textContent;
    trigger.textContent = '正在取题…';
    try {
      const body = {
        ...currentFilters(),
        size: Number(size.value) || SIZES[0],
      };
      // 选了简历才带 `resume_id`；不选时**省略该字段**（与后端「不传 / 传 null 都走
      // 普通筛选」等价，但省略更干净 —— module-22 §5.3）
      if (resume.value) body.resume_id = Number(resume.value);
      const detail = await api.post('/practice/sessions', body);
      navigate(`/candidate/practice/${detail.session.id}`);
    } catch (error) {
      // 409 = 取不到题 / 触发限流。**筛选条件保留不重置** —— 让人看到自己选的是什么
      toast.error(error.message);
      starting = false;
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

  // 简历另起一行：它不是筛选条件（不缩小题目池），只改变挑选与排序。
  // 同排会让人以为多了一项过滤，两行则把「筛什么」与「怎么挑」分开了
  const resumeBar = el('div', { class: 'filterbar filterbar--sub' },
    el('span', { class: 'filterbar-label', text: '取题方式' }),
    resume,
    // 没有简历时把「去哪录」直接指出来，而不是只留一个灰掉的下拉
    resumes.length
      ? null
      : el('span', { class: 'meta' },
          '录入简历后可按简历推荐题目 —— ',
          el('button', {
            class: 'btn btn--quiet btn--sm',
            type: 'button',
            text: '去录入',
            onClick: () => navigate('/candidate/resumes'),
          })));

  /* -------------------------- 我的练习 -------------------------- */

  const ongoing = sessions.filter((s) => s.status === 'ongoing');
  const history = sessions.filter((s) => s.status !== 'ongoing');

  mount(main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: '刷题' }),
        el('p', { class: 'page-lede' },
          '选好条件开始一次练习。题目提交即判分，答错的会自动进错题本。'))),

    el('div', { class: 'panel' }, filterBar, resumeBar),

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
