/**
 * 评估页（module-07 §5.4）—— 最复杂的一屏。
 *
 * 页面不区分「开始评估」与「查看报告」两个入口：一律先建立 SSE，
 * 由服务端决定是重放进行中的运行、从库合成历史，还是推 error。
 * 这样避免了前端与后端各判一套状态而产生的分歧。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { sseConnect } from '../sse.js';
import { toast } from '../components/toast.js';
import { drawRadar } from '../components/radar.js';
import {
  contextTitle,
  createShell,
  dimTag,
  emptyState,
  formatDateTime,
  loadingBlock,
  navigate,
  scoreClass,
  statusRail,
} from '../components/shell.js';

let connection = null;

/** 路由在离开页面前会调用它 —— 不清理会导致连接泄漏。 */
export function destroy() {
  if (connection) {
    connection.close();
    connection = null;
  }
}

export async function render(container, params) {
  destroy(); // 防御：重复进入时先关掉旧连接

  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('评估'));
  mount(container, root);
  mount(main, loadingBlock('正在连接评估服务…'));

  let detail;
  try {
    detail = await api.get(`/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('加载失败', error.message)));
    return;
  }

  // 未完成的面试本来就不可评估 —— 直接给出方向，而不是让它推到 error
  if (detail.status === 'ongoing' || detail.status === 'draft') {
    mount(
      main,
      el('div', { class: 'page-head' }, el('div', {}, el('h1', { class: 'h-page', text: '评估' }))),
      statusRail(detail.status),
      el(
        'div',
        { class: 'panel' },
        emptyState(
          '这场面试还没有完成',
          '先把面试标记为完成，才能开始评估。',
          el('button', {
            class: 'btn btn--primary',
            text: '回到面试详情',
            onClick: () => navigate(`/interviews/${interviewId}`),
          }),
        ),
      ),
    );
    return;
  }

  /* ------------------------------ 状态 ------------------------------ */

  const state = {
    phase: 'connecting',
    questions: [],
    dimensions: [],
    report: null,
    questionScores: [],
    errorMessage: '',
    total: detail.question_count,
    // 默认取文档约定的固定路径；触发评估后以服务端返回的 stream_url 为准
    streamUrl: `/api/interviews/${interviewId}/evaluation/stream`,
  };

  /**
   * 清掉已累积的流数据。
   *
   * 服务端在重连时会**从头重放**全部事件（API 文档 §9.2），所以重连前必须把
   * 上一轮收到的逐题 / 维度 / 报告清空 —— 否则重放的事件会被再 push 一遍：
   * 逐题行翻倍、进度显示 16/8。触发评估（retry）与重新连接两条路都要过这里。
   */
  function resetStreamState() {
    state.questions = [];
    state.dimensions = [];
    state.report = null;
    state.questionScores = [];
    state.errorMessage = '';
  }

  /* ------------------------------ 容器 ------------------------------ */

  const noticeSlot = el('div', {});
  const progressSlot = el('div', {});
  const reportSlot = el('div', {});

  function paintHeader() {
    const stage = state.phase === 'done' ? 'evaluated' : detail.status;

    return [
      el(
        'div',
        { class: 'page-head' },
        el(
          'div',
          {},
          el('h1', { class: 'h-page', text: detail.candidate_name }),
          el('p', { class: 'page-lede', text: `${detail.position_name} 的评估报告` }),
        ),
        el(
          'div',
          { class: 'page-head-actions' },
          el('button', {
            class: 'btn btn--ghost',
            text: '面试详情',
            onClick: () => navigate(`/interviews/${interviewId}`),
          }),
          el('button', {
            class: 'btn btn--ghost',
            text: '返回列表',
            onClick: () => navigate('/interviews'),
          }),
        ),
      ),
      // 状态由状态轨表达，不再另加状态标签
      statusRail(stage),
    ];
  }

  /* ---------------------------- 进度区 ---------------------------- */

  function paintProgress() {
    clear(progressSlot);
    if (state.phase === 'done') return;

    const arrived = state.questions.length;
    const percent = state.total ? Math.round((arrived / state.total) * 100) : 0;

    progressSlot.append(
      el(
        'div',
        { class: 'eval-progress' },
        el('span', { class: 'eval-progress-text', text: '逐题评分' }),
        el('div', { class: 'progress' }, el('div', { class: 'progress-fill', style: `width:${percent}%` })),
        el('span', { class: 'eval-progress-text', text: `${arrived} / ${state.total}` }),
      ),
    );

    // 雷达图逐维度「生长」（module-07 §5.4）：每收到一个 dimension 事件就重绘一次，
    // 还没到达的维度按 0 处理并灰显 —— drawRadar 的 revealed 正是为此准备的。
    const radarBox = el('div', { class: 'report-radar' });
    appendRadar(radarBox, streamingAxes(), { revealed: state.dimensions.length });
    progressSlot.append(el('div', { class: 'panel', style: 'margin-bottom:24px' }, radarBox));

    if (state.questions.length) {
      progressSlot.append(
        el(
          'div',
          { class: 'panel', style: 'margin-bottom:24px' },
          el('div', { class: 'panel-body' }, buildLiveList()),
        ),
      );
    }
  }

  /**
   * 评估进行中的雷达轴：轴固定是岗位的评估维度，分数取已到达的那几个。
   * 用维度名对齐而不是按到达顺序 —— 服务端的事件顺序不该成为前端的隐含依赖。
   */
  function streamingAxes() {
    const arrived = new Map(state.dimensions.map((item) => [item.dimension, item.score]));
    return detail.evaluation_dimensions.map((dimension) => ({
      dimension,
      score: arrived.get(dimension) ?? 0,
    }));
  }

  /** 维度不足 3 个画不出多边形 —— 给降级文案（module-07 §4.4）。 */
  function appendRadar(slot, axes, options) {
    if (axes.length < 3) {
      slot.append(el('p', { class: 'hint', text: '维度不足 3 个，无法绘制雷达图。' }));
      return;
    }

    const canvas = el('canvas', { 'aria-label': '各维度得分雷达图' });
    slot.append(canvas);
    drawRadar(canvas, axes, options);
  }

  function buildLiveList() {
    return el(
      'div',
      { class: 'live-list' },
      state.questions.map((q) =>
        el(
          'div',
          { class: 'live-row' },
          el('span', { class: 'qscore-seq', text: String(q.seq).padStart(2, '0') }),
          el('span', { class: 'qscore-content', text: q.dimension }),
          el('span', {
            class: `score score--cell ${scoreClass(q.score)}`,
            text: q.score.toFixed(1),
          }),
          el('span', { class: 'live-comment', text: q.comment }),
        ),
      ),
    );
  }

  /* ---------------------------- 报告区 ---------------------------- */

  function paintReport() {
    // 先清空再判断：重新评估时 phase 回到 connecting，上一份报告必须让位给进度区，
    // 否则旧报告会和新进度条同时留在屏幕上（paintProgress 就是这么做的）
    clear(reportSlot);
    if (state.phase !== 'done') return;

    const report = state.report;
    const dimensions = state.dimensions.length
      ? state.dimensions
      : detail.evaluation_dimensions.map((dimension) => ({ dimension, score: 0, comment: '' }));

    const radarSlot = el('div', { class: 'report-radar' });

    // 英雄区：总分 + 雷达并置。分数用衬线，颜色编码通过与否。
    const hero = el(
      'div',
      { class: 'panel' },
      el(
        'div',
        { class: 'report-hero' },
        el(
          'div',
          { class: 'report-verdict' },
          el(
            'div',
            { class: 'report-score-row' },
            el('span', {
              class: `score score--hero ${scoreClass(report.overall_score)}`,
              text: report.overall_score.toFixed(1),
            }),
            el('span', { class: 'report-score-unit', text: '总分 / 10' }),
          ),
          el('p', { class: 'report-conclusion', text: report.conclusion }),
          el('p', {
            class: 'meta',
            style: 'margin-top:16px',
            text: `评估于 ${formatDateTime(report.evaluated_at)}`,
          }),
        ),
        radarSlot,
      ),
    );

    const dimensionPanel = el(
      'div',
      { class: 'panel' },
      el('div', { class: 'panel-head' }, el('h2', { class: 'h-sub', text: '维度得分' })),
      el(
        'div',
        { class: 'panel-body' },
        dimensions.map((item) =>
          el(
            'div',
            {},
            el(
              'div',
              { class: 'dim-row' },
              el('span', { class: 'dim-name', text: item.dimension }),
              el(
                'div',
                { class: 'dim-track' },
                el('div', {
                  class: `dim-fill ${scoreClass(item.score)}`,
                  style: `width:${item.score * 10}%`,
                }),
              ),
              el('span', {
                class: `score score--md ${scoreClass(item.score)}`,
                text: item.score.toFixed(1),
              }),
            ),
            item.comment ? el('p', { class: 'dim-comment', text: item.comment }) : null,
          ),
        ),
      ),
    );

    const findingsPanel = el(
      'div',
      { class: 'panel' },
      el(
        'div',
        { class: 'panel-body' },
        el(
          'div',
          { class: 'findings' },
          el(
            'div',
            {},
            el('h3', { class: 'findings-title is-pass', text: '优势' }),
            el(
              'ul',
              { class: 'findings-list findings-list--pass' },
              report.strengths.map((text) => el('li', { text })),
            ),
          ),
          el(
            'div',
            {},
            el('h3', { class: 'findings-title is-watch', text: '待改进' }),
            el(
              'ul',
              { class: 'findings-list findings-list--watch' },
              report.weaknesses.map((text) => el('li', { text })),
            ),
          ),
        ),
      ),
    );

    const detailPanel = el(
      'div',
      { class: 'panel' },
      el(
        'div',
        { class: 'panel-head' },
        el('h2', { class: 'h-sub', text: '逐题明细' }),
        el('span', { class: 'meta', style: 'margin-left:auto', text: `${detail.question_count} 题` }),
      ),
      el('div', { class: 'panel-body panel-body--tight' }, buildQuestionScores()),
    );

    reportSlot.append(hero, dimensionPanel, findingsPanel, detailPanel);

    // 画布要等元素进 DOM 才量得到尺寸
    appendRadar(radarSlot, dimensions);
  }

  function buildQuestionScores() {
    const scores = state.questionScores || [];
    if (!scores.length) {
      return el('div', { class: 'panel-body' }, el('p', { class: 'hint', text: '暂无逐题明细。' }));
    }

    return el(
      'div',
      {},
      scores.map((item) => {
        const body = el('div', { class: 'qscore-body', hidden: true });
        let expanded = false;

        const head = el(
          'button',
          {
            class: 'qscore-head',
            'aria-expanded': 'false',
            onClick: () => {
              expanded = !expanded;
              body.hidden = !expanded;
              head.setAttribute('aria-expanded', String(expanded));
            },
          },
          el('span', { class: 'qscore-seq', text: String(item.seq).padStart(2, '0') }),
          el('span', { class: 'qscore-content', text: item.content }),
          el('span', {
            class: `score score--cell ${scoreClass(item.score)}`,
            text: item.score.toFixed(1),
          }),
        );

        body.append(
          el(
            'div',
            { class: 'qscore-block' },
            el('div', { class: 'qscore-label', text: '候选人回答' }),
            el('div', {
              class: 'qscore-answer',
              text: item.answer || '（未作答）',
            }),
          ),
          el(
            'div',
            { class: 'qscore-block' },
            el('div', { class: 'qscore-label', text: 'AI 评语' }),
            el('p', { text: item.comment }),
          ),
          el('div', { style: 'margin-top:12px' }, dimTag(item.dimension)),
        );

        return el('div', { class: 'qscore' }, head, body);
      }),
    );
  }

  function paintNotice() {
    clear(noticeSlot);

    if (state.phase === 'error') {
      noticeSlot.append(
        el(
          'div',
          { class: 'eval-notice eval-notice--error' },
          el(
            'div',
            { class: 'eval-notice-body' },
            el('div', { class: 'eval-notice-title', text: '评估失败' }),
            el('p', { text: state.errorMessage }),
            el('p', { class: 'hint' }, '本次评估没有写入任何结果，可以安全重试。'),
          ),
          el('button', {
            class: 'btn btn--primary',
            text: '重新评估',
            onClick: () => retry(),
          }),
        ),
      );
    }

    if (state.phase === 'disconnected') {
      noticeSlot.append(
        el(
          'div',
          { class: 'eval-notice eval-notice--warn' },
          el(
            'div',
            { class: 'eval-notice-body' },
            el('div', { class: 'eval-notice-title', text: '连接已断开' }),
            el('p', {}, '评估任务仍在后台继续。重新连接后会从头重放进度。'),
          ),
          el('button', {
            class: 'btn btn--primary',
            text: '重新连接',
            onClick: () => {
              // 服务端会从头重放，先清空 —— 否则逐题行会翻倍
              resetStreamState();
              state.phase = 'connecting';
              paintAll();
              connect();
            },
          }),
        ),
      );
    }
  }

  function paintAll() {
    clear(main);
    paintHeader().forEach((node) => main.append(node));
    main.append(noticeSlot, progressSlot, reportSlot);
    paintNotice();
    paintProgress();
    paintReport();
  }

  /* ------------------------------ 连接 ------------------------------ */

  function handleEvent(name, payload) {
    if (name === 'question') {
      state.questions.push(payload);
      state.phase = 'streaming';
      paintProgress();
      return;
    }

    if (name === 'dimension') {
      state.dimensions.push(payload);
      paintProgress(); // 让雷达图当场长出一个维度
      return;
    }

    if (name === 'report') {
      state.report = payload;
      return;
    }

    if (name === 'done') {
      state.phase = 'done';
      finish();
      return;
    }

    if (name === 'error') {
      state.phase = 'error';
      state.errorMessage = payload.message || '评估失败';
      detail.status = 'completed'; // 后端已回退
      paintAll();
    }
  }

  /**
   * done 之后**不再请求** `GET /report`（module-07 §5.4 与 §10 验收标准：
   * 「done 后不重复请求造成闪烁」）。
   *
   * 汇总数据 SSE 的 report 事件已经给了；逐题明细缺的只是题干与回答，
   * 而进入页面时的 `GET /interviews/{id}` 里就有 —— 按 interview_question_id
   * 合并即可。省掉一次往返，也省掉它带来的时序闪烁。
   */
  function finish() {
    const byId = new Map(
      detail.questions.map((question) => [question.interview_question_id, question]),
    );

    state.questionScores = state.questions.map((scored) => {
      const question = byId.get(scored.interview_question_id);
      return {
        interview_question_id: scored.interview_question_id,
        seq: scored.seq,
        content: question?.content ?? '',
        dimension: scored.dimension,
        answer: question?.answer ?? null,
        score: scored.score,
        comment: scored.comment,
      };
    });

    detail.status = 'evaluated';
    paintAll();
  }

  function connect() {
    destroy();

    const handlers = {
      onEvent: handleEvent,
      onError: () => {
        state.phase = 'disconnected';
        paintAll();
      },
      onUnauthorized: () => {
        toast.error('登录状态已失效，请重新登录');
        navigate('/login');
      },
      onClose: () => {
        if (state.phase === 'connecting') state.phase = 'streaming';
        paintProgress();
      },
    };

    connection = sseConnect(state.streamUrl, handlers);
  }

  async function retry() {
    try {
      const run = await api.post(`/interviews/${interviewId}/evaluate`);
      // 服务端是 stream_url 的权威来源（幂等时还会返回同一个地址）
      if (run?.stream_url) state.streamUrl = run.stream_url;

      state.phase = 'connecting';
      resetStreamState();
      paintAll();
      connect();
    } catch (error) {
      toast.error(error.message);
    }
  }

  /* ------------------------------ 启动 ------------------------------ */

  paintAll();
  connect();
}
