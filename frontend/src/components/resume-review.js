/**
 * components/resume-review.js —— 简历与岗位的 AI 匹配度评估（PRD §4.15）
 *
 * **两端共用**：HR 在面试详情页、候选人在「我的简历」页。两边的结果结构完全相同
 * （分数 + 结论 + 亮点 + 差距），差异只有「分数可能为 null」这一点。
 *
 * 共用一份实现是为了让「分数为 null 时**整块不渲染**」这条规则只有一处 ——
 * 否则候选人侧那条容易在 HR 侧的复制粘贴里丢掉，而那正是脱敏失效的方式。
 *
 * ⚠️ 结果**不落库、每次点都真算一次**（PRD §4.15），因此这里既不缓存，
 * 也不在弹窗里给「重试」——重试的入口收敛到页面上那一颗按钮。
 */

import { clear, el } from '../dom.js';
import * as api from '../api.js';
import { openModal } from './modal.js';
import { loadingBlock } from './shell.js';

/**
 * 分数档位 → 文案与样式类。
 *
 * ⚠️ **与后端结论档位保持一致**（module-27 §4.2 的档位表；边界 6.5 与后端
 * `PASS_THRESHOLD` 同值），改一处必须改另一处。
 *
 * ⚠️ 档位文案只说「重合度」，**不得**出现「通过 / 推荐 / 淘汰 / 进入下一轮」
 * 这类去留判断：后端已经守住了结论文案，前端不要又贴一个判断标签把它破掉。
 */
export function scoreBand(score) {
  if (score == null) return { label: '', tone: '' };
  if (score >= 8) return { label: '重合度高', tone: 'is-high' };
  if (score >= 6.5) return { label: '重合度较好', tone: 'is-mid' };
  if (score >= 4) return { label: '部分重合', tone: 'is-low' };
  return { label: '重合较少', tone: 'is-weak' };
}

const ENDPOINTS = {
  hr: (interviewId) => `/interviews/${interviewId}/resume-review`,
  candidate: (interviewId) => `/candidate/interviews/${interviewId}/resume-review`,
};

function section(title, content) {
  return el('div', { class: 'review-section' },
    el('div', { class: 'dossier-label', text: title }), content);
}

function bulletList(items, fallback) {
  if (!items.length) return el('p', { class: 'meta', text: fallback });
  return el('ul', { class: 'review-list' }, items.map((text) => el('li', { text })));
}

function renderReview(result) {
  const band = scoreBand(result.match_score);

  return el('div', { class: 'review' },
    // 分数为 null（候选人 `summary` 档）时**整块不渲染**：显示 `0`、`—` 或
    // 「暂无」都会让人以为「我得了零分」或「系统坏了」。脱敏的正确表现是
    // 「这件事不存在」——因此这里刻意不输出任何占位节点。
    result.match_score == null ? null : el('div', { class: `review-score ${band.tone}` },
      el('span', { class: 'review-score-value', text: String(result.match_score) }),
      el('span', { class: 'review-score-label', text: band.label })),

    section('综合结论', el('p', { class: 'prose', text: result.conclusion })),
    section('亮点', bulletList(result.strengths, '（无）')),
    // 后端允许 gaps 为空（「没什么明显差距」是正当结论）；空白区块看起来像渲染
    // 失败，因此给它一句固定文案
    section('差距', bulletList(result.gaps, '未发现明显差距')),
  );
}

/**
 * 打开评估弹窗。
 *
 * `side` 由调用方显式传入（`'hr'` / `'candidate'`），不让组件去猜 —— 两端的
 * 登录态按 key 分开存储，猜需要读 session，而组件不该依赖 session 的形状。
 *
 * `button` 是页面上的那颗触发按钮，由本函数负责它的忙态：评估每次都真调一次 AI，
 * 连点几下就是几次调用，必须挡住。忙态放在这里而不是各调用点，是为了让「怎么
 * 复位」只有一处实现（`finally`，弹窗中途被关掉也不会卡在「评估中…」）。
 *
 * 先开弹窗再发请求：评估要调 AI，可能数秒；先立起弹窗放 loading 才能让人看到
 * 「正在跑」，否则按钮转几秒像卡死。失败信息也留在弹窗里（用户刚点的是这个
 * 按钮，用 toast 会让「弹窗是空的 + 角落一句话」同时出现）。
 */
export function openResumeReview({ interviewId, side, button }) {
  const body = el('div', {});
  const handle = openModal({
    title: '简历与岗位匹配度',
    body,
    footer: el('button', { class: 'btn btn--ghost', text: '关闭', onClick: () => handle.close() }),
  });

  body.append(loadingBlock('AI 正在评估简历与岗位的匹配度…'));

  const label = button ? button.textContent : '';
  if (button) {
    button.disabled = true;
    button.textContent = '评估中…';
  }

  (async () => {
    try {
      const result = await api.post(ENDPOINTS[side](interviewId));
      clear(body);
      body.append(renderReview(result));
    } catch (error) {
      // 后端文案原样展示（含 409 / 502 / 403）
      clear(body);
      body.append(el('p', { class: 'field-error', text: error.message }));
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = label;
      }
    }
  })();

  return handle;
}
