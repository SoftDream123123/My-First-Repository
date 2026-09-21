/**
 * 刷题模块 Mock 联调测试 —— 取题 / 练习作答与即时判分 / 重判 / 结束 / 错题本 / 统计。
 *
 * 覆盖的是**只靠单测测不到**的那一半：真实路由跳转、真实 DOM、真实请求体与查询串。
 * `referenceAnswerOf` 与 `percent` 在 `src/__tests__/practice-grading.test.js` 里测；
 * 这里测的是「它们真的被用上了没有」。
 *
 * ⚠️ 断言里的期望值**从接口文档来**（§12 / §13.19–13.25），不从 `standalone.html`
 * 原型的字段名来。原型在这一块有两处与真实契约对不上（本轮都按契约改了）：
 *   1. 提交作答的参考答案**按题型二选一**（`correct_answer` / `reference_answer`），
 *      原型只读 `reference_answer` → 单选题的复盘永远标不出正确答案；
 *   2. `WrongBookItem` **没有** `dimension` / `question_type`，原型直接读它们
 *      → 渲染出一排空标签。本轮错题本不做这两个筛选（见该页文件头）。
 *
 * 运行：npm run dev 后打开 /mock/practice-harness.html
 */

import { boot, installUnauthorizedHandler } from '../src/app.js';
import * as router from '../src/router.js';
import * as session from '../src/session.js';
import { buttonIn, clearToasts, createReport, installFakeBackend, openOverlay, settle, toasts } from './harness.js';

const report = createReport('刷题模块 Mock 测试');
const { check } = report;

/* ==========================================================================
   固定数据
   ========================================================================== */

const CANDIDATE = { id: 7, username: 'li.yun', role: 'candidate', is_active: true, created_at: '2026-09-01T09:00:00' };

const POSITIONS = [
  { id: 1, name: '后端工程师', question_count: 12 },
  { id: 2, name: '前端工程师', question_count: 4 },
];

const choice = (id, content, options, dimension = '专业能力') => ({
  id, position_id: 1, category: '基础', dimension, difficulty: 'easy',
  content, question_type: 'single_choice', options, tags: ['网络'],
});
const written = (id, content, dimension = '沟通能力') => ({
  id, position_id: 1, category: '基础', dimension, difficulty: 'medium',
  content, question_type: 'short_answer', options: [], tags: [],
});

/** 题池：三题，**没有 hard** —— 用来验「筛到 0 题」的表现。 */
const POOL = [
  choice(12, 'HTTP 状态码 401 表示什么？', ['未认证', '未授权', '资源不存在', '服务器错误']),
  choice(13, '数据库索引的最左前缀原则是什么？', ['A 选项', 'B 选项', 'C 选项']),
  written(14, '请描述一次你处理线上故障的完整过程。'),
];

const SESSION_ONGOING = {
  session_id: 7, status: 'ongoing', position_name: '后端工程师',
  category: '基础', dimension: null, difficulty: 'medium', question_type: null,
  total: 4, answered_count: 2, correct_count: 1,
  started_at: '2026-09-21T14:00:00', finished_at: null,
};
const SESSION_DONE = {
  session_id: 6, status: 'finished', position_name: '前端工程师',
  category: null, dimension: null, difficulty: 'easy', question_type: 'single_choice',
  total: 5, answered_count: 5, correct_count: 3,
  started_at: '2026-09-19T14:00:00', finished_at: '2026-09-19T14:20:00',
};

/**
 * 练习详情：四道题把三种状态都摆出来 ——
 *   61 单选、已答且判对；62 单选、**未答**（提交它才能验 correct_answer 那条路径）；
 *   63 简答、未答（验「提交一道不会清掉另一道里写了一半的内容」）；
 *   64 简答、已答但**未判分**（验三态里的中间那一态 + 重判入口）。
 */
