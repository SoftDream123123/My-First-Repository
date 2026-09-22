/**
 * pages/evaluation.js —— 评估报告
 *
 * 两处判断：
 *
 * 1. **不切成「进度页 → 结果页」两套版式。** 流式产出时用的就是最终那份版式，
 *    分数一条条落进去 —— 看到的是报告在成形，而不是一个进度条在转。
 *    因此状态行只有一条（当前阶段 + 已评几题），不再画三段步骤条：
 *    逐题分数自己就是进度，再画一遍是把同一件事说两次。
 * 2. **维度分不做第二张表。** 雷达图的图例每行直接带该维度的评语 ——
 *    图给形状、图例给数值与理由，两者是同一件事的两面。
 *
 * ⚠️ **事件名以 API 文档 §9.2 为准**：`question` / `dimension` / `report` /
 * `done` / `error`（另有 `: ping` 心跳注释，由 `sse.js` 静默丢弃）。
 * 原型 `standalone.html` 里的 mock 用的是 `stage` / `question_score` /
 * `dimension_score` —— 那是原型自造的，**与真实后端不一致**，
 * 照搬会让整页收不到任何一条进度。搬进 `src/` 时按接口文档改对了。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  baseTitle, contextTitle, createShell, emptyState, dimTag, formatDateTime, loadingBlock,
  panelHead, statusRail,
} from '../components/shell.js';
import { radarSvg, scoreClass, SCORE_MAX, PASS_THRESHOLD } from '../components/radar.js';
import { currentNavId, navigate } from '../router.js';

const STAGES = [
  { label: '逐题评分', text: '每一题给一个 0–10 的分数，并写清这个分数是看了什么得出的。' },
  { label: '多维评分', text: '按岗位的评估维度分别打分，画成雷达图，看出强项与短板在哪一侧。' },
  { label: '汇总报告', text: '给出总分、综合结论、优点与待改进 —— 可以直接写进评审结论。' },
];

/** 离开页面时要停掉正在读的 SSE。 */
let activeAbort = null;

// 生命周期状态必须是**模块级**，不能放 render 的局部变量：render 里要 await
// 取详情，这期间用户可能已经导航走了 —— 那一刻 router 调用的 destroy() 只看得到
// 模块级状态。若 destroyed 是局部变量，render 恢复后会以为自己是活的，照常建立
// SSE 流，而此后没有任何人能关掉它（router 的 currentPage 已换成别的页面）。
let destroyed = true;

export function destroy() {
  destroyed = true;
  if (activeAbort) { activeAbort(); activeAbort = null; }
  document.title = baseTitle();
}

function scoreSpan(className, value) {
  const known = typeof value === 'number';
  return el('span', {
    class: `${className}${known ? ` ${scoreClass(value)}` : ''}`,
    text: known ? value.toFixed(1) : '—',
  });
}

/**
 * 右栏：3 维及以上画雷达；1–2 维围不成面积，改画横条 —— 别硬凑一个三角形。
 *
 * 1–2 维时**必须写明为什么没有雷达图**：不给一句话的话，读者只会看到一个
 * 与报告其余部分长相不同的东西，不知道是「维度少」还是「图挂了」。
 */
function buildChartCell(dims, scores, notes) {
  if (!dims.length) {
    return el('div', { class: 'report-head-side' },
      el('p', { class: 'hint', text: '该岗位没有定义评估维度。' }));
  }

  if (dims.length < 3) {
    return el('div', { class: 'report-head-side' },
      el('p', { class: 'hint', text: '维度不足 3 个，无法绘制雷达图 —— 按维度列出得分。' }),
      el('div', { class: 'dim-bars' }, dims.map((dim) => {
        const value = scores[dim];
        return el('div', {},
          el('div', { class: 'dim-bar-top' },
            el('span', { class: 'dim-legend-name', text: dim }),
            scoreSpan('dim-legend-score', value)),
          el('div', { class: 'dim-bar-track' },
            el('div', {
              class: `dim-bar-fill${typeof value === 'number' ? ` ${scoreClass(value)}` : ''}`,
              style: `width:${typeof value === 'number' ? (value / SCORE_MAX) * 100 : 0}%`,
            })),
          notes[dim] ? el('div', { class: 'dim-legend-comment', text: notes[dim] }) : null);
      })));
  }

  return el('div', { class: 'report-head-side' }, radarSvg(dims, scores));
}

