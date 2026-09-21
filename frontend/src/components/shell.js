/**
 * components/shell.js —— 应用外壳
 * 脊（身份 + 导航）+ 工作区（顶栏 + 内容）。
 *
 * 两端共用一副骨架，只换品牌文案与导航 —— 同一个产品的两个人格。
 * 导航项**从路由表派生**：两份清单分开维护必然漂移，而且候选人脊上
 * 不该出现 HR 的入口（反之亦然），按端过滤是这里必须做的事。
 */

import { el } from '../dom.js';
import * as auth from '../auth.js';
import * as router from '../router.js';
import * as session from '../session.js';

const BRANDS = {
  hr: { sub: 'HR 工作台', role: () => (auth.isAdmin() ? '管理员' : 'HR') },
  candidate: { sub: '候选人端', role: () => '候选人' },
};

const navItems = () => router.routes.filter(
  (route) => route.nav && route.side === session.getSide(),
);

function activeRoot() {
  const hash = location.hash.replace(/^#/, '');
  // 取**最长**的匹配前缀，避免 `/interviews` 把 `/interviews/:id/evaluation` 也点亮成同一项
  return navItems()
    .filter((item) => hash === item.path || hash.startsWith(`${item.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]?.path;
}

function buildSpine() {
  const brand = BRANDS[session.getSide()] ?? BRANDS.hr;
  const user = auth.getUser();
  const current = activeRoot();

  const nav = el(
    'nav',
    { class: 'spine-nav', 'aria-label': '主导航' },
    navItems()
      .filter((item) => !item.adminOnly || auth.isAdmin())
      .map((item) =>
        el('a', {
          class: `nav-item${current === item.path ? ' is-active' : ''}`,
          href: `#${item.path}`,
          text: item.nav,
          'aria-current': current === item.path ? 'page' : null,
        }),
      ),
  );

  return el(
    'aside',
    { class: 'spine' },
    el(
      'div',
      { class: 'spine-head' },
      el('div', { class: 'spine-mark', text: '面试助手' }),
      el('div', { class: 'spine-sub', text: brand.sub }),
    ),
    nav,
    el(
      'div',
      { class: 'spine-foot' },
      el(
        'div',
        { class: 'spine-user' },
        el('span', { class: 'spine-username', text: user?.username ?? '' }),
        el('span', { class: 'spine-role', text: brand.role() }),
      ),
      el('button', {
        class: 'btn btn--onspine btn--wide',
        text: '退出登录',
        onClick: () => auth.logout(),
      }),
    ),
  );
}

function buildTopbar(contextNodes) {
  return el('header', { class: 'topbar' }, el('div', { class: 'topbar-context' }, contextNodes));
}

/** 创建外壳。返回 { root, main }，页面把内容渲染进 main。 */
export function createShell(contextNodes = []) {
  const main = el('main', { class: 'main' });
  const root = el(
    'div',
    { class: 'shell' },
    buildSpine(),
    el('div', { class: 'workspace' }, buildTopbar(contextNodes), main),
  );
  return { root, main };
}

/** 顶栏里的页面路径。 */
export function contextTitle(text, note) {
  return [
    el('span', { class: 'topbar-title', text }),
    note ? el('span', { class: 'meta', text: note }) : null,
  ];
}

/** 浏览器标签的兜底标题 —— 按端区分：候选人不该在自己的标签页上看到「HR 工作台」。 */
export function baseTitle() {
  return session.getSide() === 'candidate' ? '面试助手 · 候选人端' : '面试助手 · HR 工作台';
}

/** 面试状态标签。状态文案与状态机一一对应（API 文档 §8.1）。 */
const STATUS_LABELS = {
  draft: '草稿',
  ongoing: '进行中',
  completed: '已完成',
  evaluating: '评估中',
  evaluated: '已评估',
};

export function statusTag(status) {
  return el('span', { class: `tag tag--${status}`, text: STATUS_LABELS[status] || status });
}

/* ---- 状态轨：面试的真实流程 ---- */

