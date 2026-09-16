/**
 * 原型用的模拟数据。
 *
 * 字段与后端 §8 的响应结构一一对应，因此页面代码写的是真实契约：
 * 接上后端时只需把 api.js 的 MOCK 开关关掉，页面代码不用改。
 *
 * 内容刻意写成真实面试里会出现的样子 —— 泛泛的占位文本会让
 * 设计看起来比实际更"模板"。
 */

export const users = [
  { id: 1, username: "admin", role: "admin", is_active: true, created_at: "2026-08-02T09:14:00" },
  { id: 2, username: "li.yan", role: "hr", is_active: true, created_at: "2026-08-11T14:30:00" },
  { id: 3, username: "zhao.ming", role: "hr", is_active: true, created_at: "2026-09-01T10:05:00" },
  { id: 4, username: "chen.xi", role: "hr", is_active: false, created_at: "2026-09-05T16:42:00" },
];

export const positions = [
  {
    id: 1,
    name: "后端工程师",
    jd: "负责核心交易链路的服务设计与开发。要求熟悉 Python 或 Go，理解 MySQL 索引与事务，有高并发场景的排查经验。团队规模 8 人，直接汇报给技术负责人。",
    evaluation_dimensions: ["沟通能力", "专业能力", "逻辑思维", "文化契合"],
    created_by: 2,
    created_at: "2026-08-12T10:20:00",
  },
  {
    id: 2,
    name: "产品经理",
    jd: "负责 B 端产品的需求调研与方案设计。需要能独立完成用户访谈、撰写 PRD，并与研发和设计紧密协作推动落地。",
    evaluation_dimensions: ["需求洞察", "沟通能力", "逻辑思维"],
    created_by: 2,
    created_at: "2026-08-14T15:00:00",
  },
  {
    id: 3,
    name: "数据分析师",
    jd: "支持业务侧的数据需求，搭建指标体系与看板。要求熟练使用 SQL，具备将业务问题转化为分析框架的能力。",
    evaluation_dimensions: ["专业能力", "逻辑思维"],
    created_by: 3,
    created_at: "2026-09-02T09:40:00",
  },
];

export const questions = [
  { id: 11, position_id: 1, category: "技术", dimension: "专业能力", difficulty: "hard",
    content: "你们的订单库做过分库分表吗？分片键是怎么选的，遇到跨分片查询怎么处理？",
    tags: ["分布式", "MySQL"], source: "bank", created_by: 2, created_at: "2026-08-12T10:40:00" },
  { id: 12, position_id: 1, category: "行为", dimension: "沟通能力", difficulty: "medium",
    content: "请描述一次你需要说服同事接受不同技术方案的经历，你当时是怎么推进的？",
    tags: ["协作"], source: "bank", created_by: 2, created_at: "2026-08-12T10:42:00" },
  { id: 13, position_id: 1, category: "场景", dimension: "逻辑思维", difficulty: "hard",
    content: "线上接口 P99 从 80ms 涨到 800ms，你会按什么顺序排查？说说每一步想验证什么。",
    tags: ["排查", "性能"], source: "bank", created_by: 2, created_at: "2026-08-12T10:45:00" },
  { id: 14, position_id: 1, category: "行为", dimension: "文化契合", difficulty: "medium",
    content: "你上一份工作里，团队是怎么做技术决策的？你更适应哪种方式？",
    tags: [], source: "ai", created_by: 2, created_at: "2026-09-14T11:02:00" },
  { id: 21, position_id: 2, category: "行为", dimension: "需求洞察", difficulty: "medium",
    content: "讲一个你做过用户访谈后，推翻了原本需求假设的例子。",
    tags: ["用户研究"], source: "bank", created_by: 2, created_at: "2026-08-14T15:10:00" },
];