/**
 * 维度图例横跨面板底部：每个维度给「名称 + 分数 + 一句为什么」。
 * 维度不足 3 个时横条自己已经带了评语，这里就不再重复一遍。
 */
function buildLegendRow(dims, scores, notes) {
  if (dims.length < 3) return null;
  return el('div', { class: 'dim-legend' }, dims.map((dim) => el('div', { class: 'dim-legend-row' },
    el('div', { class: 'dim-legend-top' },
      el('span', { class: 'dim-legend-name', text: dim }),
      scoreSpan('dim-legend-score', scores[dim])),
    notes[dim] ? el('div', { class: 'dim-legend-comment', text: notes[dim] }) : null)));
}

function findSection(title, items, band, emptyText) {
  return el('section', {},
    el('h3', { class: 'panel-title', text: title }),
    items.length
      ? el('div', { class: 'find-list', style: 'margin-top:var(--s3)' },
          items.map((text) => el('p', { class: `find-item ${band}`, text })))
      : el('p', { class: 'hint', style: 'margin-top:var(--s3)', text: emptyText }));
}

/** 优点与待改进：这两条是直接能抄进评审结论的话，因此紧跟在综合结论下面。 */
function findingsBlock(report) {
  return el('div', { class: 'report-finds' },
    findSection('优点', report.strengths, 'is-pass', '本次评估没有提炼出明显优势。'),
    findSection('待改进', report.weaknesses, 'is-watch', '本次评估没有发现突出的短板。'));
}

