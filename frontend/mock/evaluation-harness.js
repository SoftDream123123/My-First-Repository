/**
 * 评估页 —— Mock 联调测试（浏览器端）。
 *
 * 这一屏是本项目最复杂的一页（SSE 流式 + 断线重连 + 雷达图 + 报告），
 * 也是三条缺陷里两条的所在，所以单独一套用例。
 *
 * fetch 被完全接管：普通接口返回 JSON，SSE 端点返回一个真正的
 * ReadableStream —— 于是 `sse.js` 那套分帧 / 跨块缓冲的代码是**真跑**的，
 * 不是被绕过去的。
 *
 * 运行：npm run dev 后打开 /mock/evaluation-harness.html
 */

import * as evaluation from '../src/pages/evaluation.js';
import * as session from '../src/session.js';

session.save('mock-token', {
  id: 1, username: 'admin', role: 'admin', is_active: true,
  created_at: '2026-08-02T09:00:00',
});

/* ==========================================================================
   1. 假数据
   ========================================================================== */

const DIMENSIONS = ['沟通能力', '专业能力', '逻辑思维', '文化契合'];

function buildDetail(overrides = {}) {
  return {
    id: 1,
    position_id: 1,
    position_name: '后端工程师',
    candidate_name: '张三',
    candidate_contact: null,
    status: 'completed',
    created_at: '2026-09-17T10:10:00',
    completed_at: '2026-09-17T10:20:00',
    question_count: 4,
    answered_count: 4,
    jd: '负责后端服务的开发与维护。',
    evaluation_dimensions: [...DIMENSIONS],
    questions: [
      { interview_question_id: 11, seq: 1, content: '题干一：谈谈你处理过的线上故障。', dimension: '沟通能力', source: 'bank', answer: '回答一', recorded_at: '2026-09-17T10:15:00' },
      { interview_question_id: 12, seq: 2, content: '题干二：说说你最熟悉的技术栈。', dimension: '专业能力', source: 'bank', answer: '回答二', recorded_at: '2026-09-17T10:16:00' },
      { interview_question_id: 13, seq: 3, content: '题干三：如何定位一个慢查询。', dimension: '逻辑思维', source: 'ai', answer: '回答三', recorded_at: '2026-09-17T10:17:00' },
      { interview_question_id: 14, seq: 4, content: '题干四：你怎么看待代码评审。', dimension: '文化契合', source: 'ai', answer: null, recorded_at: null },
    ],
    ...overrides,
  };
}

const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

const QUESTION_EVENTS = [
  event('question', { interview_question_id: 11, seq: 1, index: 1, total: 4, dimension: '沟通能力', score: 7.0, comment: '切题。' }),
  event('question', { interview_question_id: 12, seq: 2, index: 2, total: 4, dimension: '专业能力', score: 8.0, comment: '扎实。' }),
  event('question', { interview_question_id: 13, seq: 3, index: 3, total: 4, dimension: '逻辑思维', score: 5.0, comment: '偏浅。' }),
  event('question', { interview_question_id: 14, seq: 4, index: 4, total: 4, dimension: '文化契合', score: 6.0, comment: '中肯。' }),
];

const DIMENSION_EVENTS = [
  event('dimension', { dimension: '沟通能力', index: 1, total: 4, score: 7.0, comment: '表达清晰。' }),
  event('dimension', { dimension: '专业能力', index: 2, total: 4, score: 8.0, comment: '基础扎实。' }),
  event('dimension', { dimension: '逻辑思维', index: 3, total: 4, score: 5.0, comment: '有待加强。' }),
  event('dimension', { dimension: '文化契合', index: 4, total: 4, score: 6.0, comment: '基本一致。' }),
];

const REPORT_EVENT = event('report', {
  overall_score: 6.5,
  conclusion: '整体表现良好，建议结合岗位要求综合评估。',
  strengths: ['专业能力（8.0）：表现较好'],
  weaknesses: ['逻辑思维（5.0）：有待提升'],
});

const DONE_EVENT = event('done', { status: 'evaluated' });

const FULL_STREAM = [...QUESTION_EVENTS, ...DIMENSION_EVENTS, REPORT_EVENT, DONE_EVENT];

/** 只有 2 个维度的岗位 —— 用来验证「维度 < 3 不画雷达、给降级文案」。 */
const TWO_DIM_STREAM = [
  event('question', { interview_question_id: 11, seq: 1, index: 1, total: 2, dimension: '沟通能力', score: 7.0, comment: '切题。' }),
  event('question', { interview_question_id: 12, seq: 2, index: 2, total: 2, dimension: '专业能力', score: 8.0, comment: '扎实。' }),
  event('dimension', { dimension: '沟通能力', index: 1, total: 2, score: 7.0, comment: '表达清晰。' }),
  event('dimension', { dimension: '专业能力', index: 2, total: 2, score: 8.0, comment: '基础扎实。' }),
  event('report', { overall_score: 7.5, conclusion: '还行。', strengths: ['专业能力（8.0）：表现较好'], weaknesses: ['沟通能力（7.0）：有待提升'] }),
  DONE_EVENT,
];

