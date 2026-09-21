/**
 * 评估模块 Mock 联调测试。
 *
 * 这个测试台的价值有一半在**事件契约**上：原型 `standalone.html` 用的是
 * `stage` / `question_score` / `dimension_score`，而真实后端推的是
 * `question` / `dimension` / `report` / `done` / `error`（API 文档 §9.2）。
 * 照搬原型的话整页收不到任何一条进度，而界面上只会表现为「一直转圈」。
 * 所以这里逐条钉住事件名、字段名与推送顺序。
 *
 * 另一半在**重连重放**上：服务端从头重放是设计特性，前端若按「来一条加一条」
 * 累加，刷新一次进度就翻倍。这里专门喂一份重放报文来验它。
 *
 * 运行：npm run dev 后打开 /mock/evaluation-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import {
  buttonIn, clearToasts, closeAnyModal, createReport, installFakeBackend,
  openOverlay, settle, sseText, toasts,
} from './harness.js';

const report = createReport('评估模块 Mock 测试');
const { check } = report;

session.setSide('hr');
session.save('hr-token', {
  id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
});

/* ---------- 假数据 ---------- */

// 必须是 3 个及以上：少于 3 个时页面**故意**改画横条（围不成面积），
// 那样就测不到雷达图那条路径了。
const DIMS = ['专业能力', '沟通能力', '逻辑思维'];

function questions() {
  return [
    { interview_question_id: 101, seq: 1, content: '第 1 题的题干。', dimension: '专业能力',
      source: 'bank', answer: '第 1 题的回答内容。', recorded_at: '2026-09-09T11:00:00', answer_source: 'hr' },
    { interview_question_id: 102, seq: 2, content: '第 2 题的题干。', dimension: '沟通能力',
      source: 'bank', answer: '   ', recorded_at: '2026-09-09T11:00:00', answer_source: 'hr' },
    { interview_question_id: 103, seq: 3, content: '第 3 题的题干。', dimension: '逻辑思维',
      source: 'bank', answer: '第 3 题的回答内容。', recorded_at: '2026-09-09T11:00:00', answer_source: 'hr' },
  ];
}

let STATUS = 'completed';

function detail() {
  return {
    id: 1, position_id: 1, position_name: '后端工程师', candidate_name: '张三',
    candidate_contact: '13800000000', status: STATUS,
    created_at: '2026-09-08T10:00:00', completed_at: '2026-09-09T11:00:00',
    question_count: 3, answered_count: 2, jd: '……',
    evaluation_dimensions: DIMS, resume_id: null, questions: questions(),
  };
}

const REPORT = {
  interview_id: 1, candidate_name: '张三', position_name: '后端工程师',
  overall_score: 6.5,
  conclusion: '整体表现良好，建议结合岗位要求综合评估。',
  strengths: ['专业能力（7.0）：技术基础扎实', '逻辑思维（6.5）：分析有条理'],
  weaknesses: ['沟通能力（6.0）：表达可再凝练'],
  evaluated_at: '2026-09-21T10:30:00',
  dimension_scores: [
    { dimension: '专业能力', score: 7.0, comment: '技术基础扎实。' },
    { dimension: '沟通能力', score: 6.0, comment: '表达可再凝练。' },
    { dimension: '逻辑思维', score: 6.5, comment: '分析有条理。' },
  ],
  question_scores: [
    { interview_question_id: 101, seq: 1, content: '第 1 题的题干。', dimension: '专业能力',
      answer: '第 1 题的回答内容。', score: 7.0, comment: '回答切题。' },
    { interview_question_id: 102, seq: 2, content: '第 2 题的题干。', dimension: '沟通能力',
      answer: '', score: 6.0, comment: '未作答，按 0 分计入。' },
    { interview_question_id: 103, seq: 3, content: '第 3 题的题干。', dimension: '逻辑思维',
      answer: '第 3 题的回答内容。', score: 6.5, comment: '思路清晰。' },
  ],
};