const RAIL_STAGES = [
  { key: 'ongoing', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'evaluating', label: '评估中' },
  { key: 'evaluated', label: '已评估' },
];
const RAIL_ORDER = ['draft', 'ongoing', 'completed', 'evaluating', 'evaluated'];

/**
 * `draft` 是事务内的瞬态、从不落库，因此只呈现 4 段。
 * 未知状态（后端加了新状态而前端还没跟上）按最靠前的 `ongoing` 处理，
 * 而不是让整条轨塌掉。
 */
export function statusRail(status) {
  const currentIndex = Math.max(RAIL_ORDER.indexOf(status), RAIL_ORDER.indexOf('ongoing'));
  return el(
    'ol',
    { class: 'rail', 'aria-label': '面试进度' },
    RAIL_STAGES.map((stage) => {
      const index = RAIL_ORDER.indexOf(stage.key);
      const isCurrent = index === currentIndex;
      const isDone = index < currentIndex;
      return el(
        'li',
        {
          class: `rail-step${isDone ? ' is-done' : ''}${isCurrent ? ' is-current' : ''}`,
          'aria-current': isCurrent ? 'step' : null,
        },
        el('span', { class: 'rail-index', text: String(index) }),
        el('span', { class: 'rail-label', text: stage.label }),
        el('span', { class: 'rail-bar' }),
      );
    }),
  );
}

/** 面板标题行：标题 + 可选注解 + 可选操作按钮。 */export function panelHead(title, note, actions) {
  return el('div', { class: 'panel-head' },
    el('div', {},
      el('span', { class: 'panel-title', text: title }),
      note ? el('div', { class: 'panel-note', text: note }) : null),
    actions && actions.length ? el('div', { class: 'panel-head-actions' }, actions) : null);
}

export function dimTag(dimension) {
  return el('span', { class: 'tag tag--dim', text: dimension });
}

/** 选项字母 A…Z。后端单选的选项上限是 10 个，26 个足够。 */
export function optionKey(index) { return String.fromCharCode(65 + index); }

/**
 * 从判分结果里取出**参考答案**。
 *
 * ⚠️ 这个函数存在的唯一理由是：提交作答与重新判分的响应里，参考答案**按题型二选一**
 * ——单选放在 `correct_answer`、简答放在 `reference_answer`，另一个为 `null`
 * （API 文档 §13.22）。原型只读 `reference_answer`，于是**单选题的复盘永远标不出
 * 正确答案**：界面不报错，只是那一栏空着，很难发现。
 *
 * 抽成纯函数是为了让它**能被测到** —— 留在页面里就等于永远不会被测（同 radar 的做法）。
 * 注意「练习详情」的 `PracticeItemOut` 用的是另一个形状（单选简答都放
 * `reference_answer`），它不走这个函数。
 */
export function referenceAnswerOf(result) {
  return result?.reference_answer ?? result?.correct_answer ?? null;
}

/**
 * 单选题复盘：标出**正确答案**，以及候选人**自己选错**的那一项。
 *
 * 只标正确答案是不够的 —— 复盘的价值在于让人看清「我当时选了哪个」，
 * 所以错选那一项用破坏性色单独标出，并给一句「你选的」。
 *
 * ⚠️ `correctAnswer` 必须传**已经归一化过的**参考答案：提交作答的响应里
 * 单选把答案放在 `correct_answer`、简答放在 `reference_answer`（API 文档 §13.22），
 * 两者按题型二选一。取错字段的表现是「正确答案那一项没被标出来」，
 * 界面上不会报错，只是这条复盘失去了意义。
 */
export function choiceRecap(options, correctAnswer, myAnswer) {
  return el('div', { class: 'option-list' }, (options || []).map((text, index) => {
    const isCorrect = text === correctAnswer;
    const mine = myAnswer != null && text === myAnswer;
    const flag = mine && isCorrect ? '你选对了'
      : mine ? '你选的'
        : isCorrect ? '正确答案'
          : null;
    return el('div', {
      class: ['option-item',
        isCorrect ? 'is-correct' : '',
        mine && !isCorrect ? 'is-mine-wrong' : ''].filter(Boolean).join(' '),
    },
      el('span', { class: 'option-key', text: optionKey(index) }),
      el('span', { text }),
      flag ? el('span', { class: `option-flag${mine && !isCorrect ? ' is-danger' : ''}`, text: flag }) : null);
  }));
}