/** 面试列表。字段对齐 §4.2 的列表项结构。 */
export const interviews = [
  {
    id: 101, position_id: 1, position_name: "后端工程师",
    candidate_name: "张书宁", candidate_contact: "zhangsn@example.com",
    status: "evaluated", created_at: "2026-09-14T14:00:00", completed_at: "2026-09-14T15:20:00",
    question_count: 8, answered_count: 8,
  },
  {
    id: 102, position_id: 1, position_name: "后端工程师",
    candidate_name: "李昀", candidate_contact: "liyun@example.com",
    status: "ongoing", created_at: "2026-09-16T10:30:00", completed_at: null,
    question_count: 8, answered_count: 3,
  },
  {
    id: 103, position_id: 2, position_name: "产品经理",
    candidate_name: "王一鸣", candidate_contact: null,
    status: "completed", created_at: "2026-09-15T09:00:00", completed_at: "2026-09-15T10:05:00",
    question_count: 8, answered_count: 7,
  },
  {
    id: 104, position_id: 3, position_name: "数据分析师",
    candidate_name: "陈嘉", candidate_contact: "chenjia@example.com",
    status: "evaluating", created_at: "2026-09-16T11:10:00", completed_at: "2026-09-16T11:55:00",
    question_count: 8, answered_count: 8,
  },
];

/**
 * 面试详情：题目 + 回答。
 * content 取自 content_snapshot，dimension 取自 dimension_snapshot
 * —— 与后端 §5.5 的供给契约一致。
 */
export const interviewQuestions = {
  101: [
    { interview_question_id: 9001, seq: 1, dimension: "沟通能力", source: "bank",
      content: "请描述一次你需要说服同事接受不同技术方案的经历，你当时是怎么推进的？",
      answer: "去年我们做订单服务重构，我主张先做限流再改数据模型，另一位同事认为应该一次性重写。我没有直接争论方案，而是先拉了他一起看线上近三个月的故障工单，发现 60% 的问题集中在流量突增场景。基于这个事实我们先把限流做了，两周后故障率降了一半，他也认可了分步走的思路。",
      recorded_at: "2026-09-14T14:18:00" },
    { interview_question_id: 9002, seq: 2, dimension: "专业能力", source: "bank",
      content: "你们的订单库做过分库分表吗？分片键是怎么选的，遇到跨分片查询怎么处理？",
      answer: "做过，按 user_id 分 16 库 64 表。选 user_id 是因为绝大多数查询都带用户维度。跨分片的场景主要是商家侧的订单列表，我们的做法是额外写一份按 merchant_id 分片的异构索引表，用 binlog 同步，查询走索引表拿到 order_id 再回主库查详情。代价是有秒级延迟，对账类需求可以接受。",
      recorded_at: "2026-09-14T14:31:00" },
    { interview_question_id: 9003, seq: 3, dimension: "逻辑思维", source: "bank",
      content: "线上接口 P99 从 80ms 涨到 800ms，你会按什么顺序排查？说说每一步想验证什么。",
      answer: "我先看监控确认是全局还是单接口，以及是否和发版时间吻合。如果吻合就直接回滚。不吻合的话分三层：一是入口层看 QPS 和连接数有没有变化；二是应用层看 GC 和线程池，我们之前遇到过线程池被慢 SQL 打满；三是数据库层看慢查询和锁等待。先分层定位再深入，避免一上来就翻代码。",
      recorded_at: "2026-09-14T14:47:00" },
    { interview_question_id: 9004, seq: 4, dimension: "文化契合", source: "ai",
      content: "你上一份工作里，团队是怎么做技术决策的？你更适应哪种方式？",
      answer: "我们组比较扁平，小改动谁负责谁定，涉及多模块的会拉个短会讨论。我个人习惯是把方案写成文档发出来让大家异步评论，这样思考更充分。不太适应的是那种完全由 leader 拍板、下面只负责执行的模式。",
      recorded_at: "2026-09-14T15:02:00" },
    { interview_question_id: 9005, seq: 5, dimension: "专业能力", source: "ai",
      content: "关于专业能力：如果让你从零开始改进后端工程师岗位的一项关键流程，你会怎么做？",
      answer: "我会先改进代码评审流程。现在的评审基本只看语法和风格，缺少对边界条件和失败路径的检查。我会加一个 checklist，要求作者在提测前说明异常场景怎么处理，评审人重点看这部分。",
      recorded_at: "2026-09-14T15:09:00" },
    { interview_question_id: 9006, seq: 6, dimension: "沟通能力", source: "ai",
      content: "关于沟通能力：请举例说明你如何衡量自己在沟通能力方面的表现。",
      answer: "我一般看两件事：一是需求返工率，如果前期沟通充分，后面返工就少；二是跨组协作时对方是否愿意主动找我。上一季度我负责的模块返工率为零，我觉得算是沟通到位的一个侧面证据。",
      recorded_at: "2026-09-14T15:13:00" },
    { interview_question_id: 9007, seq: 7, dimension: "逻辑思维", source: "ai",
      content: "关于逻辑思维：请描述一次你在后端工程师相关工作中遇到的具体挑战，以及你的处理方式。",
      answer: "比较典型的是库存超卖。大促时出现了几十单超卖，我先把问题定位到扣减库存用的是先查后改，并发下存在竞态。改成用数据库的行锁加条件更新，影响行数为零就视为扣减失败。上线后没再出现过。",
      recorded_at: "2026-09-14T15:16:00" },
    { interview_question_id: 9008, seq: 8, dimension: "文化契合", source: "ai",
      content: "关于文化契合：如果让你从零开始改进后端工程师岗位的一项关键流程，你会怎么做？",
      answer: "想把值班制度改一下。现在是谁的模块出问题谁处理，但半夜被叫醒第二天效率很差。我倾向按周轮值，值班的人当周不排重活，这样响应质量和白天状态都能保证。",
      recorded_at: "2026-09-14T15:19:00" },
  ],
  102: [
    { interview_question_id: 9101, seq: 1, dimension: "沟通能力", source: "bank",
      content: "请描述一次你需要说服同事接受不同技术方案的经历，你当时是怎么推进的？",
      answer: "有一次我们争论要不要引入消息队列，我先把两边的成本列出来，包括运维负担和团队的学习成本，最后大家同意先不上，等真的有削峰需求再说。",
      recorded_at: "2026-09-16T10:41:00" },
    { interview_question_id: 9102, seq: 2, dimension: "专业能力", source: "bank",
      content: "你们的订单库做过分库分表吗？分片键是怎么选的，遇到跨分片查询怎么处理？",
      answer: "分过，按订单号做的。跨分片查得不多，实在要查就走离线表。",
      recorded_at: "2026-09-16T10:52:00" },
    { interview_question_id: 9103, seq: 3, dimension: "逻辑思维", source: "bank",
      content: "线上接口 P99 从 80ms 涨到 800ms，你会按什么顺序排查？说说每一步想验证什么。",
      answer: "",
      recorded_at: "2026-09-16T10:58:00" },
    { interview_question_id: 9104, seq: 4, dimension: "文化契合", source: "ai",
      content: "你上一份工作里，团队是怎么做技术决策的？你更适应哪种方式？",
      answer: null, recorded_at: null },
    { interview_question_id: 9105, seq: 5, dimension: "专业能力", source: "ai",
      content: "关于专业能力：请举例说明你如何衡量自己在专业能力方面的表现。",
      answer: null, recorded_at: null },
    { interview_question_id: 9106, seq: 6, dimension: "沟通能力", source: "ai",
      content: "关于沟通能力：请描述一次你在后端工程师相关工作中遇到的具体挑战，以及你的处理方式。",
      answer: null, recorded_at: null },
    { interview_question_id: 9107, seq: 7, dimension: "逻辑思维", source: "ai",
      content: "关于逻辑思维：如果让你从零开始改进后端工程师岗位的一项关键流程，你会怎么做？",
      answer: null, recorded_at: null },
    { interview_question_id: 9108, seq: 8, dimension: "文化契合", source: "ai",
      content: "关于文化契合：请举例说明你如何衡量自己在文化契合方面的表现。",
      answer: null, recorded_at: null },
  ],
};