/** 正常的评估流：3 题 → 2 维 → 报告 → done，中间夹两次心跳。 */
function goodStream() {
  return sseText([
    { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '回答切题。' } },
    null,
    { event: 'question', data: { interview_question_id: 102, seq: 2, index: 2, total: 3, dimension: '沟通能力', score: 6.0, comment: '未作答，按 0 分计入。' } },
    null,
    { event: 'question', data: { interview_question_id: 103, seq: 3, index: 3, total: 3, dimension: '逻辑思维', score: 6.5, comment: '思路清晰。' } },
    { event: 'dimension', data: { dimension: '专业能力', index: 1, total: 3, score: 7.0, comment: '技术基础扎实。' } },
    { event: 'dimension', data: { dimension: '沟通能力', index: 2, total: 3, score: 6.0, comment: '表达可再凝练。' } },
    { event: 'dimension', data: { dimension: '逻辑思维', index: 3, total: 3, score: 6.5, comment: '分析有条理。' } },
    { event: 'report', data: { overall_score: 6.5, conclusion: REPORT.conclusion, strengths: REPORT.strengths, weaknesses: REPORT.weaknesses } },
    { event: 'done', data: { status: 'evaluated' } },
  ]);
}

let STREAM = goodStream();
let STREAM_CHUNK = 5; // 刻意切得很碎，逼出跨块缓冲
let PRINTED = 0;