/* ==========================================================================
   2. fetch 接管
   ========================================================================== */

let calls = [];
/** SSE 端点的脚本队列：每次建连取一条。 */
let streamScripts = [];
let jsonHandlers = {};

const encoder = new TextEncoder();

function makeStream(script) {
  return new ReadableStream({
    async start(controller) {
      for (const step of script) {
        // 先让读取方消费掉上一个 chunk 再 error ——
        // controller.error() 会**清空队列**，同步 error 会把还没读的 chunk 丢掉，
        // 于是「断线前已收到 N 条」这类断言会看到 0。
        // delay 用来把两个 chunk 拉开距离，好在两者之间观察界面。
        await new Promise((resolve) => setTimeout(resolve, step.delay ?? 5));

        // hold：吊住不关，模拟「评估仍在进行」。
        // 不能靠「脚本跑完自动 close」—— sseConnect 的 onClose 会顺手重绘一次，
        // 那次重绘会掩盖「dimension 事件到底有没有触发重绘」。
        if (step.hold) return;

        if (step.error) {
          controller.error(new Error(step.error));
          return;
        }
        controller.enqueue(encoder.encode(step.chunk));
      }
      controller.close();
    },
  });
}

function matchedJsonHandler(method, path) {
  const exact = jsonHandlers[`${method} ${path}`];
  if (exact) return exact;
  for (const [key, fn] of Object.entries(jsonHandlers)) {
    const [m, pattern] = key.split(' ');
    if (m !== method) continue;
    const pp = pattern.split('/').filter(Boolean);
    const ap = path.split('/').filter(Boolean);
    if (pp.length !== ap.length) continue;
    if (pp.every((part, i) => part.startsWith(':') || part === ap[i])) return fn;
  }
  return null;
}

window.fetch = async (url, options = {}) => {
  const method = (options.method || 'GET').toUpperCase();
  const path = String(url).replace(/^\/api/, '');
  const body = options.body ? JSON.parse(options.body) : undefined;

  calls.push({ method, path, body, isStream: Boolean(options.signal) });

  // SSE 端点
  if (path.endsWith('/evaluation/stream')) {
    const script = streamScripts.shift() ?? [{ chunk: FULL_STREAM.join('') }];
    return { ok: true, status: 200, body: makeStream(script) };
  }

  const handler = matchedJsonHandler(method, path);
  const result = handler
    ? handler({ method, path, body })
    : { status: 404, body: { code: 'NOT_FOUND', message: `未 mock 的路由：${method} ${path}`, detail: null } };

  return {
    ok: result.status >= 200 && result.status < 300,
    status: result.status,
    async json() {
      if (result.body === undefined) throw new Error('该响应无 JSON 体');
      return result.body;
    },
  };
};

/* ==========================================================================
   3. 脚手架
   ========================================================================== */

const results = [];
const errors = [];

function check(name, condition, detail = '') {
  // 条件允许传函数（惰性求值）。
  // 必须先判类型再调用 —— `Boolean(函数)` 恒为 true，
  // 直接 Boolean(condition) 会让惰性条件的断言**永远通过**（踩过一次）。
  const pass = Boolean(typeof condition === 'function' ? condition() : condition);
  results.push({ name, pass, detail });
}

const settle = (ms = 40) => new Promise((resolve) => setTimeout(resolve, ms));

function buttonsIn(scope) {
  return [...scope.querySelectorAll('button')];
}

function buttonWith(text, scope = document) {
  return buttonsIn(scope).find((b) => b.textContent.trim() === text);
}

function toasts() {
  return [...document.querySelectorAll('.toast')].map((n) => n.textContent.trim());
}

function clearToasts() {
  document.querySelectorAll('.toast').forEach((n) => n.remove());
}

function liveRows() {
  return [...document.querySelectorAll('.main .live-row')];
}

function qscoreRows() {
  return [...document.querySelectorAll('.main .qscore')];
}

function progressText() {
  return [...document.querySelectorAll('.main .eval-progress-text')].map((n) => n.textContent.trim());
}

/* ==========================================================================
   4. 用例
   ========================================================================== */

