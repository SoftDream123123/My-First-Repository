/**
 * router 纯函数单测。
 *
 * 为什么单测的是**守卫决策**而不是页面：路由守卫的错法都很安静 ——
 * 少一次重定向就是白屏，多一次重定向就是「点了没反应」，而这类问题
 * 在浏览器里要靠手工构造登录态才能复现。把它抽成纯函数之后，这些边界
 * 就是几行断言。
 *
 * 这儿**不引入 jsdom / testing-library**（module-07 §8.1 的既有决策）：
 * 纯函数不需要 DOM，页面行为由 `mock/*-harness.html` 在真实浏览器里跑。
 */

import { describe, expect, it } from 'vitest';
import { decide, defaultRoute, entryRoute, loginPath, matchRoute, routes } from '../router.js';

describe('matchRoute', () => {
  it('匹配到已注册的路由，并给出 key', () => {
    expect(matchRoute('/login')?.route.key).toBe('login');
    expect(matchRoute('/interviews')?.route.key).toBe('interviews');
    expect(matchRoute('/positions')?.route.key).toBe('positions');
    expect(matchRoute('/users')?.route.key).toBe('users');
    expect(matchRoute('/candidate/login')?.route.key).toBe('candidateLogin');
    expect(matchRoute('/candidate/activate')?.route.key).toBe('candidateActivate');
    expect(matchRoute('/candidate/interviews')?.route.key).toBe('candidateInterviews');
  });

  it('带不带 # 前缀都一样', () => {
    expect(matchRoute('#/positions')?.route.key).toBe('positions');
    expect(matchRoute('/positions')?.route.key).toBe('positions');
  });

  it('`:id` 段被提取成 params，而不是当成字面量', () => {
    expect(matchRoute('/interviews/7')?.route.key).toBe('interviewDetail');
    expect(matchRoute('/interviews/7')?.params).toEqual({ id: '7' });
    expect(matchRoute('/candidate/interviews/3')?.route.key).toBe('candidateInterviewDetail');
    expect(matchRoute('/candidate/interviews/3')?.params).toEqual({ id: '3' });
    expect(matchRoute('/candidate/interviews/3/feedback')?.route.key).toBe('candidateFeedback');
  });

  it('候选人端两个前缀相同的路由不会互相吃掉', () => {
    // `/candidate/interviews/:id` 与 `/candidate/interviews/:id/feedback` 段数不同，
    // 前者不能把后者截走一部分
    expect(matchRoute('/candidate/interviews/3/feedback')?.route.key).not.toBe('candidateInterviewDetail');
  });

  it('候选人练习一侧的四条路由都匹配得上', () => {
    expect(matchRoute('/candidate/practice')?.route.key).toBe('candidatePractice');
    expect(matchRoute('/candidate/practice/7')?.route.key).toBe('practiceSession');
    expect(matchRoute('/candidate/practice/7')?.params).toEqual({ id: '7' });
    expect(matchRoute('/candidate/wrong-book')?.route.key).toBe('wrongBook');
    expect(matchRoute('/candidate/stats')?.route.key).toBe('practiceStats');
  });

  it('未注册的路径返回 null，而不是模糊匹配到别处', () => {
    // 这是最后一个还没落地的候选人页面 —— 现在必须**明确不匹配**，
    // 否则会渲染出「页面未注册」的错误，而不是被送去一个能用的地方。
    expect(matchRoute('/candidate/resumes')).toBeNull();
    expect(matchRoute('/')).toBeNull();
  });

  it('段数不同不算匹配（防止把子路径吃掉一部分）', () => {
    expect(matchRoute('/users/1')).toBeNull();
    expect(matchRoute('/interviews/1/2')).toBeNull();
  });
});

describe('loginPath', () => {
  it('按端给出各自的登录页', () => {
    expect(loginPath('hr')).toBe('/login');
    expect(loginPath('candidate')).toBe('/candidate/login');
  });
});

describe('defaultRoute', () => {
  it('取本端第一个带导航的路由', () => {
    expect(defaultRoute('hr', false)).toBe('/interviews');
    expect(defaultRoute('hr', true)).toBe('/interviews');
  });

  it('候选人端的默认页是「我的面试」，不是刷题也不是登录页', () => {
    // 候选人最关心的永远是「有没有待答的面试」，刷题是次一级的自主行为
    expect(defaultRoute('candidate', false)).toBe('/candidate/interviews');
  });

  it('adminOnly 的路由不会成为非管理员的落地页（哪怕它排在最前）', () => {
    routes.unshift({ path: '/admin-only', key: 'adminOnly', side: 'hr', nav: '仅管理员', adminOnly: true });
    try {
      expect(defaultRoute('hr', false)).toBe('/interviews');
      expect(defaultRoute('hr', true)).toBe('/admin-only');
    } finally {
      routes.shift();
    }
  });

  it('某端一条可达路由都没有时，退回该端的登录页', () => {
    // 这是防御性分支：`loginPath` 本身也要保证不回一个不存在的路径，
    // 否则用户会被送去一个匹配不上任何路由的地方
    const removed = routes.splice(0, routes.length, ...routes.filter((r) => r.side === 'candidate'));
    try {
      expect(defaultRoute('hr', false)).toBe('/login');
    } finally {
      routes.splice(0, routes.length, ...removed);
    }
  });
});

