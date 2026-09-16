/**
 * HTTP 封装（module-07 §4.1）。
 *
 * MOCK 开关：原型阶段由内存 mock 后端应答，页面代码写的是真实契约，
 * 接上 FastAPI 时把 MOCK 置为 false 即可，页面代码一行不改。
 *
 * 切换方式：URL 加 ?live=1 走真实后端，或控制台执行
 *   localStorage.setItem('prototype.live', '1')
 */

import * as mock from './mock.js';

const LIVE =
  new URLSearchParams(location.search).has('live') ||
  localStorage.getItem('prototype.live') === '1';

export const isLive = () => LIVE;

/** 后端 BASE。原型默认指向本地 FastAPI。 */
const BASE = '/api';

const NETWORK_MESSAGE = '网络连接失败，请检查后端服务';

export class ApiError extends Error {
  constructor({ code = 'UNKNOWN', message, detail = null, status = 0 }) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
    this.status = status;
  }
}

let unauthorizedHandler = null;

export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

export function clearToken() {
  localStorage.removeItem('prototype.token');
  localStorage.removeItem('prototype.user');
}

function token() {
  return localStorage.getItem('prototype.token');
}

export async function request(method, path, body) {
  if (!LIVE) return mockRequest(method, path, body);

  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError({ code: 'NETWORK_ERROR', message: NETWORK_MESSAGE });
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (response.ok) return payload;

  const shaped = payload && typeof payload.code === 'string' && 'message' in payload;
  const error = new ApiError(
    shaped
      ? { ...payload, status: response.status }
      : {
          code: 'UNKNOWN',
          message: `请求失败（${response.status}）`,
          status: response.status,
        },
  );

  if (response.status === 401) {
    clearToken();
    if (unauthorizedHandler) unauthorizedHandler();
  }

  throw error;
}

export const get = (path) => request('GET', path);
export const post = (path, body) => request('POST', path, body);
export const put = (path, body) => request('PUT', path, body);
export const patch = (path, body) => request('PATCH', path, body);
export const del = (path) => request('DELETE', path);

/* ==========================================================================
   内存 mock 后端 —— 仅原型使用
   ========================================================================== */

const db = {
  users: structuredClone(mock.users),
  positions: structuredClone(mock.positions),
  questions: structuredClone(mock.questions),
  interviews: structuredClone(mock.interviews),
  answers: new Map(), // interview_question_id -> content
  reports: { 101: structuredClone(mock.report101) },
  evaluating: new Set([104]),
};

let nextId = 500;