async function run() {
  const container = document.createElement('div');
  document.body.append(container);

  async function openPage({ detail = buildDetail(), scripts = [[{ chunk: FULL_STREAM.join('') }]] } = {}) {
    evaluation.destroy();
    calls = [];
    streamScripts = scripts;
    jsonHandlers = { 'GET /interviews/:id': () => ({ status: 200, body: detail }) };
    clearToasts();
    await evaluation.render(container, { id: '1' });
    await settle();
  }

  /* ---------- 逐题流式 ---------- */

  // 只吐前两条逐题事件，停在「流式进行中」
  await openPage({
    scripts: [[{ chunk: [...QUESTION_EVENTS.slice(0, 2)].join('') }]],
  });
  await settle();

  check('逐题事件到达后进度显示 2 / 4', progressText().includes('2 / 4'), progressText().join(' | '));
  check('逐题事件渲染出 2 行实时列表', liveRows().length === 2, String(liveRows().length));
  check(
    '实时列表带分数与评语',
    liveRows()[0]?.textContent.includes('7.0') && liveRows()[0]?.textContent.includes('切题'),
    liveRows()[0]?.textContent.slice(0, 40),
  );
  check('只有一个 dimension 都没到时，雷达轴仍在（按 0 画）', Boolean(document.querySelector('.main .report-radar canvas')), '未找到雷达画布');

  /* ---------- 雷达图逐维度生长（缺口 D） ---------- */

  // 分两次吐，中间留出观察窗口：先逐题事件，400ms 后再吐维度事件。
  // 「生长」的可观察证据是**画布被重画过**：paintProgress 每次都重建 progressSlot，
  // 所以重绘会产生一个**新**的画布节点。只断言「有画布」是不够的 ——
  // 画布在逐题事件阶段就已经存在了，那断言连「dimension 不重绘」都抓不到。
  await openPage({
    scripts: [[
      { chunk: QUESTION_EVENTS.join(''), delay: 5 },
      { chunk: DIMENSION_EVENTS.slice(0, 2).join(''), delay: 400 },
      { hold: true },
    ]],
  });

  const canvasAfterQuestions = document.querySelector('.main .report-radar canvas');
  check('逐题阶段就画出雷达（轴就位，维度按 0）', Boolean(canvasAfterQuestions), '未找到雷达画布');
  check(
    '逐题阶段的画布已绘制过',
    canvasAfterQuestions ? canvasAfterQuestions.width > 0 : false,
    canvasAfterQuestions ? `width=${canvasAfterQuestions.width}` : 'n/a',
  );

  await settle(500);
  const canvasAfterDimensions = document.querySelector('.main .report-radar canvas');
  check(
    'dimension 事件到达后雷达被重绘（逐维度生长）',
    Boolean(canvasAfterDimensions) && canvasAfterDimensions !== canvasAfterQuestions,
    canvasAfterDimensions === canvasAfterQuestions ? '画布节点未变 —— 说明没收 dimension 时重绘' : 'n/a',
  );
  check('进行中不显示报告区', qscoreRows().length === 0, String(qscoreRows().length));

  /* ---------- done → 报告，且不重复请求 /report（缺口 B） ---------- */

  await openPage();
  await settle(80);

  const reportCalls = calls.filter((c) => c.path.endsWith('/report'));
  check('done 之后没有请求 GET /report', reportCalls.length === 0, `实际 ${reportCalls.length} 次`);

  const hero = document.querySelector('.main .score--hero');
  check('报告渲染总分 6.5', hero?.textContent.trim() === '6.5', hero?.textContent);
  check('报告渲染结论', document.body.textContent.includes('整体表现良好'), '');
  check('逐题明细 4 行', qscoreRows().length === 4, String(qscoreRows().length));

  const scores = [...document.querySelectorAll('.main .qscore-head')].map((n) => n.textContent);
  check(
    '逐题明细的分数来自 SSE 事件',
    scores[0]?.includes('7.0') && scores[2]?.includes('5.0'),
    scores.join(' | ').slice(0, 80),
  );

  // 题干在 head 里、回答在展开后的 body 里 —— 两者都来自本地 detail，没有第二次请求
  const headContent = document.querySelector('.main .qscore-head .qscore-content');
  check(
    '逐题明细的题干来自本地 detail（未请求报告）',
    headContent?.textContent === '题干一：谈谈你处理过的线上故障。',
    headContent?.textContent ?? 'n/a',
  );

  document.querySelector('.main .qscore-head').click();
  await settle(10);
  const firstBody = document.querySelector('.main .qscore .qscore-body');
  check(
    '点击可展开逐题明细',
    Boolean(firstBody) && !firstBody.hidden,
    firstBody ? `hidden=${firstBody.hidden}` : 'n/a',
  );
  check(
    '逐题明细的回答来自本地 detail',
    firstBody?.querySelector('.qscore-answer')?.textContent === '回答一',
    firstBody?.querySelector('.qscore-answer')?.textContent ?? 'n/a',
  );
  check('未作答的那题显示占位', document.body.textContent.includes('（未作答）'));

  /* ---------- 断线重连不翻倍（缺口 A） ---------- */

  await openPage({
    scripts: [
      // 第一次：吐了 4 条逐题事件后断开（没有 done）
      [{ chunk: QUESTION_EVENTS.join('') }, { error: 'network down' }],
      // 第二次（重连）：服务端从头重放整段
      [{ chunk: FULL_STREAM.join('') }],
    ],
  });
  await settle(60);

  check('断线后显示「连接已断开」', document.body.textContent.includes('连接已断开'), '');
  check('断线后提供「重新连接」按钮', Boolean(buttonWith('重新连接')));
  check('断线时已收到 4 条逐题事件', liveRows().length === 4, String(liveRows().length));

  buttonWith('重新连接').click();
  await settle(120);

  const rowsAfterReconnect = qscoreRows().length;
  check(
    '重连重放后逐题明细仍是 4 行（不翻倍）',
    rowsAfterReconnect === 4,
    `实际 ${rowsAfterReconnect} 行`,
  );
  check(
    '重连后报告正常渲染',
    document.querySelector('.main .score--hero')?.textContent.trim() === '6.5',
    document.querySelector('.main .score--hero')?.textContent,
  );
  check(
    '重连后进度不超总数（done 后进度区已收起）',
    progressText().length === 0,
    progressText().join(' | '),
  );

  /* ---------- 重新评估会清掉旧报告 ---------- */

  await openPage();
  await settle(80);
  check('重评前报告在屏幕上', qscoreRows().length === 4, String(qscoreRows().length));

  // 模拟「重新评估」：从 evaluated 状态回到流式
  const detail = buildDetail({ status: 'evaluated' });
  jsonHandlers = {
    'GET /interviews/:id': () => ({ status: 200, body: detail }),
    'POST /interviews/:id/evaluate': () => ({
      status: 202,
      body: { interview_id: 1, status: 'evaluating', stream_url: '/api/interviews/1/evaluation/stream' },
    }),
  };
  streamScripts = [[{ chunk: QUESTION_EVENTS.slice(0, 1).join('') }]];
  evaluation.destroy();
  await evaluation.render(container, { id: '1' });
  await settle(60);

  check(
    '重新评估进行中不再残留旧报告',
    qscoreRows().length === 0,
    String(qscoreRows().length),
  );

  /* ---------- 维度不足 3 个时降级 ---------- */

  await openPage({
    detail: buildDetail({ evaluation_dimensions: ['沟通能力', '专业能力'], status: 'completed' }),
    scripts: [[{ chunk: TWO_DIM_STREAM.join('') }]],
  });
  await settle(80);
  check(
    '维度 < 3 时显示降级文案',
    document.body.textContent.includes('维度不足 3 个'),
    '',
  );
  check('维度 < 3 时不画雷达', !document.querySelector('.main .report-radar canvas'));

  /* ---------- 未完成的面试 ---------- */

  await openPage({ detail: buildDetail({ status: 'ongoing' }) });
  check('进行中的面试直接给出方向，不建 SSE', document.body.textContent.includes('这场面试还没有完成'));
  check(
    '进行中不发 SSE 请求',
    calls.filter((c) => c.isStream).length === 0,
    String(calls.filter((c) => c.isStream).length),
  );

  evaluation.destroy();
}

