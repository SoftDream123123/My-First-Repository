/**
 * `api.js` 拦截器判定的纯函数单测（module-32 §6）。
 *
 * `isCredentialCheck` 决定「一个 401 是**凭据不符**还是**会话失效**」。
 * 判错的方向只有一个是危险的：把「凭据不符」判成「会话失效」→ 拦截器
 * `session.clear()` + 跳登录页 → 用户只是打错一次凭据却被登出。
 *
 * 这几条用例的价值不在覆盖率，而在把「哪个端点属于这一类」变成一份**会红的清单**：
 * 新增一个凭据端点却忘了登记时，这里能看出来。
 */

import { describe, expect, it } from 'vitest';
import { isCredentialCheck } from '../api.js';

describe('isCredentialCheck —— 401 是「凭据不符」而非「会话失效」', () => {
  it('三个凭据端点都在名单里', () => {
    expect(isCredentialCheck('/auth/login')).toBe(true);
    expect(isCredentialCheck('/auth/phone/login')).toBe(true);
    expect(isCredentialCheck('/candidate/invitations/hT9rQ2xLm4Zb/accept')).toBe(true);
  });

  it('accept 挂在 open 路由上，因此它**必须**在名单里', () => {
    // `/candidate/activate` 是 `open: true` —— 登录与否都可达、不重定向。
    // 因此「已登录时凭它发请求并收到 401」是**可达**的，这一条不是保险而是必需。
    expect(isCredentialCheck('/candidate/invitations/abc/accept')).toBe(true);
  });

  it('发码端点**不在**名单里，但它永不返回 401，因此无影响', () => {
    // 记录现状而非要求改动：/auth/phone/code 只返回 200 / 400 / 429。
    // 若哪天给它加了 401，这条会红 —— 那正是需要重新判断的时刻。
    expect(isCredentialCheck('/auth/phone/code')).toBe(false);
  });

  it('其他端点的 401 一律视为会话失效', () => {
    for (const path of ['/auth/me', '/users', '/interviews', '/candidate/interviews']) {
      expect(isCredentialCheck(path), path).toBe(false);
    }
  });

  it('前缀相同但不同的路径不会被误判', () => {
    // 用精确相等而非 startsWith 就是为了这个 —— 前缀匹配会把将来新增的
    // `/auth/phone/loginX` 悄悄放进名单。
    expect(isCredentialCheck('/auth/phone/login/something')).toBe(false);
    expect(isCredentialCheck('/auth/phone')).toBe(false);
    expect(isCredentialCheck('/x/auth/login')).toBe(false);
  });

  it('accept 用正则匹配，邀请码变化不影响判定', () => {
    expect(isCredentialCheck('/candidate/invitations/A/accept')).toBe(true);
    expect(isCredentialCheck('/candidate/invitations/abc-123_XYZ/accept')).toBe(true);
    // 缺段 / 多段 / 换动词都不该命中
    expect(isCredentialCheck('/candidate/invitations/accept')).toBe(false);
    expect(isCredentialCheck('/candidate/invitations/a/b/accept')).toBe(false);
    expect(isCredentialCheck('/candidate/invitations/abc/reject')).toBe(false);
  });
});