export async function render(container, params) {
  const navId = currentNavId();
  destroyed = false;
  // 「我这一轮还算数吗」—— 中途导航走（router 的换页序号会变）或本页的流被
  // destroy 掉，都算不算数。每个 await 之后都要过这一关，否则会把内容画进已
  // 卸载的 DOM，或留下一条没人关得掉的 SSE 流。
  const superseded = () => destroyed || currentNavId() !== navId;

  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('面试', '评估报告'));
  mount(container, root);
  mount(main, loadingBlock('正在加载面试…'));

  let detail;
  try {
    detail = await api.get(`/interviews/${interviewId}`);
  } catch (error) {
    if (superseded()) return;
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '返回列表', onClick: () => navigate('/interviews') }))));
    return;
  }
  if (superseded()) return;

  // PDF 导出走浏览器打印，文件名取的就是这个标题
  document.title = `${detail.candidate_name} · 面试评估报告`;

  const dims = detail.evaluation_dimensions || [];
  const questions = detail.questions || [];
  const backToDetail = el('button', {
    class: 'btn btn--ghost', text: '返回详情', onClick: () => navigate(`/interviews/${interviewId}`),
  });

  function simplePage(title, text, extra) {
    mount(main,
      el('div', { class: 'page-head' },
        el('div', {},
          el('h1', { text: detail.candidate_name }),
          el('p', { class: 'page-lede', text: detail.position_name })),
        el('div', { class: 'page-head-actions' }, backToDetail)),
      statusRail(detail.status),
      el('div', { class: 'panel', style: 'margin-top:var(--s5)' },
        panelHead(title),
        el('div', { class: 'panel-body' }, el('p', { class: 'prose', text }), extra || null)));
  }

  if (detail.status === 'draft' || detail.status === 'ongoing') {
    simplePage('还不能评估',
      '评估读的是已经记录下来的回答。请先把面试标记为完成，再回到这里开始评估。');
    return;
  }

  if (!questions.length) {
    simplePage('这场面试没有题目',
      '题目在创建面试时生成。如果这里为空，说明出题那一步没有落库。');
    return;
  }

  if (detail.status === 'completed') {
    const missing = questions.filter((q) => !String(q.answer ?? '').trim()).length;
    const start = el('button', { class: 'btn btn--primary', text: '开始评估' });
    start.addEventListener('click', async () => {
      // 同步请求，真正的产出在接下来的 SSE 流里；提交期间锁住按钮防连点
      start.disabled = true;
      start.textContent = '正在提交…';
      try {
        await api.post(`/interviews/${interviewId}/evaluate`);
        if (superseded()) return;
        render(container, params); // 状态已变为「评估中」，重载后自动接流
      } catch (error) {
        toast.error(error.message);
        start.disabled = false;
        start.textContent = '开始评估';
      }
    });

    simplePage('尚未评估',
      '回答已经记录完，可以开始评估。评估会逐题给分、按维度综合，最后汇总成一份报告。',
      el('div', {},
        missing
          ? el('p', { class: 'note-box', style: 'margin-top:var(--s4)',
              text: `本场有 ${missing} 道题没有记录回答，评估时按 0 分计入。` })
          : null,
        el('ol', { class: 'stage-list' }, STAGES.map((stage, index) => el('li', {},
          el('span', { class: 'stage-list-index', text: String(index + 1) }),
          el('div', {},
            el('p', { class: 'stage-list-label', text: stage.label }),
            el('p', { class: 'stage-list-text', text: stage.text }))))),
        el('div', { class: 'editor-actions' }, start)));
    return;
  }

  /* ---------------------- 评估中 / 已评估 ---------------------- */

  const view = {
    status: detail.status,
    done: detail.status === 'evaluated',
    restarting: false,
    failed: null,
    total: questions.length,
    scoreMap: {},  // interview_question_id → { score, comment, ... }
    dimMap: {},    // dimension → { score, comment }
    report: null,
    lastArrived: null,
  };

  const headRegion = el('div', { class: 'panel' });
  const scoresRegion = el('div', { class: 'panel' });
  const actionsRegion = el('div', { class: 'page-head-actions' });
  // 状态轨要能重画：收到 done 之后状态已经变成「已评估」，
  // 而它在挂载时是按「评估中」画好的。状态轨是回答「现在到哪了」的那一条，
  // 让它停在旧状态等于对着使用者说谎 —— 刷新一下才对得上。
  const railRegion = el('div', {});

  function repaintRail() {
    clear(railRegion);
    railRegion.append(statusRail(view.status));
  }

  mount(main,
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', { text: detail.candidate_name }),
        el('p', { class: 'page-lede' },
          detail.candidate_contact
            ? `${detail.position_name} · ${detail.candidate_contact}`
            : detail.position_name),
        el('p', { class: 'meta' },
          detail.completed_at
            ? `创建于 ${formatDateTime(detail.created_at)}，完成于 ${formatDateTime(detail.completed_at)}`
            : `创建于 ${formatDateTime(detail.created_at)}`)),
      actionsRegion),
    railRegion,
    el('div', { style: 'margin-top:var(--s5)' }, headRegion, scoresRegion));

  const dimScores = () => Object.fromEntries(
    dims.filter((dim) => view.dimMap[dim]).map((dim) => [dim, view.dimMap[dim].score]));
  const dimNotes = () => Object.fromEntries(
    dims.filter((dim) => view.dimMap[dim]).map((dim) => [dim, view.dimMap[dim].comment]));

  /**
   * 当前阶段由**已经到的东西**推出来，不依赖服务端另发一个 stage 事件。
   * 顺序是接口保证的：question×N → dimension×M → report → done。
   */
  function currentStage() {
    if (view.report) return 'report';
    if (Object.keys(view.dimMap).length) return 'dimension';
    return 'question';
  }

  function streamNote() {
    if (view.failed) {
      return el('div', { class: 'stream-note is-failed' },
        el('span', { text: view.failed.message }),
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '重新加载', // 状态可能已经变了，重新拉一次比在这里猜更可靠
          onClick: () => render(container, params),
        }));
    }
    if (view.done) return null;

    const stage = currentStage();
    const text = stage === 'dimension' ? '正在生成多维评分…'
      : stage === 'report' ? '正在汇总报告…'
      : '正在逐题评分…';
    return el('div', { class: 'stream-note' },
      el('span', { class: 'stream-dot' }),
      el('span', { text }),
      // 计数只在逐题阶段有意义 —— 那时的分数自己就是进度
      stage === 'question'
        ? el('span', { class: 'stream-count',
            text: `${Object.keys(view.scoreMap).length} / ${view.total}` })
        : null);
  }

  function repaintHead() {
    const report = view.report;
    // 用 mount 而不是原生 append：原生 append 会把 streamNote() 的 null 变成字符串 "null"
    mount(headRegion,
      streamNote(),
      el('div', { class: 'report-head' },
        el('div', { class: 'report-head-main' },
          el('div', { class: 'report-score' },
            // 还没汇出总分时留一个小字占位，别先填一个 0 —— 0 分和「还没算出来」是两件事
            report
              ? el('span', {
                  class: `report-score-value ${scoreClass(report.overall_score)}`,
                  text: report.overall_score.toFixed(1),
                })
              : el('span', { class: 'report-score-pending', text: '待出分' }),
            report ? el('span', { class: 'report-score-unit', text: `/ ${SCORE_MAX}` }) : null),
          el('p', { class: 'report-score-scale', text: `满分 ${SCORE_MAX} 分，${PASS_THRESHOLD} 分及以上为达标` }),
          el('p', { class: 'report-conclusion', text: report
            ? report.conclusion
            : '综合结论在评估完成后给出，它由逐题评分与多维评分汇总而来。' }),
          report ? findingsBlock(report) : null),
        buildChartCell(dims, dimScores(), dimNotes())),
      buildLegendRow(dims, dimScores(), dimNotes()));
  }

  function repaintScores() {
    const arrived = questions.filter((q) => view.scoreMap[q.interview_question_id]);
    clear(scoresRegion);
    scoresRegion.append(
      panelHead('逐题评分', arrived.length ? `${arrived.length} / ${questions.length} 题` : null),
      arrived.length
        ? el('div', {}, arrived.map((question) => {
            const row = view.scoreMap[question.interview_question_id];
            const answer = String(question.answer ?? '').trim();
            return el('div', {
              class: `score-item${question.interview_question_id === view.lastArrived ? ' just-arrived' : ''}`,
            },
              el('div', { class: 'score-item-head' },
                el('span', { class: 'score-seq', text: String(question.seq) }),
                dimTag(question.dimension),
                scoreSpan('score-value', row.score)),
              el('p', { class: 'score-question', text: question.content }),
              el('div', { class: 'score-block' },
                el('div', { class: 'dossier-label', text: '候选人回答' }),
                el('p', { class: `answer-quote${answer ? '' : ' is-blank'}`, text: answer || '本题未作答' })),
              el('div', { class: 'score-block' },
                el('div', { class: 'dossier-label', text: '评估意见' }),
                el('p', { class: 'score-comment', text: row.comment })));
          }))
        : el('div', { class: 'panel-body' },
            el('p', { class: 'hint', text: '评估会逐题产出分数与评语，它们会依次出现在这里。' })));
  }

  function repaintActions() {
    clear(actionsRegion);
    actionsRegion.append(backToDetail);
    if (view.status !== 'evaluated') return;

    actionsRegion.append(
      el('button', {
        class: 'btn btn--quiet',
        text: '重新评估',
        onClick: async () => {
          const ok = await confirmModal({
            title: '重新评估这场面试？',
            message: '新报告会整体覆盖当前这一份 —— 逐题评分、多维评分与结论都不会保留。评估本身不可编辑，重评是唯一的修改方式。',
            confirmLabel: '重新评估',
            danger: false,
          });
          if (!ok) return;
          try {
            await api.post(`/interviews/${interviewId}/evaluate`);
            if (superseded()) return;
            render(container, params);
          } catch (error) {
            toast.error(error.message);
          }
        },
      }),
      el('button', {
        class: 'btn btn--ghost',
        text: '导出 DOCX',
        title: '由后端用 python-docx 生成，含基本信息与两张评分表（不含雷达图）',
        onClick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          button.textContent = '正在生成…';
          try {
            const name = await api.download(
              `/interviews/${interviewId}/report/export?format=docx`,
              `面试报告_${detail.candidate_name}.docx`,
            );
            toast.success(`已导出 ${name}`);
          } catch (error) {
            // PRD §7：DOCX 失败时提示可改用浏览器打印那条路径
            toast.error(`${error.message}（可改用「导出 PDF」）`);
          } finally {
            button.disabled = false;
            button.textContent = '导出 DOCX';
          }
        },
      }),
      el('button', {
        class: 'btn btn--primary',
        text: '导出 PDF',
        title: '走浏览器打印，雷达图所见即所得',
        onClick: () => window.print(),
      }));
  }

  function repaint() {
    repaintRail();
    repaintActions();
    repaintHead();
    repaintScores();
  }

  let controller = null;
  activeAbort = () => { destroyed = true; if (controller) controller.abort(); };

  async function attachStream() {
    if (destroyed) return;
    controller = new AbortController();
    try {
      await api.stream(`/interviews/${interviewId}/evaluation/stream`, {
        signal: controller.signal,
        onEvent: ({ name, data }) => {
          if (destroyed || view.restarting) return;

          if (name === 'error') {
            // 评估失败：后端已把状态回退到「已完成」，重新加载就能回到「开始评估」
            view.restarting = true;
            toast.error(data.message);
            controller.abort();
            render(container, params);
            return;
          }

          if (name === 'question') {
            // ⚠️ **按 id 覆盖，不是追加**：重连时服务端会从头重放（API 文档 §9.2），
            // 追加会让进度与逐题行都翻倍。
            view.scoreMap[data.interview_question_id] = data;
            view.lastArrived = data.interview_question_id;
            if (typeof data.total === 'number') view.total = data.total;
            repaintScores();
          } else if (name === 'dimension') {
            view.dimMap[data.dimension] = data;
          } else if (name === 'report') {
            view.report = data; // 结论、优点与待改进都随 repaintHead 一起落进头版
          } else if (name === 'done') {
            view.done = true;
            view.status = 'evaluated';
            repaint();       // 状态轨与动作都要跟着换，不只是动作
            return;
          }
          repaintHead();
        },
      });
    } catch (error) {
      if (destroyed || view.restarting || error?.name === 'AbortError') return;
      view.failed = { message: error.message };
      repaintHead();
      return;
    }

    // 流自然结束却没收到 done：连接断了。任务可能还在后台跑，
    // 因此不说「失败」，只请人重新加载 —— 重新加载会接上同一条任务
    if (!destroyed && !view.restarting && !view.done) {
      view.failed = { message: '评估流已断开。评估任务可能仍在后台继续，重新加载即可接上进度。' };
      repaintHead();
    }
  }

  repaint();

  if (detail.status === 'evaluated') {
    try {
      const report = await api.get(`/interviews/${interviewId}/report`);
      if (superseded()) return;
      view.report = report;
      view.done = true;
      for (const item of report.question_scores) view.scoreMap[item.interview_question_id] = item;
      for (const item of report.dimension_scores) view.dimMap[item.dimension] = item;
      repaint();
    } catch (error) {
      if (superseded()) return;
      // 状态说已评估、报告却读不到：如实说，不假装有报告
      clear(headRegion);
      headRegion.append(
        emptyState('报告读取失败', error.message,
          el('button', { class: 'btn btn--primary', text: '重新加载', onClick: () => render(container, params) })),
      );
    }
  } else {
    attachStream();
  }
}
