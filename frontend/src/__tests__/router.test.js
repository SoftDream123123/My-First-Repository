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
    expect(matchRoute('/positions')?.route.key).toBe('positions');
    expect(matchRoute('/users')?.route.key).toBe('users');
  });

  it('带不带 # 前缀都一样', () => {
    expect(matchRoute('#/positions')?.route.key).toBe('positions');
    expect(matchRoute('/positions')?.route.key).toBe('positions');
  });

  it('未注册的路径返回 null，而不是模糊匹配到别处', () => {
    // 这几个是后续模块才落地的页面 —— 现在必须**明确不匹配**，
    // 否则会渲染出「页面未注册」的错误，而不是被送去一个能用的地方。
    expect(matchRoute('/interviews')).toBeNull();
    expect(matchRoute('/candidate/interviews')).toBeNull();
    expect(matchRoute('/')).toBeNull();
  });

  it('段数不同不算匹配（防止把子路径吃掉一部分）', () => {
    expect(matchRoute('/users/1')).toBeNull();
  });
});

describe('loginPath', () => {
  it('HR 端有登录页就用它', () => {
    expect(loginPath('hr')).toBe('/login');
  });

  it('候选人端登录页还没落地时退回 HR 登录页（而不是返回一个不存在的路径）', () => {
    expect(loginPath('candidate')).toBe('/login');
  });
});

describe('defaultRoute', () => {
  it('取本端第一个带导航的路由', () => {
    expect(defaultRoute('hr', false)).toBe('/positions');
    expect(defaultRoute('hr', true)).toBe('/positions');
  });

  it('adminOnly 的路由不会成为非管理员的落地页（哪怕它排在最前）', () => {
    routes.unshift({ path: '/admin-only', key: 'adminOnly', side: 'hr', nav: '仅管理员', adminOnly: true });
    try {
      expect(defaultRoute('hr', false)).toBe('/positions');
      expect(defaultRoute('hr', true)).toBe('/admin-only');
    } finally {
      routes.shift();
    }
  });

  it('某端一条可达路由都没有时，退回该端的登录页', () => {
    expect(defaultRoute('candidate', false)).toBe('/login');
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
    const activate = { path: '/candidate/activate', side: 'candidate', isPublic: true, open: true };
    expect(decide(activate, { loggedIn: true, isAdmin: true, target: '/positions' }))
      .toEqual({ action: 'allow' });
    expect(decide(activate, { loggedIn: false, isAdmin: false, target: '/login' }))
      .toEqual({ action: 'allow' });
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

  it('端由 side 决定：HR 的登录态不算候选人端的登录态', () => {
    // 调用方在取值前会 `session.setSide(route.side)`，因此这里传进来的
    // loggedIn 已经是**候选人端**的。候选人端没登录 → 去候选人端登录页。
    const candidatePage = { path: '/candidate/practice', key: 'candidatePractice', side: 'candidate' };
    expect(decide(candidatePage, { loggedIn: false, isAdmin: false, target: '/positions' }))
      .toEqual({ action: 'redirect', to: '/login' }); // 候选人端登录页尚未落地，退回 /login
  });
});

describe('entryRoute —— 裸入口与未知 hash', () => {
  const nobody = {
    hr: { loggedIn: false, isAdmin: false },
    candidate: { loggedIn: false, isAdmin: false },
  };

  it('没登录的人进空 hash → HR 默认页', () => {
    expect(entryRoute({ hash: '', sides: nobody })).toBe('/positions');
  });

  it('未知 hash 先看前缀：`#/candidate/xxx` 不能把人弹到 HR 侧', () => {
    const out = entryRoute({ hash: '#/candidate/nowhere', sides: nobody });
    expect(out.startsWith('/candidate')).toBe(false);
    expect(out).toBe('/login'); // 候选人端页面尚未落地时的过渡结果
  });

  it('已登录的 HR 去未知 hash → 回到自己的默认页', () => {
    const sides = { ...nobody, hr: { loggedIn: true, isAdmin: true } };
    expect(entryRoute({ hash: '#/nope', sides })).toBe('/positions');
  });

  it('只登录了候选人时优先候选人端（候选人端落地后应改为候选人默认页）', () => {
    const sides = { ...nobody, candidate: { loggedIn: true, isAdmin: false } };
    // 过渡态：候选人端一条路由都没有，因此只能落到登录页。
    // 候选人模块落地后这条断言应当改成 '/candidate/interviews'。
    expect(entryRoute({ hash: '', sides })).toBe('/login');
  });

  it('两端都登录 → 优先候选人', () => {
    const sides = {
      hr: { loggedIn: true, isAdmin: true },
      candidate: { loggedIn: true, isAdmin: false },
    };
    const out = entryRoute({ hash: '', sides });
    expect(out).not.toBe('/positions');
  });
});