/* ==========================================================================
   5. 出结果
   ========================================================================== */

function paint() {
  const passed = results.filter((r) => r.pass).length;
  const failed = results.length - passed;

  const head = document.createElement('h1');
  head.textContent = `评估页 Mock 测试：${passed} 通过 / ${failed} 失败`;
  head.className = failed === 0 ? 'ok' : 'bad';

  const table = document.createElement('table');
  table.className = 'report';
  for (const r of results) {
    const tr = document.createElement('tr');
    tr.className = r.pass ? 'pass' : 'fail';
    const cells = [r.pass ? 'PASS' : 'FAIL', r.name, r.detail];
    for (const text of cells) {
      const td = document.createElement('td');
      td.textContent = text;
      tr.append(td);
    }
    table.append(tr);
  }

  const box = document.getElementById('results');
  box.replaceChildren(head, table);
  if (errors.length) {
    const pre = document.createElement('pre');
    pre.textContent = errors.join('\n');
    box.append(pre);
  }
  document.title = failed === 0 ? `MOCK-ALL-PASS ${passed}` : `MOCK-FAIL ${failed}/${results.length}`;
}

window.addEventListener('error', (e) => errors.push(`uncaught: ${e.message}`));
window.addEventListener('unhandledrejection', (e) => errors.push(`unhandled rejection: ${e.reason}`));

run()
  .catch((error) => errors.push(`用例执行中断: ${error?.stack || error}`))
  .finally(paint);