function defaultHandlers() {
  return {
    'GET /auth/me': () => ({ status: 200, body: { id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00' } }),
    'GET /interviews/:id': () => ({ status: 200, body: detail() }),
    'GET /interviews/:id/report': () => ({ status: 200, body: REPORT }),
    'POST /interviews/:id/evaluate': () => {
      STATUS = 'evaluating';
      return { status: 202, body: { interview_id: 1, status: 'evaluating', stream_url: '/api/interviews/1/evaluation/stream' } };
    },
    'GET /interviews/:id/evaluation/stream': () => ({ status: 200, stream: STREAM, chunkSize: STREAM_CHUNK }),
    'GET /interviews/:id/report/export': () => ({
      status: 200,
      blob: 'PK\u0003\u0004fake-docx',
      headers: {
        'Content-Disposition': "attachment; filename=\"report.docx\"; filename*=UTF-8''%E5%BC%A0%E4%B8%89-%E9%9D%A2%E8%AF%95%E6%8A%A5%E5%91%8A.docx",
      },
    }),
  };
}

const backend = installFakeBackend(defaultHandlers());
installUnauthorizedHandler();
window.print = () => { PRINTED += 1; };

/* ---------- DOM 助手 ---------- */

const page = () => document.getElementById('app');
const scoreItems = () => [...page().querySelectorAll('.score-item')];
/**
 * 安全地从第 i 条逐题行里取一段文本。
 * ⚠️ 不要写 `scoreItems()[0].querySelector(...)`：**实参在进入 check 之前就求值了**，
 * 数组为空时那个 `.querySelector` 会直接抛出去、把整轮跑挂掉，
 * 报告只留下抛错前的几条 —— 恰恰是出问题时最需要看全的时候。
 */
const scoreText = (index, selector) => scoreItems()[index]?.querySelector(selector)?.textContent ?? null;
const scoreHasClass = (index, selector, cls) =>
  scoreItems()[index]?.querySelector(selector)?.classList.contains(cls) ?? null;
const legendRows = () => [...page().querySelectorAll('.dim-legend-row')];
const streamNote = () => page().querySelector('.stream-note');
const overallScore = () => page().querySelector('.report-score-value')?.textContent ?? null;

async function go(target) {
  router.navigate(String(target).replace(/^#/, ''));
  await settle();
  await settle();
  await settle();
}

/** 轮询等待条件成立 —— 流是分块异步读的，固定 settle 次数会脆。 */
async function waitFor(predicate, timeout = 4000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (predicate()) return true;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return false;
}

function reset(status) {
  STATUS = status;
  STREAM = goodStream();
  STREAM_CHUNK = 5;
  PRINTED = 0;
  clearToasts();
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }
  session.setSide('hr');
  session.save('hr-token', {
    id: 2, username: 'li.yan', role: 'hr', is_active: true, created_at: '2026-08-11T09:00:00',
  });

  reset('completed');
  backend.setHandlers(defaultHandlers());
  await boot(document.getElementById('app'));
  await settle();

  /* ---------- 1. 未完成面试：不能评估 ---------- */
  reset('ongoing');
  await go('#/interviews/1/evaluation');
  check('ongoing → 提示先标记完成', page().textContent.includes('还不能评估'), page().textContent.slice(0, 60));

  /* ---------- 2. completed：尚未评估 + 三步说明 ---------- */
  reset('completed');
  await go('#/interviews/1/evaluation');
  check('completed → 显示「尚未评估」而非直接开跑',
    page().querySelector('.panel-title')?.textContent === '尚未评估', String(page().querySelector('.panel-title')?.textContent));
  check('给出三步说明（逐题 / 多维 / 汇总）', page().querySelectorAll('.stage-list li').length === 3,
    String(page().querySelectorAll('.stage-list li').length));
  check('有未作答的题时提前说明会按 0 分计入',
    page().querySelector('.note-box')?.textContent.includes('1 道题没有记录回答') ?? false,
    String(page().querySelector('.note-box')?.textContent));
  check('有「开始评估」按钮', buttonIn(page(), '开始评估') !== undefined);
  check('状态轨停在「已完成」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '已完成',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));

  /* ---------- 3. 触发评估 → 接流 ---------- */
  backend.reset();
  buttonIn(page(), '开始评估').click();
  await waitFor(() => scoreItems().length === 3);
  check('点「开始评估」→ POST evaluate', Boolean(backend.find('POST', '/interviews/1/evaluate')));
  // 注意：状态轨「评估中」这一态要在**流还开着**的时候断言（见用例 10）——
  // 跑完这一整条流之后它已经正确地变成「已评估」了。

  /* ---------- 4. 事件契约：逐题分逐条落地 ---------- */
  check('逐题分按事件逐条出现（3 条全到）', scoreItems().length === 3, `实际 ${scoreItems().length}`);
  check('逐题行按 seq 升序', scoreItems().map((n) => n.querySelector('.score-seq').textContent).join(',') === '1,2,3',
    scoreItems().map((n) => n.querySelector('.score-seq').textContent).join(','));
  check('逐题分带维度标签', scoreText(0, '.tag') === '专业能力', String(scoreText(0, '.tag')));
  check('逐题分带分数', scoreText(0, '.score-value') === '7.0', String(scoreText(0, '.score-value')));
  check('逐题分带评估意见', scoreText(0, '.score-comment') === '回答切题。', String(scoreText(0, '.score-comment')));
  check('逐题分带候选人回答原文', scoreText(0, '.answer-quote') === '第 1 题的回答内容。', String(scoreText(0, '.answer-quote')));
  check('空白回答标为「本题未作答」（不是渲染一个空框）',
    scoreText(1, '.answer-quote') === '本题未作答', String(scoreText(1, '.answer-quote')));
  check('未作答那条也带 is-blank 样式', scoreHasClass(1, '.answer-quote', 'is-blank') === true,
    String(scoreHasClass(1, '.answer-quote', 'is-blank')));

  /* ---------- 5. 心跳被静默丢弃 ---------- */
  check('报文里的 `: ping` 没有变成任何一条进度或错误', !page().textContent.includes('ping'));

  /* ---------- 6. 维度分与雷达图 ---------- */
  await waitFor(() => page().querySelector('.radar-area') !== null);
  check('三个维度全到 → 画出雷达多边形（少一个顶点就不封口）',
    page().querySelector('.radar-area') !== null);
  check('雷达图的顶点数等于维度数', page().querySelector('.radar-area')?.getAttribute('points')?.split(' ').length === 3,
    String(page().querySelector('.radar-area')?.getAttribute('points')));
  check('维度图例有 3 行（每维一行）', legendRows().length === 3, `实际 ${legendRows().length}`);
  // 取行前先判存在 —— 直接 legendRows()[0].querySelector 在数组为空时会抛，把整轮跑挂掉
  const legendText = (index) => legendRows()[index]?.querySelector('.dim-legend-comment')?.textContent ?? '';
  const legendPass = (index) => legendRows()[index]?.querySelector('.dim-legend-score')?.classList.contains('is-pass') ?? null;
  check('图例每行带该维度的评语', legendText(0) === '技术基础扎实。', legendText(0));
  check('图例分数按 6.5 阈值上色（7.0 达标）', legendPass(0) === true, String(legendPass(0)));
  check('图例分数按 6.5 阈值上色（6.0 待改进）', legendPass(1) === false, String(legendPass(1)));
  check('图例分数按 6.5 阈值上色（6.5 恰好达标 —— 阈值是 >= 不是 >）',
    legendPass(2) === true, String(legendPass(2)));

  /* ---------- 7. 汇总报告 ---------- */
  await waitFor(() => buttonIn(page(), '导出 DOCX') !== undefined);
  check('总分渲染成一位小数', overallScore() === '6.5', String(overallScore()));
  check('总分达标时用 pass 色', page().querySelector('.report-score-value')?.classList.contains('is-pass'));
  check('综合结论落地', page().querySelector('.report-conclusion')?.textContent === REPORT.conclusion,
    String(page().querySelector('.report-conclusion')?.textContent));
  check('优点照抄进结论下方（两条都在）',
    [...page().querySelectorAll('.report-finds .find-item.is-pass')].map((n) => n.textContent).join(' | ')
      === '专业能力（7.0）：技术基础扎实 | 逻辑思维（6.5）：分析有条理',
    [...page().querySelectorAll('.report-finds .find-item.is-pass')].map((n) => n.textContent).join(' | '));
  check('待改进同上',
    page().querySelector('.report-finds .find-item.is-watch')?.textContent === '沟通能力（6.0）：表达可再凝练',
    String(page().querySelector('.report-finds .find-item.is-watch')?.textContent));

  /* ---------- 8. done 之后：状态行消失、动作出现 ---------- */
  check('收到 done → 状态行消失', streamNote() === null, String(streamNote()?.textContent));
  check('done 后状态轨走到「已评估」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '已评估',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));
  check('done 后出现「重新评估」', buttonIn(page(), '重新评估') !== undefined);
  check('done 后出现「导出 DOCX」与「导出 PDF」',
    buttonIn(page(), '导出 DOCX') !== undefined && buttonIn(page(), '导出 PDF') !== undefined,
    [...page().querySelectorAll('.page-head-actions button')].map((b) => b.textContent).join(','));

  /* ---------- 9. 重连重放：按 id 覆盖而不是追加 ---------- */
  reset('evaluating');
  // 服务端从头重放（API 文档 §9.2）：同一批 question 事件发两遍。
  // 刻意**不带 done**，这样进度计数还留在屏幕上，能直接读它有没有翻倍。
  const replayable = sseText([
    { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '回答切题。' } },
    { event: 'question', data: { interview_question_id: 102, seq: 2, index: 2, total: 3, dimension: '沟通能力', score: 6.0, comment: '未作答。' } },
    { event: 'question', data: { interview_question_id: 103, seq: 3, index: 3, total: 3, dimension: '逻辑思维', score: 6.5, comment: '思路清晰。' } },
  ]);
  STREAM = replayable + replayable;
  STREAM_CHUNK = 32;
  backend.setHandlers({ ...defaultHandlers(), 'GET /interviews/:id/evaluation/stream': () => ({ status: 200, stream: STREAM, chunkSize: STREAM_CHUNK, hold: true }) });
  await go('#/interviews/1/evaluation');
  await waitFor(() => scoreItems().length === 3);
  check('重放两遍 → 逐题行**没有翻倍**（仍为 3 条）', scoreItems().length === 3, `实际 ${scoreItems().length}`);
  check('重放两遍 → 进度计数没有翻倍（3 / 3，不是 6 / 3）',
    page().querySelector('.stream-count')?.textContent === '3 / 3',
    String(page().querySelector('.stream-count')?.textContent));

  /* ---------- 10. 只到一部分维度时不封口 ---------- */
  reset('evaluating');
  STREAM = sseText([
    { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '好。' } },
  ]);
  STREAM_CHUNK = 40;
  // 连接**一直开着**：评估进行中本来就是长连接，推完即断是另一种情形（见用例 13）
  backend.setHandlers({ ...defaultHandlers(), 'GET /interviews/:id/evaluation/stream': () => ({ status: 200, stream: STREAM, chunkSize: STREAM_CHUNK, hold: true }) });
  await go('#/interviews/1/evaluation');
  await waitFor(() => page().querySelector('.score-item') !== null);
  check('只有一个维度到 → **不画**多边形（提前封口等于编一个读数）',
    page().querySelector('.radar-area') === null);
  check('但流没结束，状态行还在', streamNote() !== null);
  check('评估进行中 → 状态轨停在「评估中」',
    page().querySelector('.rail-step.is-current .rail-label')?.textContent === '评估中',
    String(page().querySelector('.rail-step.is-current .rail-label')?.textContent));
  check('状态行显示逐题进度 1 / 3', page().querySelector('.stream-count')?.textContent === '1 / 3',
    String(page().querySelector('.stream-count')?.textContent));

  /* ---------- 11. 阶段文案随已到的东西推进 ---------- */
  reset('evaluating');
  STREAM = sseText([
    { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '好。' } },
    { event: 'dimension', data: { dimension: '专业能力', index: 1, total: 2, score: 7.0, comment: '好。' } },
  ]);
  backend.setHandlers({ ...defaultHandlers(), 'GET /interviews/:id/evaluation/stream': () => ({ status: 200, stream: STREAM, chunkSize: 40, hold: true }) });
  await go('#/interviews/1/evaluation');
  await waitFor(() => page().querySelector('.score-item') !== null);
  check('有维度分之后状态行改说「正在生成多维评分…」',
    streamNote()?.textContent.includes('正在生成多维评分') ?? false, String(streamNote()?.textContent));

  /* ---------- 12. error 事件：提示 + 回退到可重试的状态 ---------- */
  reset('evaluating');
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /interviews/:id/evaluation/stream': () => {
      // ⚠️ 后端在推 error 之前**已经把状态回退到 completed**（API 文档 §9.2），
      // 假后端必须一起模拟这一步：否则页面收到 error 后重新加载，又会看到
      // evaluating 并重新接流，于是「报错 → 重连 → 再报错」无限循环打转。
      STATUS = 'completed';
      return {
        status: 200,
        chunkSize: 40,
        stream: sseText([
          { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '好。' } },
          { event: 'error', data: { code: 'AI_PROVIDER_ERROR', message: 'AI 服务调用失败，请稍后重试' } },
        ]),
      };
    },
  });
  STATUS = 'evaluating';
  await go('#/interviews/1/evaluation');
  await waitFor(() => toasts().some((t) => t.includes('AI 服务调用失败')));
  check('error 事件 → 弹出后端文案', toasts().some((t) => t.includes('AI 服务调用失败')), toasts().join(' | '));
  await waitFor(() => page().textContent.includes('尚未评估'));
  check('评估失败后 → 回到「尚未评估」，可以直接重试（后端已回退状态）',
    page().textContent.includes('尚未评估'), page().textContent.slice(0, 80));

  /* ---------- 13. 流断开（没有 done）不是「失败」 ---------- */
  reset('evaluating');
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /interviews/:id/evaluation/stream': () => ({
      status: 200,
      chunkSize: 40,
      // 只推一条就断流：任务可能还在后台跑
      stream: sseText([
        { event: 'question', data: { interview_question_id: 101, seq: 1, index: 1, total: 3, dimension: '专业能力', score: 7.0, comment: '好。' } },
      ]),
    }),
  });
  STATUS = 'evaluating';
  await go('#/interviews/1/evaluation');
  await waitFor(() => streamNote()?.classList.contains('is-failed') === true);
  check('断流 → 说「可能仍在后台继续」，而不是断言失败',
    streamNote()?.textContent.includes('可能仍在后台继续') ?? false, String(streamNote()?.textContent));
  check('断流 → 给「重新加载」而不是让人干等', buttonIn(streamNote(), '重新加载') !== undefined);

  /* ---------- 14. 已评估：拉报告而不是接流 ---------- */
  reset('evaluated');
  backend.setHandlers(defaultHandlers());
  backend.reset(defaultHandlers());
  await go('#/interviews/1/evaluation');
  await waitFor(() => scoreItems().length > 0);
  check('evaluated → 直接读报告接口', Boolean(backend.find('GET', '/interviews/1/report')));
  check('evaluated → **不接流**（不会再去拉 SSE）',
    !backend.calls.some((c) => c.path === '/interviews/1/evaluation/stream'),
    backend.calls.map((c) => c.path).join(' '));
  check('evaluated → 逐题分从报告里铺出来（3 条）', scoreItems().length === 3, `实际 ${scoreItems().length}`);
  check('evaluated → 总分与结论就位', overallScore() === '6.5' &&
    page().querySelector('.report-conclusion')?.textContent === REPORT.conclusion);
  check('evaluated → 状态行不存在（已经结束了）', streamNote() === null);

  /* ---------- 15. 状态说已评估、报告却读不到 ---------- */
  reset('evaluated');
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /interviews/:id/report': () => ({ status: 409, body: { code: 'BUSINESS_ERROR', message: '评估尚未完成', detail: null } }),
  });
  await go('#/interviews/1/evaluation');
  await waitFor(() => page().textContent.includes('报告读取失败'));
  check('报告读不到 → 如实说，不假装有报告', page().textContent.includes('报告读取失败'),
    page().textContent.slice(0, 80));
  check('报告读不到 → 展示后端 message', page().textContent.includes('评估尚未完成'));

  /* ---------- 16. 导出 DOCX ---------- */
  reset('evaluated');
  backend.setHandlers(defaultHandlers());
  backend.reset(defaultHandlers());
  await go('#/interviews/1/evaluation');
  await waitFor(() => buttonIn(page(), '导出 DOCX') !== undefined);
  buttonIn(page(), '导出 DOCX').click();
  await waitFor(() => toasts().some((t) => t.includes('已导出')));
  check('导出 DOCX → 请求带 ?format=docx',
    backend.find('GET', '/interviews/1/report/export')?.query === 'format=docx',
    String(backend.find('GET', '/interviews/1/report/export')?.query));
  check('导出 DOCX → 文件名取的是 RFC 5987 的中文名',
    toasts().some((t) => t.includes('张三-面试报告.docx')), toasts().join(' | '));
  check('导出 DOCX → 按钮恢复可用', buttonIn(page(), '导出 DOCX').disabled === false);

  /* ---------- 17. 导出 DOCX 失败：提示可改用 PDF ---------- */
  clearToasts();
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /interviews/:id/report/export': () => ({
      status: 500, body: { code: 'INTERNAL_ERROR', message: '服务器内部错误', detail: null },
    }),
  });
  buttonIn(page(), '导出 DOCX').click();
  await waitFor(() => toasts().some((t) => t.includes('服务器内部错误')));
  check('DOCX 失败 → 原样展示后端文案', toasts().some((t) => t.includes('服务器内部错误')), toasts().join(' | '));
  check('DOCX 失败 → 指明可以改用「导出 PDF」（PRD §7）',
    toasts().some((t) => t.includes('可改用「导出 PDF」')), toasts().join(' | '));

  /* ---------- 18. 导出 PDF 走浏览器打印 ---------- */
  backend.setHandlers(defaultHandlers());
  const before = PRINTED;
  buttonIn(page(), '导出 PDF').click();
  await settle();
  check('导出 PDF → 调 window.print()（后端没有 PDF 接口）', PRINTED === before + 1, `${before} → ${PRINTED}`);

  /* ---------- 19. 重新评估：先二次确认 ---------- */
  clearToasts();
  buttonIn(page(), '重新评估').click();
  await settle();
  check('点「重新评估」→ 先二次确认（会整体覆盖当前报告）',
    openOverlay()?.textContent.includes('整体覆盖') ?? false, openOverlay()?.textContent?.slice(0, 60));
  check('确认文案提到「不可编辑，重评是唯一修改方式」',
    openOverlay()?.textContent.includes('不可编辑') ?? false);
  backend.reset();
  buttonIn(openOverlay(), '取消').click();
  await settle();
  check('取消 → 不发 evaluate', backend.calls.length === 0, `实际 ${backend.calls.length} 次`);
  await closeAnyModal();

  /* ---------- 20. 没有题目 ---------- */
  reset('completed');
  backend.setHandlers({
    ...defaultHandlers(),
    'GET /interviews/:id': () => ({ status: 200, body: { ...detail(), questions: [], question_count: 0 } }),
  });
  await go('#/interviews/1/evaluation');
  check('没有题目 → 明确说清原因，而不是显示一份空报告',
    page().textContent.includes('这场面试没有题目'), page().textContent.slice(0, 80));

  /* ---------- 21. 标签页标题（打印 PDF 用的就是它） ---------- */
  check('评估页把标签页标题改成「候选人 · 面试评估报告」',
    document.title === '张三 · 面试评估报告', document.title);
});