/** 取面试详情；未收录的用例返回一份通用的 8 题骨架。 */
export function getInterviewDetail(id) {
  const base = interviews.find((i) => i.id === Number(id));
  if (!base) return null;

  const questionsForId = interviewQuestions[base.id] || buildGenericQuestions(base);
  return { ...base, jd: "", evaluation_dimensions: [], questions: questionsForId };
}

function buildGenericQuestions(base) {
  const dims = ["沟通能力", "专业能力", "逻辑思维", "文化契合"];
  return Array.from({ length: 8 }, (_, i) => ({
    interview_question_id: base.id * 100 + i,
    seq: i + 1,
    dimension: dims[i % dims.length],
    source: i < 3 ? "bank" : "ai",
    content: "（原型未收录该面试的题目内容）",
    answer: i < base.answered_count ? "（原型未收录该面试的回答内容）" : null,
    recorded_at: i < base.answered_count ? base.created_at : null,
  }));
}

/**
 * 评估报告 —— 分数刻意跨过 6.5 阈值，用来验证 pass / watch 两色的分界。
 * 总分 7.2 = (8.0 + 7.5 + 7.0 + 6.3) / 4
 */
export const report101 = {
  interview_id: 101,
  candidate_name: "张书宁",
  position_name: "后端工程师",
  overall_score: 7.2,
  conclusion: "整体表现良好，建议结合岗位要求综合评估。",
  strengths: [
    "沟通能力（8.0）：表现较好",
    "专业能力（7.5）：表现较好",
    "逻辑思维（7.0）：表现较好",
  ],
  weaknesses: ["文化契合（6.3）：有待提升"],
  evaluated_at: "2026-09-14T15:21:00",
  dimension_scores: [
    { dimension: "沟通能力", score: 8.0, comment: "回答详实，沟通能力方面有清晰的具体事例支撑，表达有条理。" },
    { dimension: "专业能力", score: 7.5, comment: "回答基本切题，在专业能力方面有一定体现，建议补充更多细节与量化结果。" },
    { dimension: "逻辑思维", score: 7.0, comment: "回答基本切题，在逻辑思维方面有一定体现，建议补充更多细节与量化结果。" },
    { dimension: "文化契合", score: 6.3, comment: "回答基本切题，在文化契合方面有一定体现，建议补充更多细节与量化结果。" },
  ],
  question_scores: interviewQuestions[101].map((q, i) => ({
    interview_question_id: q.interview_question_id,
    seq: q.seq,
    content: q.content,
    dimension: q.dimension,
    answer: q.answer || null,
    score: [8.0, 7.5, 7.0, 6.0, 7.5, 8.5, 7.0, 6.5][i],
    comment: [
      "回答详实，沟通能力方面有清晰的具体事例支撑，表达有条理。",
      "回答详实，专业能力方面有清晰的具体事例支撑，表达有条理。",
      "回答基本切题，在逻辑思维方面有一定体现，建议补充更多细节与量化结果。",
      "回答较简略，尚未体现出文化契合方面的具体经验。",
      "回答详实，专业能力方面有清晰的具体事例支撑，表达有条理。",
      "回答详实，沟通能力方面有清晰的具体事例支撑，表达有条理。",
      "回答基本切题，在逻辑思维方面有一定体现，建议补充更多细节与量化结果。",
      "回答基本切题，在文化契合方面有一定体现，建议补充更多细节与量化结果。",
    ][i],
  })),
};