function sessionDetail(over = {}) {
  return {
    session: {
      id: 7, status: 'ongoing', position_id: 1,
      category: '基础', dimension: null, difficulty: 'medium', question_type: null,
      total: 4, answered_count: 2, correct_count: 1,
      started_at: '2026-09-21T14:00:00', finished_at: null,
    },
    items: [
      {
        item_id: 61, seq: 1,
        question: choice(12, 'HTTP 状态码 401 表示什么？', ['未认证', '未授权', '资源不存在', '服务器错误']),
        user_answer: '未认证', is_correct: true, score: 10.0,
        explanation: '401 表示身份未认证或认证失败；403 才是已认证但无权限。',
        reference_answer: '未认证',
      },
      {
        item_id: 62, seq: 2,
        question: choice(13, '数据库索引的最左前缀原则是什么？', ['A 选项', 'B 选项', 'C 选项'], '逻辑思维'),
        user_answer: null, is_correct: null, score: null, explanation: null, reference_answer: null,
      },
      {
        item_id: 63, seq: 3,
        question: written(14, '请描述一次你处理线上故障的完整过程。'),
        user_answer: null, is_correct: null, score: null, explanation: null, reference_answer: null,
      },
      {
        item_id: 64, seq: 4,
        question: written(15, '你怎么理解「可观测性」？', '文化契合'),
        user_answer: '我的回答', is_correct: null, score: null,
        explanation: 'AI 判分暂时不可用，本题稍后可重判。', reference_answer: null,
      },
    ],
    resume_id: null,
    resume_match_applied: false,
    ...over,
  };
}

const WRONG_BOOK = [
  {   // 单选的错题：options 非空 → 判为单选并渲染复盘
    question_id: 21,
    content: 'HTTP 状态码 403 表示什么？',
    options: ['未认证', '无权限', '资源不存在', '服务器错误'],
    reference_answer: '无权限',
    explanation: '403 是已认证但没有权限。',
    my_wrong_answer: '未认证',
    wrong_count: 2,
    last_wrong_at: '2026-09-21T14:30:00',
  },
  {   // 简答的错题：options 为空数组 → 判为简答
    question_id: 22,
    content: '说说你对幂等性的理解。',
    options: [],
    reference_answer: '同一请求重复执行，结果一致。',
    explanation: null,
    my_wrong_answer: '',
    wrong_count: 1,
    last_wrong_at: '2026-09-20T09:00:00',
  },
];

const STATS = {
  total_answered: 40, scored_count: 36, unscored_count: 4,
  correct_count: 24, accuracy: 0.667, session_count: 5,
  by_dimension: [
    { dimension: '专业能力', answered: 20, scored: 18, correct: 12, accuracy: 0.667 },
    { dimension: '沟通能力', answered: 12, scored: 12, correct: 8, accuracy: 0.667 },
    { dimension: '文化契合', answered: 8, scored: 6, correct: 4, accuracy: null },
  ],
  by_type: [
    { question_type: 'single_choice', answered: 22, scored: 22, correct: 15, accuracy: 0.682 },
    { question_type: 'short_answer', answered: 18, scored: 14, correct: 9, accuracy: 0.643 },
  ],
};

const STATS_EMPTY = {
  total_answered: 0, scored_count: 0, unscored_count: 0,
  correct_count: 0, accuracy: null, session_count: 0,
  by_dimension: [], by_type: [],
};

/* ==========================================================================
   假后端
   ========================================================================== */

const flags = {
  sessions: [SESSION_ONGOING, SESSION_DONE],
  pool: POOL,
  startFails: false,
  detail: null,
  wrongBook: WRONG_BOOK,
  stats: STATS,
  finishing: true,
};