/* ---- 候选人看到的「我的面试」状态 ----
   候选人关心的是**他自己接下来要做什么**，不是 HR 的面试状态机
   （draft / ongoing / completed / evaluating / evaluated）。后端下发的是 HR 的
   `status`（CandidateInterviewItem 是白名单模型，没有额外字段），翻译在这一层
   做一次 —— 否则列表页与详情页会各译一套说法。 */

const CANDIDATE_STATE_LABELS = {
  await: '待作答',
  submitted: '已交卷',
  feedback: '有反馈',
  closed: '已结束',
};

/**
 * 纯函数：把后端的两字段（`status` + `submitted`）译成候选人的四态。
 *
 *   evaluated            → feedback  —— 评估完成就一定有反馈可看，与交没交过卷无关
 *   submitted            → submitted
 *   ongoing 且未交卷      → await
 *   其余（completed / evaluating，未交卷）→ closed
 *
 * 最后一档是必要的：HR 可以不等候选人交卷就手工标记完成。那一场对当事人而言
 * **不是「待作答」**（他已经答不了了），说成待作答是句假话。
 */
export function candidateState(item) {
  if (item.status === 'evaluated') return 'feedback';
  if (item.submitted) return 'submitted';
  return item.status === 'ongoing' ? 'await' : 'closed';
}

export function candidateStateTag(item) {
  const state = candidateState(item);
  return el('span', { class: `tag tag--${state}`, text: CANDIDATE_STATE_LABELS[state] });
}

/* ---- 刷题侧的题型 / 难度文案 ----
   与 HR 题库页刻意不同字：那边是「易 / 中 / 难」「单选题 / 简答题」（编辑表单里宽裕），
   这边是筛选栏的选项与题头的小标签，一行里要塞好几项，用短名才不挤。
   三个候选人页面共用，所以放这里而不是各写一份。 */
export const PRACTICE_DIFFICULTY_LABELS = { easy: '简单', medium: '中等', hard: '困难' };
export const PRACTICE_TYPE_LABELS = { single_choice: '单选', short_answer: '简答' };

/** 正确率百分比。`null` 一律显示「—」—— 0% 与「没数据」是两件事。 */
export function percent(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

/**
 * 题目来源。**三个分支都要有** —— `resume_match` 是 MVP-3 新增的来源，
 * 漏掉它会把英文枚举值（`resume_match`）直接显示给用户，并给出错误或空的提示。
 *
 * 注：来源标签**不带底色**（`.tag--bank` / `.tag--ai` 没有对应规则），
 * 它与旁边带框的元数据标签是两层信息 —— 来源更安静，这是原型定的层级。
 */
const SOURCE_LABELS = { bank: '手工', ai: 'AI', resume_match: '简历匹配' };
const SOURCE_TITLES = {
  bank: '手工录入题库',
  ai: '由 AI 生成并收录进题库',
  resume_match: '按候选人简历从题库匹配而来',
};

export function sourceTag(source) {
  return el('span', {
    class: `tag tag--${source}`,
    text: SOURCE_LABELS[source] || source,
    title: SOURCE_TITLES[source] || '',
  });
}

function pad(n) { return String(n).padStart(2, '0'); }

/** 接口下发的是无时区的 ISO 串（按本地时间理解），因此直接取字段而不是转 UTC。 */
export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return `${formatDate(value)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 空态：空屏是一次邀请，不是板着脸。 */
export function emptyState(title, hint, action) {
  return el(
    'div',
    { class: 'empty' },
    el('p', { class: 'empty-title', text: title }),
    hint ? el('p', { text: hint }) : null,
    action ? el('div', { class: 'empty-action' }, action) : null,
  );
}

export function loadingBlock(text = '加载中…') {
  return el(
    'div',
    { class: 'empty' },
    el('div', { style: 'display:flex;justify-content:center;margin-bottom:12px' }, el('div', { class: 'spinner' })),
    el('p', { text }),
  );
}