// 预置 101 的回答，使详情页的"已答 8"与数据一致
for (const q of mock.interviewQuestions[101]) {
  db.answers.set(q.interview_question_id, q.answer ?? "");
}
for (const q of mock.interviewQuestions[102]) {
  if (q.answer !== null) db.answers.set(q.interview_question_id, q.answer);
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function fail(status, code, message, detail = null) {
  throw new ApiError({ status, code, message, detail });
}

function detailOf(id) {
  const base = db.interviews.find((i) => i.id === Number(id));
  if (!base) fail(404, 'NOT_FOUND', '面试不存在');

  const seeded = mock.interviewQuestions[base.id];
  const questions = seeded
    ? seeded.map((q) => ({
        ...q,
        answer: db.answers.has(q.interview_question_id)
          ? db.answers.get(q.interview_question_id)
          : q.answer,
      }))
    : mock.getInterviewDetail(base.id).questions;

  return { ...base, questions };
}

async function mockRequest(method, path, body) {
  await delay(120 + Math.random() * 160); // 模拟真实往返，让加载态可见

  const [rawPath, query] = path.split('?');
  const parts = rawPath.split('/').filter(Boolean);
  const params = new URLSearchParams(query || '');

  // ---- 认证 ----
  if (method === 'POST' && rawPath === '/auth/login') {
    const user = db.users.find(
      (u) => u.username === body.username && u.is_active,
    );
    if (!user || body.password.length < 4) {
      fail(401, 'UNAUTHORIZED', '用户名或密码错误');
    }
    return { token: 'prototype-token', user: publicUser(user) };
  }

  if (method === 'GET' && rawPath === '/auth/me') {
    return publicUser(db.users[0]);
  }

  // ---- 用户 ----
  if (parts[0] === 'users') {
    if (method === 'GET') return db.users.map(publicUser);

    if (method === 'POST') {
      if (db.users.some((u) => u.username === body.username)) {
        fail(409, 'BUSINESS_ERROR', '用户名已存在');
      }
      const user = {
        id: nextId++,
        username: body.username,
        role: body.role,
        is_active: true,
        created_at: new Date().toISOString(),
      };
      db.users.push(user);
      return publicUser(user);
    }

    if (method === 'PATCH') {
      const user = db.users.find((u) => u.id === Number(parts[1]));
      if (!user) fail(404, 'NOT_FOUND', '用户不存在');
      if (user.id === 1) fail(409, 'BUSINESS_ERROR', '不能修改自己的角色或状态');
      if (body.role) user.role = body.role;
      if (body.is_active !== undefined) user.is_active = body.is_active;
      return publicUser(user);
    }
  }

  // ---- 岗位 ----
  if (parts[0] === 'positions') {
    if (method === 'GET' && parts.length === 1) {
      const keyword = params.get('keyword');
      return keyword
        ? db.positions.filter((p) => p.name.includes(keyword))
        : db.positions;
    }

    if (method === 'POST') {
      if (db.positions.some((p) => p.name === body.name)) {
        fail(409, 'BUSINESS_ERROR', '该岗位名称已存在');
      }
      const position = {
        id: nextId++,
        ...body,
        created_by: 1,
        created_at: new Date().toISOString(),
      };
      db.positions.push(position);
      return position;
    }

    if (method === 'PUT') {
      const position = db.positions.find((p) => p.id === Number(parts[1]));
      if (!position) fail(404, 'NOT_FOUND', '岗位不存在');
      Object.assign(position, body);
      return position;
    }

    if (method === 'DELETE') {
      const id = Number(parts[1]);
      const used = db.questions.some((q) => q.position_id === id);
      if (used) fail(409, 'BUSINESS_ERROR', '该岗位已被题库或面试引用，无法删除');
      db.positions = db.positions.filter((p) => p.id !== id);
      return null;
    }
  }

  // ---- 题库 ----
  if (parts[0] === 'questions') {
    if (method === 'GET' && parts.length === 1) {
      return db.questions.filter((q) => {
        if (params.get('position_id') && q.position_id !== Number(params.get('position_id'))) return false;
        if (params.get('category') && q.category !== params.get('category')) return false;
        if (params.get('dimension') && q.dimension !== params.get('dimension')) return false;
        if (params.get('source') && q.source !== params.get('source')) return false;
        if (params.get('keyword') && !q.content.includes(params.get('keyword'))) return false;
        return true;
      });
    }

    if (method === 'POST') {
      const question = {
        id: nextId++,
        ...body,
        category: body.category || '通用',
        difficulty: body.difficulty || 'medium',
        tags: body.tags || [],
        source: 'bank', // 服务端决定
        created_by: 1,
        created_at: new Date().toISOString(),
      };
      db.questions.push(question);
      return question;
    }

    if (method === 'PUT') {
      const question = db.questions.find((q) => q.id === Number(parts[1]));
      if (!question) fail(404, 'NOT_FOUND', '题目不存在');
      Object.assign(question, body, {
        category: body.category || '通用',
        difficulty: body.difficulty || 'medium',
        tags: body.tags || [],
      });
      return question;
    }

    if (method === 'DELETE') {
      db.questions = db.questions.filter((q) => q.id !== Number(parts[1]));
      return null;
    }
  }

  // ---- 面试 ----
  if (parts[0] === 'interviews') {
    const id = Number(parts[1]);

    if (method === 'GET' && parts.length === 1) return db.interviews;
    if (method === 'GET' && parts.length === 2) return detailOf(id);

    if (method === 'POST' && parts.length === 1) {
      const position = db.positions.find((p) => p.id === body.position_id);
      if (!position) fail(404, 'NOT_FOUND', '岗位不存在');

      const interview = {
        id: nextId++,
        position_id: position.id,
        position_name: position.name,
        candidate_name: body.candidate_name,
        candidate_contact: body.candidate_contact || null,
        status: 'ongoing',
        created_at: new Date().toISOString(),
        completed_at: null,
        question_count: 8,
        answered_count: 0,
      };
      db.interviews.unshift(interview);
      return detailOf(interview.id);
    }

    if (method === 'POST' && parts[2] === 'answers') {
      db.answers.set(body.interview_question_id, body.content);
      const detail = detailOf(id);
      db.interviews.find((i) => i.id === id).answered_count = detail.questions.filter(
        (q) => q.answer,
      ).length;
      return detail.questions.find((q) => q.interview_question_id === body.interview_question_id);
    }

    if (method === 'POST' && (parts[2] === 'complete' || parts[2] === 'rollback')) {
      const interview = db.interviews.find((i) => i.id === id);
      if (!interview) fail(404, 'NOT_FOUND', '面试不存在');

      const target = parts[2] === 'complete' ? 'completed' : 'ongoing';
      const allowed =
        (interview.status === 'ongoing' && target === 'completed') ||
        ((interview.status === 'completed' || interview.status === 'evaluated') &&
          target === 'ongoing');

      if (!allowed) {
        fail(409, 'BUSINESS_ERROR', `不允许从「${label(interview.status)}」迁移到「${label(target)}」`, {
          from: interview.status,
          to: target,
        });
      }

      interview.status = target;
      interview.completed_at = target === 'completed' ? new Date().toISOString() : null;
      return detailOf(id);
    }

    if (method === 'PATCH') {
      const interview = db.interviews.find((i) => i.id === id);
      if (!interview) fail(404, 'NOT_FOUND', '面试不存在');
      if (interview.status === 'evaluating' || interview.status === 'evaluated') {
        fail(409, 'BUSINESS_ERROR', '评估中或已评估的面试不可修改候选人信息');
      }
      if (body.candidate_name) interview.candidate_name = body.candidate_name;
      if ('candidate_contact' in body) interview.candidate_contact = body.candidate_contact;
      return detailOf(id);
    }

    if (method === 'POST' && parts[2] === 'evaluate') {
      const interview = db.interviews.find((i) => i.id === id);
      if (!interview) fail(404, 'NOT_FOUND', '面试不存在');
      if (interview.status === 'evaluating') {
        return {
          interview_id: id,
          status: 'evaluating',
          stream_url: `/api/interviews/${id}/evaluation/stream`,
        };
      }
      if (interview.status !== 'completed' && interview.status !== 'evaluated') {
        fail(409, 'BUSINESS_ERROR', '当前状态不可开始评估');
      }
      interview.status = 'evaluating';
      db.evaluating.add(id);
      return {
        interview_id: id,
        status: 'evaluating',
        stream_url: `/api/interviews/${id}/evaluation/stream`,
      };
    }

    if (method === 'GET' && parts[2] === 'report') {
      const interview = db.interviews.find((i) => i.id === id);
      if (!interview) fail(404, 'NOT_FOUND', '面试不存在');
      if (interview.status !== 'evaluated') fail(409, 'BUSINESS_ERROR', '评估尚未完成');
      return db.reports[id] || null;
    }
  }

  fail(404, 'NOT_FOUND', `原型未实现的接口：${method} ${rawPath}`);
}

function publicUser(user) {
  const { username, role, is_active, created_at, id } = user;
  return { id, username, role, is_active, created_at };
}

const STATUS_LABELS = {
  draft: '草稿',
  ongoing: '进行中',
  completed: '已完成',
  evaluating: '评估中',
  evaluated: '已评估',
};

function label(status) {
  return STATUS_LABELS[status] || status;
}

/** 原型专用的评估完成标记，让 SSE 演示能落回真实状态。 */
export function markEvaluated(interviewId) {
  const interview = db.interviews.find((i) => i.id === Number(interviewId));
  if (!interview) return;
  interview.status = 'evaluated';
  interview.completed_at = interview.completed_at || new Date().toISOString();
  db.evaluating.delete(Number(interviewId));
  if (!db.reports[interviewId]) db.reports[interviewId] = structuredClone(mock.report101);
}