function handlers() {
  return {
    'GET /auth/me': () => ({ status: 200, body: CANDIDATE }),
    'GET /candidate/positions': () => ({ status: 200, body: POSITIONS }),

    'GET /practice/sessions': () => ({ status: 200, body: flags.sessions }),

    // 按查询串真的过滤一下，好让「符合条件 N 题」这条断言测的是真行为
    'GET /practice/questions': ({ query }) => {
      const params = new URLSearchParams(query);
      const difficulty = params.get('difficulty');
      const dimension = params.get('dimension');
      const rows = flags.pool.filter((q) =>
        (!difficulty || q.difficulty === difficulty) && (!dimension || q.dimension === dimension));
      return { status: 200, body: rows };
    },

    'POST /practice/sessions': ({ body }) => {
      if (flags.startFails) {
        return { status: 409, body: { code: 'BUSINESS_ERROR', message: '没有符合条件的题目，请调整筛选条件', detail: null } };
      }
      flags.lastStartBody = body;
      return { status: 201, body: sessionDetail() };
    },

    'GET /practice/sessions/:id': () => ({ status: 200, body: flags.detail ?? sessionDetail() }),

    'POST /practice/sessions/:id/items': ({ body }) => {
      // 单选把答案放 `correct_answer`、简答放 `reference_answer`（API 文档 §13.22）
      const isChoice = body.item_id === 62;
      return {
        status: 200,
        body: {
          item_id: body.item_id,
          seq: body.item_id === 62 ? 2 : 3,
          user_answer: body.user_answer,
          is_correct: isChoice ? false : true,
          score: isChoice ? 0.0 : 8.0,
          correct_answer: isChoice ? 'B 选项' : null,
          reference_answer: isChoice ? null : '参考作答',
          explanation: isChoice ? '最左前缀原则指的是…' : '答得不错，可以再补充排查顺序。',
          progress: { answered_count: 3, correct_count: 2, total: 4 },
        },
      };
    },

    'POST /practice/items/:id/rescore': ({ path }) => ({
      status: 200,
      body: {
        item_id: Number(path.split('/')[3]),
        seq: 4,
        user_answer: '我的回答',
        is_correct: true,
        score: 7.5,
        correct_answer: null,
        reference_answer: '可观测性由日志、指标、链路三块构成。',
        explanation: '重判完成。',
        progress: { answered_count: 2, correct_count: 2, total: 4 },
      },
    }),

    'POST /practice/sessions/:id/finish': () => ({
      status: 200,
      body: {
        session_id: 7, status: 'finished',
        total: 4, answered_count: 2, correct_count: 1, unscored_count: 1,
        accuracy: 0.5,
        by_dimension: [
          { dimension: '专业能力', answered: 1, correct: 1, accuracy: 1 },
          { dimension: '文化契合', answered: 1, correct: 0, accuracy: null },
        ],
      },
    }),

    'GET /practice/wrong-book': () => ({ status: 200, body: flags.wrongBook }),
    'GET /practice/stats': () => ({ status: 200, body: flags.stats }),
  };
}

const backend = installFakeBackend(handlers());
installUnauthorizedHandler();

/* ==========================================================================
   小工具
   ========================================================================== */

