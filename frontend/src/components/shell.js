/**
 * 应用外壳：侧边导航 + 顶栏（module-07 §3.4）。
 * 以及状态轨 —— 全站的结构脊柱。
 */

import { el, append } from '../dom.js';
import * as auth from '../auth.js';
import { navigate } from '../router.js';

const NAV = [
  { path: '/interviews', label: '面试' },
  { path: '/positions', label: '岗位' },
  { path: '/questions', label: '题库' },
  { path: '/users', label: '用户管理', adminOnly: true },
];

/** 当前所在的顶层路径，用于点亮导航。 */
function activeRoot() {
  const hash = location.hash.replace(/^#/, '') || '/interviews';
  return NAV.find((item) => hash.startsWith(item.path))?.path;
}

function buildSidebar() {
  const nav = el(
    'nav',
    { class: 'sidebar-nav', 'aria-label': '主导航' },
    NAV.filter((item) => !item.adminOnly || auth.isAdmin()).map((item) =>
      el('a', {
        class: `nav-item${activeRoot() === item.path ? ' is-active' : ''}`,
        href: `#${item.path}`,
        text: item.label,
        'aria-current': activeRoot() === item.path ? 'page' : null,
      }),
    ),
  );

  return el(
    'aside',
    { class: 'sidebar' },
    el(
      'div',
      { class: 'sidebar-brand' },
      '面试助手',
      el('span', { text: 'HR 工作台' }),
    ),
    nav,
  );
}

function buildTopbar(contextNodes) {
  const user = auth.getUser();

  return el(
    'header',
    { class: 'topbar' },
    el('div', { class: 'topbar-context' }, contextNodes),
    el(
      'div',
      { class: 'topbar-user' },
      el('span', { text: `${user?.username ?? ''}${auth.isAdmin() ? '（管理员）' : ''}` }),
      el('button', {
        class: 'btn btn--quiet btn--sm',
        text: '退出',
        onClick: () => auth.logout(),
      }),
    ),
  );
}

/**
 * 创建外壳。返回 { root, main }，页面把内容渲染进 main。
 */
export function createShell(contextNodes = []) {
  const main = el('main', { class: 'main' });
  const root = el(
    'div',
    { class: 'shell' },
    buildSidebar(),
    el('div', { class: 'workspace' }, buildTopbar(contextNodes), main),
  );

  return { root, main };
}

/** 顶栏里的页面标题。 */
export function contextTitle(text, note) {
  return [
    el('span', { class: 'topbar-title', text }),
    note ? el('span', { class: 'meta', text: note }) : null,
  ];
}

/* ==========================================================================
   状态轨 —— 面试的真实流程，不是装饰性步骤条
   ========================================================================== */

const STAGES = [
  { key: 'ongoing', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'evaluating', label: '评估中' },
  { key: 'evaluated', label: '已评估' },
];

const ORDER = ['draft', 'ongoing', 'completed', 'evaluating', 'evaluated'];

/**
 * 状态轨。draft 是事务内瞬态（module-05 §5.1），不对外可见，因此只呈现 4 段。
 */
export function statusRail(status) {
  const currentIndex = Math.max(ORDER.indexOf(status), ORDER.indexOf('ongoing'));

  return el(
    'ol',
    { class: 'rail', 'aria-label': '面试进度' },
    STAGES.map((stage) => {
      const index = ORDER.indexOf(stage.key);
      const isCurrent = index === currentIndex;
      const isDone = index < currentIndex;

      return el(
        'li',
        {
          class: `rail-step${isDone ? ' is-done' : ''}${isCurrent ? ' is-current' : ''}`,
          'aria-current': isCurrent ? 'step' : null,
        },
        el('span', { class: 'rail-label', text: stage.label }),
      );
    }),
  );
}

/* ==========================================================================
   共享的小展示件
   ========================================================================== */

const STATUS_LABELS = {
  draft: '草稿',
  ongoing: '进行中',
  completed: '已完成',
  evaluating: '评估中',
  evaluated: '已评估',
};

export function statusTag(status) {
  return el('span', {
    class: `tag tag--${status}`,
    text: STATUS_LABELS[status] || status,
  });
}

const SOURCE_LABELS = { bank: '手工', ai: 'AI' };

export function sourceTag(source) {
  return el('span', {
    class: `tag tag--${source}`,
    text: SOURCE_LABELS[source] || source,
    title: source === 'ai' ? '由 AI 生成并收录进题库' : '手工录入题库',
  });
}

export function dimTag(dimension) {
  return el('span', { class: 'tag tag--dim', text: dimension });
}

/** 分数着色：阈值 6.5 与后端 strengths 的定义一致（module-04 §4.4）。 */
export function scoreClass(score) {
  return score >= 6.5 ? 'is-pass' : 'is-watch';
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  const pad = (n) => String(n).padStart(2, '0');
  return `${formatDate(value)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 表格空态 —— 空屏是一次邀请，不是情绪的板着脸。 */
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

export { navigate };
