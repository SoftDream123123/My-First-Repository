/**
 * pages/candidate-feedback.js —— 面试反馈（脱敏）
 *
 * 一份**文书**，不是一块看板：宽度收在 1000px（与准备助手同一种读法），
 * 综合结论 → 优点 → 待改进，顺着读。HR 报告是「左右对照」，这里不需要对照。
 *
 * 三处刻意的克制：
 *
 * 1. **颜色跟着可见的分数走。** 候选人默认看不到任何分数，优点 / 待改进因此沿用
 *    `.find-item` 的**灰**边框，不加 `.is-pass` / `.is-watch`。配置开到 `full` 档时
 *    也只有总分上色 —— 逐题分与维度分仍然不下发，给建议条目上色等于让人去对一组
 *    看不见的数字。
 * 2. **口径与 HR 报告不同**：不带招聘方的去留判断。报告里那句「建议进入下一轮 /
 *    不建议继续推进」是 HR 的决策，该由 HR 另行沟通，不该出现在自助页面上。
 * 3. **不去别处拼凑被脱掉的字段。** `CandidateFeedbackOut` 是白名单模型
 *    （API 文档 §13.12），逐题分 / 维度分 / 雷达图**结构上不存在** ——
 *    页面也不该试图从面试详情或任何别的地方补回来。
 */

import { el, mount } from '../dom.js';
import * as api from '../api.js';
import { contextTitle, createShell, emptyState, loadingBlock } from '../components/shell.js';
import { scoreClass } from '../components/radar.js';
import { navigate } from '../router.js';

const backButton = () => el('button', {
  class: 'btn btn--ghost',
  text: '返回我的面试',
  onClick: () => navigate('/candidate/interviews'),
});

function findList(items) {
  return el('div', { class: 'find-list' },
    (items || []).map((text) => el('p', { class: 'find-item', text })));
}

function section(label, body) {
  return el('section', { class: 'dossier-section' },
    el('div', { class: 'dossier-label', text: label }),
    body);
}

export async function render(container, params) {
  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('面试反馈'));
  mount(container, root);
  mount(main, loadingBlock('正在加载反馈…'));

  // 先取面试本身：岗位名只在那边，反馈响应里没有（白名单模型）
  let detail;
  try {
    detail = await api.get(`/candidate/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('打不开这份反馈', error.message, backButton())));
    return;
  }

  let feedback;
  try {
    feedback = await api.get(`/candidate/interviews/${interviewId}/feedback`);
  } catch (error) {
    // 未评估 → 409：这是**正常状态**，不是错误，因此用空态而不是报错样式
    const notReady = error.status === 409;
    mount(main, el('div', { class: 'panel' }, notReady
      ? emptyState('反馈还没出来',
          '招聘方评估完成后才能生成反馈，过一阵再来看看。', backButton())
      : emptyState('反馈加载失败', error.message, backButton())));
    return;
  }

  // `summary` 档恒为 null，`full` 档才有数 —— 判 `typeof` 而不是真值，
  // 免得 0 分被当成「没有分数」而不显示
  const score = typeof feedback.overall_score === 'number'
    ? el('div', { class: 'feedback-total' },
        el('span', {
          class: `score-value ${scoreClass(feedback.overall_score)}`,
          text: String(feedback.overall_score),
        }),
        // 只写单位：块标题已经是「总分」，这里再写一遍就是同一句话说两次
        el('span', { class: 'feedback-total-label', text: '/ 10' }))
    : null;

  mount(main, el('div', { class: 'feedback-page' },
    el('div', { class: 'page-head' }, el('div', {},
      el('h1', { text: '面试反馈' }),
      el('p', { class: 'page-lede', text: detail.position_name }))),

    // 把「脱敏」这条规则**说出来**，而不是让它看起来像加载失败。
    // 文案必须跟着档位走 —— full 档下总分就在下面，还说「不含分数」就是自相矛盾
    el('p', { class: 'note-box' }, feedback.level === 'full'
      ? '这份反馈来自招聘方。按当前档位，它含总分、综合结论与建议 —— 逐题评价与维度明细不在候选人反馈的范围内。'
      : '这份反馈来自招聘方。按脱敏规则，它只含综合结论与建议 —— 不含分数、逐题评价与维度明细。'),

    el('div', { class: 'panel' },
      score ? section('总分', score) : null,
      section('综合结论', el('p', { class: 'feedback-lede', text: feedback.conclusion })),
      section('优点', findList(feedback.strengths)),
      section('待改进', findList(feedback.weaknesses)))));
}