describe('decide —— 公开页', () => {
  const loginRoute = routes.find((r) => r.path === '/login');

  it('未登录 → 放行', () => {
    expect(decide(loginRoute, { loggedIn: false, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'allow' });
  });

  it('已登录 → 送回本端默认页', () => {
    expect(decide(loginRoute, { loggedIn: true, isAdmin: true, target: '/positions' }))
      .toEqual({ action: 'redirect', to: '/positions' });
  });

  it('已登录但本端还没有可达页面 → 放行，不做「重定向到自己」的空转', () => {
    // 同 hash 不触发 hashchange，重定向到自己会让页面空着不渲染
    expect(decide(loginRoute, { loggedIn: true, isAdmin: false, target: '/login' }))
      .toEqual({ action: 'allow' });
  });

  it('open 的路由登录与否都放行（激活页要这样）', () => {
    const activate = routes.find((r) => r.path === '/candidate/activate');
    expect(activate.open).toBe(true);
    expect(decide(activate, { loggedIn: true, isAdmin: true, target: '/positions' }))
      .toEqual({ action: 'allow' });
    expect(decide(activate, { loggedIn: false, isAdmin: false, target: '/candidate/login' }))
      .toEqual({ action: 'allow' });
  });

  it('候选人登录页已登录 → 送回候选人默认页（不是 HR 默认页）', () => {
    const route = routes.find((r) => r.path === '/candidate/login');
    expect(decide(route, { loggedIn: true, isAdmin: false, target: '/candidate/interviews' }))
      .toEqual({ action: 'redirect', to: '/candidate/interviews' });
  });
});

describe('decide —— 受保护页', () => {
  const positionsRoute = routes.find((r) => r.path === '/positions');
  const usersRoute = routes.find((r) => r.path === '/users');

  it('未登录 → 去本端登录页', () => {
    expect(decide(positionsRoute, { loggedIn: false, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'redirect', to: '/login' });
    expect(decide(usersRoute, { loggedIn: false, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'redirect', to: '/login' });
  });

  it('已登录的 HR 角色可以进岗位', () => {
    expect(decide(positionsRoute, { loggedIn: true, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'allow' });
  });

  it('adminOnly 的页面：管理员放行，HR 被拦下并改道', () => {
    expect(decide(usersRoute, { loggedIn: true, isAdmin: true, target: '/positions' }))
      .toEqual({ action: 'allow' });
    expect(decide(usersRoute, { loggedIn: true, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'deny', message: '无权限访问该页面', to: '/positions' });
  });

  it('守不住也无处可去时给出 to=null（避免无限改道）', () => {
    const verdict = decide(usersRoute, { loggedIn: true, isAdmin: false, target: '/users' });
    expect(verdict.action).toBe('deny');
    expect(verdict.to).toBeNull();
  });

  it('候选人页面未登录 → 去**候选人**登录页，不是 HR 登录页', () => {
    // 调用方在取值前会 `session.setSide(route.side)`，因此这里传进来的
    // loggedIn 已经是**候选人端**的。候选人端没登录 → 去候选人端登录页。
    for (const path of ['/candidate/interviews', '/candidate/interviews/:id', '/candidate/interviews/:id/feedback']) {
      const route = routes.find((r) => r.path === path);
      expect(decide(route, { loggedIn: false, isAdmin: false, target: '/candidate/interviews' }))
        .toEqual({ action: 'redirect', to: '/candidate/login' });
    }
  });

  it('候选人已登录 → 放行候选人页面', () => {
    const route = routes.find((r) => r.path === '/candidate/interviews');
    expect(decide(route, { loggedIn: true, isAdmin: false, target: '/candidate/interviews' }))
      .toEqual({ action: 'allow' });
  });

  it('跨端串号：守卫按端的 token 判定，不会放行后再让人吃一屏 403', () => {
    // 按端分 key 存储的直接后果：一端登录时另一端的 token 是 null。
    // 调用方据此传进来的 loggedIn 是「本条路由所属那一端」的状态，
    // 因此两个方向都应当在这一步就被送回本端登录页。
    const hrRoute = routes.find((r) => r.path === '/positions');
    const candidateRoute = routes.find((r) => r.path === '/candidate/interviews');

    // HR 登录、候选人端未登录 → 候选人页面被送回候选人登录页
    expect(decide(candidateRoute, { loggedIn: false, isAdmin: false, target: '/candidate/interviews' }))
      .toEqual({ action: 'redirect', to: '/candidate/login' });
    // 候选人登录、HR 端未登录 → HR 页面被送回 HR 登录页
    expect(decide(hrRoute, { loggedIn: false, isAdmin: false, target: '/interviews' }))
      .toEqual({ action: 'redirect', to: '/login' });
  });
});

describe('entryRoute —— 裸入口与未知 hash', () => {
  const nobody = {
    hr: { loggedIn: false, isAdmin: false },
    candidate: { loggedIn: false, isAdmin: false },
  };

  it('没登录的人进空 hash → HR 默认页', () => {
    expect(entryRoute({ hash: '', sides: nobody })).toBe('/interviews');
  });

  it('未知 hash 先看前缀：`#/candidate/xxx` 不能把人弹到 HR 侧', () => {
    const out = entryRoute({ hash: '#/candidate/nowhere', sides: nobody });
    expect(out.startsWith('/candidate')).toBe(true);
    expect(out).toBe('/candidate/interviews');
  });

  it('已登录的 HR 去未知 hash → 回到自己的默认页', () => {
    const sides = { ...nobody, hr: { loggedIn: true, isAdmin: true } };
    expect(entryRoute({ hash: '#/nope', sides })).toBe('/interviews');
  });

  it('只登录了候选人时优先候选人端', () => {
    const sides = { ...nobody, candidate: { loggedIn: true, isAdmin: false } };
    expect(entryRoute({ hash: '', sides })).toBe('/candidate/interviews');
  });

  it('两端都登录 → 优先候选人', () => {
    const sides = {
      hr: { loggedIn: true, isAdmin: true },
      candidate: { loggedIn: true, isAdmin: false },
    };
    expect(entryRoute({ hash: '', sides })).toBe('/candidate/interviews');
  });
});
