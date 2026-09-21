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