/** 模拟 SSE 事件序列，用于评估页的实时演示。 */
export function buildStreamEvents(interviewId) {
  const detail = getInterviewDetail(interviewId) || getInterviewDetail(102);
  const dims = ["沟通能力", "专业能力", "逻辑思维", "文化契合"];

  const events = [];

  detail.questions.forEach((q, i) => {
    const score = [7.5, 8.0, 6.5, 6.0, 7.0, 8.5, 7.5, 6.0][i % 8];
    events.push(["question", {
      interview_question_id: q.interview_question_id,
      seq: q.seq,
      index: i + 1,
      total: detail.questions.length,
      dimension: q.dimension,
      score,
      comment: score >= 8
        ? `回答详实，${q.dimension}方面有清晰的具体事例支撑，表达有条理。`
        : score >= 6.5
          ? `回答基本切题，在${q.dimension}方面有一定体现，建议补充更多细节与量化结果。`
          : `回答较简略，尚未体现出${q.dimension}方面的具体经验。`,
    }]);
  });

  dims.forEach((dim, i) => {
    const score = [7.5, 7.8, 7.0, 6.2][i];
    events.push(["dimension", {
      dimension: dim,
      index: i + 1,
      total: dims.length,
      score,
      comment: score >= 6.5
        ? `${dim}维度表现中等，基本达到岗位要求。`
        : `${dim}维度表现偏弱，建议在后续轮次中重点考察。`,
    }]);
  });

  events.push(["report", {
    overall_score: 7.1,
    conclusion: "整体表现良好，建议结合岗位要求综合评估。",
    strengths: ["沟通能力（7.5）：表现较好", "专业能力（7.8）：表现较好", "逻辑思维（7.0）：表现较好"],
    weaknesses: ["文化契合（6.2）：有待提升"],
  }]);

  events.push(["done", { status: "evaluated" }]);
  return events;
}