async function go(hash) {
  router.navigate(String(hash).replace(/^#/, ''));
  await settle();
  await settle();
  await settle();
}

const hash = () => location.hash;
const page = () => document.getElementById('app');
const text = () => page().textContent;
const has = (selector) => Boolean(page().querySelector(selector));
const all = (selector) => [...page().querySelectorAll(selector)];
const navTexts = () => all('.nav-item').map((a) => a.textContent.trim());

/** 第 n 道题（从 0 数）。提交只重画一道，所以这个下标在重画前后都成立。 */
const itemAt = (index) => all('.practice-item')[index];

const selectIn = (index) => all('.filterbar .select')[index];
const lastCall = (method, path) => [...backend.calls].reverse().find((c) => c.method === method && c.path === path);
const called = (method, path) => backend.calls.some((c) => c.method === method && c.path === path);

function signInAsCandidate() {
  const previous = session.getSide();
  session.setSide('candidate');
  session.save('cand-token', CANDIDATE);
  session.setSide(previous);
}

/* ==========================================================================
   用例
   ========================================================================== */

report.run(async () => {
  try { localStorage.clear(); } catch { /* file:// 下可能不可用 */ }

  await boot(document.getElementById('app'));
  await settle();
  await settle();
  await settle();

  signInAsCandidate();
  await go('#/candidate/practice');

  /* ---------- 1. 导航与外壳 ---------- */
  check('候选人导航里出现了刷题、错题本、练习统计',
    ['刷题', '错题本', '练习统计'].every((label) => navTexts().includes(label)),
    navTexts().join(','));
  check('「我的面试」仍排在导航第一位（默认落地页不变）', navTexts()[0] === '我的面试', navTexts().join(','));
  check('候选人端仍没有 HR 侧入口', !navTexts().includes('岗位') && !navTexts().includes('题库'));

  /* ---------- 2. 筛选栏的取值口径 ---------- */
  const positionOptions = [...selectIn(0).options].map((o) => o.textContent.trim());
  check('岗位下拉来自 /candidate/positions，且文案带题量',
    positionOptions.includes('后端工程师（12 题）') && positionOptions.includes('前端工程师（4 题）'),
    positionOptions.join(' | '));
  const categoryOptions = [...selectIn(1).options].map((o) => o.textContent.trim());
  check('分类下拉从**实际题池**派生（而不是写死的）',
    categoryOptions.join(',') === '不限分类,基础', categoryOptions.join(','));
  const dimensionOptions = [...selectIn(2).options].map((o) => o.textContent.trim());
  // 三题里只有两个不同维度 → 下拉正好两项，这本身就证明了「派生 + 去重」。
  // 顺序是按中文 locale 排的（沟 < 专），不是题池里出现的顺序
  check('维度下拉同样从题池派生，且是同口径去重后的集合',
    dimensionOptions.join(',') === '不限维度,沟通能力,专业能力', dimensionOptions.join(','));

  /* ---------- 3. 实时计数 ---------- */
  check('首次加载就把「符合条件 N 题」报出来（不必先点开始）',
    page().querySelector('.practice-count')?.textContent === '符合条件 3 题',
    page().querySelector('.practice-count')?.textContent);
  check('计数请求不带任何筛选参数（未选即不过滤）',
    lastCall('GET', '/practice/questions')?.query === '', String(lastCall('GET', '/practice/questions')?.query));

  // 题池里没有 hard，选它应当报 0 题并把开始按钮禁掉
  const difficulty = selectIn(3);
  difficulty.value = 'hard';
  difficulty.dispatchEvent(new Event('change'));
  await settle();
  await settle();
  check('筛到 0 题 → 计数换成「换一组筛选条件」并标警示色',
    page().querySelector('.practice-count.is-none')?.textContent.includes('没有符合条件'),
    page().querySelector('.practice-count')?.textContent);
  check('筛到 0 题 → 开始按钮禁用',
    buttonIn(page(), '开始练习')?.disabled === true);

  difficulty.value = 'medium';
  difficulty.dispatchEvent(new Event('change'));
  await settle();
  await settle();
  check('筛回有结果的难度 → 计数恢复、按钮重新可用',
    page().querySelector('.practice-count')?.textContent === '符合条件 1 题'
      && buttonIn(page(), '开始练习')?.disabled === false,
    page().querySelector('.practice-count')?.textContent);

  /* ---------- 4. 开始练习的请求体 ---------- */
  backend.reset();
  selectIn(1).value = '基础';
  selectIn(1).dispatchEvent(new Event('change'));
  await settle();
  await settle();
  backend.reset();
  buttonIn(page(), '开始练习').click();
  await settle();
  await settle();
  await settle();

  const startBody = lastCall('POST', '/practice/sessions')?.body ?? {};
  check('开始练习只带选中的筛选 + 题量',
    startBody.difficulty === 'medium' && startBody.category === '基础' && startBody.size === 5,
    JSON.stringify(startBody));
  check('未选的筛选项**不出现在请求体里**（不是传空串）',
    !('dimension' in startBody) && !('position_id' in startBody) && !('question_type' in startBody),
    JSON.stringify(startBody));
  check('本轮**不带 resume_id**（简历能力属于下一轮，省略比传 null 干净）',
    !('resume_id' in startBody), JSON.stringify(startBody));
  check('取题成功 → 进入该次练习', hash() === '#/candidate/practice/7', hash());

  /* ---------- 5. 练习页：整卷铺开 + 三态 ---------- */
  check('整卷铺开：四道题一次全渲染出来',
    all('.practice-item').length === 4, String(all('.practice-item').length));
  check('岗位名从 /candidate/positions 换了出来（会话里只有 position_id）',
    page().querySelector('h1')?.textContent === '后端工程师', page().querySelector('h1')?.textContent);
  check('筛选用作副标题，留痕可读',
    text().includes('基础') && text().includes('中等'), page().querySelector('.page-lede')?.textContent);
  check('进度条报「已答 2 / 4」与「答对 1」',
    text().includes('已答 2 / 4') && text().includes('答对 1'), page().querySelector('.practice-progress')?.textContent);

  check('单选题渲染成单选项（不是文本框）',
    itemAt(1).querySelectorAll('.choice-option').length === 3);
  check('简答题渲染成文本框',
    Boolean(itemAt(2).querySelector('textarea')));
  check('单选未选中时提交按钮禁用（避免提交空答案）',
    buttonIn(itemAt(1), '提交')?.disabled === true);
  check('已判对的题显示「答对」与得分',
    itemAt(0).querySelector('.verdict.is-correct .verdict-label')?.textContent === '答对'
      && itemAt(0).querySelector('.verdict-score')?.textContent === '10 / 10',
    itemAt(0).querySelector('.verdict')?.textContent);
  check('已判对的题给出解析',
    itemAt(0).querySelector('.verdict-note')?.textContent.includes('401'),
    itemAt(0).querySelector('.verdict-note')?.textContent);

  /* ---------- 6. 未判分**不是**答错 ---------- */
  check('未判分的题显示中性「未判分」，**不带错误样式**',
    itemAt(3).querySelector('.verdict-label')?.textContent === '未判分'
      && !itemAt(3).querySelector('.verdict').classList.contains('is-wrong')
      && !itemAt(3).querySelector('.verdict').classList.contains('is-correct'),
    itemAt(3).querySelector('.verdict')?.className);
  check('未判分的题给出「重判」入口（AI 不可用是暂时的）',
    buttonIn(itemAt(3), '重判') !== undefined);
  check('未判分的题**不显示分数**（没有分数可显示）',
    itemAt(3).querySelector('.verdict-score') === null);

  /* ---------- 7. 简答空提交被本地拦住 ---------- */
  clearToasts();
  backend.reset();
  buttonIn(itemAt(2), '提交').click();
  await settle();
  check('简答空提交 → 本地提示，不发请求', toasts().includes('请先写下回答') && backend.calls.length === 0,
    `${toasts().join(' | ')} / ${backend.calls.length} 次`);

  /* ---------- 8. 提交单选：**参考答案在 correct_answer 里** ---------- */
  backend.reset();
  // 先在**另一道**题里写一半（下面要验它不会被这次提交清掉）
  const halfTextarea = itemAt(2).querySelector('textarea');
  halfTextarea.value = '写了一半、还没提交的内容';

  const radios = itemAt(1).querySelectorAll('.choice-option input');
  radios[0].checked = true;                                  // 选「A 选项」（错的）
  radios[0].dispatchEvent(new Event('change', { bubbles: true }));
  await settle();
  check('选中一项后提交按钮可用', buttonIn(itemAt(1), '提交')?.disabled === false);
  buttonIn(itemAt(1), '提交').click();
  await settle();
  await settle();

  check('提交体用的是 item_id 而不是题目 id',
    lastCall('POST', '/practice/sessions/7/items')?.body?.item_id === 62,
    JSON.stringify(lastCall('POST', '/practice/sessions/7/items')?.body));
  check('提交后该题就地显示判分结果（「答错」）',
    itemAt(1).querySelector('.verdict.is-wrong .verdict-label')?.textContent === '答错',
    itemAt(1).querySelector('.verdict')?.textContent);
  check('**单选题的正确答案被标出来了** —— 答案在 correct_answer 里，只读 reference_answer 会丢',
    itemAt(1).querySelector('.option-item.is-correct')?.textContent.includes('B 选项'),
    itemAt(1).querySelector('.option-item.is-correct')?.textContent);
  check('同时标出「我选的」那一项（复盘的价值在这里）',
    itemAt(1).querySelector('.option-item.is-mine-wrong')?.textContent.includes('A 选项'),
    itemAt(1).querySelector('.option-item.is-mine-wrong')?.textContent);

  /* ---------- 9. 提交一道**不会**清掉另一道里写了一半的内容 ---------- */
  // 断言的是**同一个节点**、值也没变 —— 只比 `value` 的话，整卷重画后再把值填回去
  // 也会通过，那测的就不是「没重画」了
  check('第三题还是原来那个文本框节点（提交只重画被提交的那一道）',
    itemAt(2).querySelector('textarea') === halfTextarea);
  check('那个文本框里写了一半的内容还在', halfTextarea.value === '写了一半、还没提交的内容',
    halfTextarea.value);

  /* ---------- 10. 重判：未判分 → 判分 ---------- */
  backend.reset();
  buttonIn(itemAt(3), '重判').click();
  await settle();
  await settle();
  check('重判请求打到 /practice/items/{item_id}/rescore',
    called('POST', '/practice/items/64/rescore'));
  check('重判后该题变成「答对」并给出分数',
    itemAt(3).querySelector('.verdict.is-correct .verdict-label')?.textContent === '答对'
      && itemAt(3).querySelector('.verdict-score')?.textContent === '7.5 / 10',
    itemAt(3).querySelector('.verdict')?.textContent);
  check('重判后不再显示「重判」按钮（已判分就不该再给这条入口）',
    buttonIn(itemAt(3), '重判') === undefined);
  check('重判给出的**简答**参考答案也能显示出来（这次走的是 reference_answer）',
    itemAt(3).textContent.includes('可观测性由日志、指标、链路三块构成'),
    itemAt(3).querySelector('.practice-answer')?.textContent);

  /* ---------- 11. 结束练习：确认前不算数 ---------- */
  clearToasts();
  backend.reset();
  buttonIn(page(), '结束练习').click();
  await settle();
  check('结束练习先弹二次确认，并如实说出还有几题没答',
    // 到这一步已答的是 61（原有）、62（第 8 节提交）、64（第 10 节重判）——
    // 所以只剩第三题没答。这个数字从当前状态算，不是写死的
    openOverlay()?.textContent.includes('还有 1 题没有作答'), openOverlay()?.textContent.slice(0, 70));
  buttonIn(openOverlay(), '取消').click();
  await settle();
  await settle();
  check('取消 → 不发结束请求', !called('POST', '/practice/sessions/7/finish'));
  check('取消 → 仍可作答（没有提前锁住）', has('.practice-item textarea') || has('.choice-option'));

  backend.reset();
  buttonIn(page(), '结束练习').click();
  await settle();
  buttonIn(openOverlay(), '结束练习').click();
  await settle();
  await settle();
  await settle();
  check('确认 → 发出结束请求', called('POST', '/practice/sessions/7/finish'));
  check('结束后给出小结（题目 / 已作答 / 答对 / 正确率）',
    text().includes('练习小结') && text().includes('正确率'),
    page().querySelector('.summary-grid')?.textContent);
  check('小结里**必须**单独报出未判分的题数（否则会被读成答错）',
    text().includes('有 1 题未判分，不计入正确率'),
    page().querySelector('.summary-grid')?.parentElement?.textContent);
  check('小结按维度拆分的条只报正确率，不报「对 / 答」',
    page().querySelector('.summary-bars')?.textContent.includes('专业能力')
      && page().querySelector('.summary-bar-value')?.textContent === '100%',
    page().querySelector('.summary-bars')?.textContent);
  check('维度里没有已判分时显示「未判分」而不是 0%',
    page().querySelector('.summary-bars')?.textContent.includes('未判分'),
    page().querySelector('.summary-bars')?.textContent);
  check('结束后未作答的题转为「未作答（本次练习已结束）」，不再给作答控件',
    text().includes('未作答（本次练习已结束）') && !has('.choice-option') && !has('.practice-item textarea'),
    text().includes('未作答（本次练习已结束）') ? 'ok' : '缺提示');
  check('结束后「结束练习」按钮消失（没有第二次结束）', buttonIn(page(), '结束练习') === undefined);

  /* ---------- 12. 取不到题：409 后筛选条件保留 ---------- */
  flags.startFails = true;
  clearToasts();
  await go('#/candidate/practice');
  const diff = selectIn(3);
  diff.value = 'easy';
  diff.dispatchEvent(new Event('change'));
  await settle();
  await settle();
  backend.reset();
  buttonIn(page(), '开始练习').click();
  await settle();
  await settle();
  check('取不到题 → 原样展示后端文案', toasts().includes('没有符合条件的题目，请调整筛选条件'),
    toasts().join(' | '));
  check('取不到题 → **筛选条件不被重置**（让人看到自己选的是什么）',
    selectIn(3).value === 'easy' && selectIn(1).value === '', `${selectIn(3).value} / ${selectIn(1).value}`);
  check('取不到题 → 按钮恢复可用，可以改了再试',
    buttonIn(page(), '开始练习')?.disabled === false);
  flags.startFails = false;

  /* ---------- 13. 进行中 / 历史 两块 ---------- */
  await go('#/candidate/practice');
  check('进行中的练习单独一块，入口写「继续」',
    text().includes('继续练习') && buttonIn(page(), '继续') !== undefined,
    all('.panel-title').map((n) => n.textContent).join(','));

  /* ---------- 14. 没有练习记录时的空态 ---------- */
  flags.sessions = [];
  await go('#/candidate/practice');
  check('没有练习记录 → 空态给出下一步', text().includes('还没有练习记录'));

  // 空态里那颗按钮必须与筛选栏那颗**是同一个动作**。取最后一个 ——
  // `buttonIn` 取的是文档顺序最前的那个（筛选栏的），点它就测不到空态那条接线了
  const startButtons = all('button').filter((b) => b.textContent.trim() === '开始练习');
  check('「开始练习」在筛选栏与空态各有一颗', startButtons.length === 2, String(startButtons.length));
  backend.reset();
  startButtons[startButtons.length - 1].click();
  await settle();
  await settle();
  check('空态那颗按钮确实发起了取题（接线到同一个动作，不是另写一份）',
    called('POST', '/practice/sessions'));
  flags.sessions = [SESSION_ONGOING, SESSION_DONE];

  /* ---------- 14b. 题库为空时，两颗「开始练习」共享同一份可用状态 ---------- */
  // 只同步一颗的后果是「按了没反应」，而原因写在页面上另一处 —— 这类沉默的
  // 失效正是本项目最在意的一种
  flags.pool = [];
  flags.sessions = [];
  await go('#/candidate/practice');
  check('题库为空 → 计数说明没有可取的题',
    page().querySelector('.practice-count.is-none')?.textContent.includes('没有符合条件'),
    page().querySelector('.practice-count')?.textContent);
  check('题库为空 → 筛选栏与空态**两颗**开始按钮都被禁用',
    (() => {
      const buttons = all('button').filter((b) => b.textContent.trim() === '开始练习');
      return buttons.length === 2 && buttons.every((b) => b.disabled);
    })(),
    all('button').filter((b) => b.textContent.trim() === '开始练习').map((b) => b.disabled).join(','));
  flags.pool = POOL;
  flags.sessions = [SESSION_ONGOING, SESSION_DONE];

  /* ---------- 15. 错题本 ---------- */
  backend.reset();
  await go('#/candidate/wrong-book');
  check('错题本请求带上 limit（默认 50 太少，取接口允许的上限 200）',
    lastCall('GET', '/practice/wrong-book')?.query === 'limit=200',
    String(lastCall('GET', '/practice/wrong-book')?.query));
  check('两道错题都渲染出来', all('.practice-item').length === 2, String(all('.practice-item').length));
  check('「错 N 次」被标出来（那正是该重点补哪一块的信号）',
    text().includes('错 2 次') && text().includes('错 1 次'));
  check('单选题的错题标出正确答案与我选错的那一项',
    itemAt(0).querySelector('.option-item.is-correct')?.textContent.includes('无权限')
      && itemAt(0).querySelector('.option-item.is-mine-wrong')?.textContent.includes('未认证'),
    itemAt(0).querySelector('.option-list')?.textContent);
  check('简答题的错题显示我的作答与参考答案',
    itemAt(1).textContent.includes('同一请求重复执行，结果一致'));
  check('题型由 options 是否为空判定（简答题的 options 必为空数组）',
    itemAt(0).querySelector('.tag--off')?.textContent === '单选'
      && itemAt(1).querySelector('.tag--off')?.textContent === '简答',
    `${itemAt(0).querySelector('.tag--off')?.textContent} / ${itemAt(1).querySelector('.tag--off')?.textContent}`);
  check('错题本**不渲染空的维度/题型下拉**（WrongBookItem 没有这两个字段，无从取值）',
    !has('.filterbar'), has('.filterbar') ? '仍在渲染筛选栏' : 'ok');

  flags.wrongBook = [];
  await go('#/candidate/wrong-book');
  check('没有错题 → 空态给「去刷题」', text().includes('还没有错题') && buttonIn(page(), '去刷题') !== undefined);
  flags.wrongBook = WRONG_BOOK;

  /* ---------- 16. 练习统计 ---------- */
  backend.reset();
  await go('#/candidate/stats');
  check('统计页**不出现雷达图**', !has('svg.radar'), has('svg.radar') ? '有雷达图' : 'ok');
  check('四个数字格：已作答 / 已判分 / 正确率 / 练习次数',
    (() => {
      const cells = all('.summary-cell').map((c) => c.textContent);
      return cells.length === 4 && cells[0].includes('40') && cells[1].includes('36')
        && cells[2].includes('67%') && cells[3].includes('5');
    })(), all('.summary-cell').map((c) => c.textContent).join(' | '));
  check('未判分的题单独报出，并说明不计入正确率',
    text().includes('还有 4 题未判分，它们不计入正确率'));
  check('按维度与按题型各一组条',
    text().includes('按维度') && text().includes('按题型') && all('.summary-bars').length === 2);
  check('维度里没有已判分的显示「未判分」而不是 0%',
    all('.summary-bars')[0].textContent.includes('未判分'), all('.summary-bars')[0].textContent);
  check('题型标签走的是候选人侧的短名（单选 / 简答）',
    all('.summary-bars')[1].textContent.includes('单选') && all('.summary-bars')[1].textContent.includes('简答'),
    all('.summary-bars')[1].textContent);

  flags.stats = STATS_EMPTY;
  await go('#/candidate/stats');
  check('一次都没练过 → 空态而不是一堆 0',
    text().includes('还没有练习记录') && buttonIn(page(), '去刷题') !== undefined);
  flags.stats = STATS;

  /* ---------- 17. 正确率为 null 时显示「—」 ---------- */
  flags.stats = { ...STATS, accuracy: null, by_dimension: [{ dimension: '专业能力', answered: 2, scored: 0, correct: 0, accuracy: null }] };
  await go('#/candidate/stats');
  check('全部未判分时正确率显示「—」并说明原因',
    page().querySelector('.summary-cell .summary-value')?.textContent === '40'
      && text().includes('还没有已判分的作答'),
    text().includes('还没有已判分的作答') ? 'ok' : '缺说明');
  check('正确率为 null 时数字格里不是「0%」（0% 会被读成「全错」）',
    all('.summary-cell')[2].textContent.includes('—'), all('.summary-cell')[2].textContent);
  flags.stats = STATS;

  /* ---------- 18. 收尾 ---------- */
  check('没有残留的弹窗', openOverlay() === null);
});
