/**
 * pages/interview-detail.js —— 面试详情（核心屏）
 *
 * 布局上做了一处明确判断：不用「8 道题的长滚动列表」，而是
 * 「题目导航 + 单题编辑」。真实面试是一题一题走的，HR 需要随时知道
 * 「问到第几题了」，而不是在长页面里滚动找位置。
 */

import { el, mount, clear } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal } from '../components/modal.js';
import {
  contextTitle, createShell, emptyState, formatDate, formatDateTime, loadingBlock,
  panelHead, sourceTag, dimTag, statusRail,
} from '../components/shell.js';
import { navigate } from '../router.js';

const SAVE_LABELS = { idle: '未修改', saving: '保存中…', saved: '已保存', failed: '保存失败' };

const INVITE_LABELS = { pending: '待接受', accepted: '已接受', revoked: '已撤销', expired: '已过期' };
const INVITE_TAG = {
  pending: 'tag--ongoing', accepted: 'tag--evaluated', revoked: 'tag--off', expired: 'tag--evaluating',
};

/** 打开时定位到第一道未答的题 —— HR 关心的永远是「下一题是什么」。 */
function pickInitialIndex(questions) {
  const index = questions.findIndex((q) => !q.answer);
  return index === -1 ? 0 : index;
}

function copyCode(code) {
  let reported = false;
  const report = (message, variant) => {
    if (reported) return; // 超时回退与成功回调可能都跑，只报第一次
    reported = true;
    if (variant === 'error') toast.error(message); else toast.success(message);
  };
  const done = () => report('邀请码已复制');
  const failed = () => report('复制失败，请手工选中邀请码复制', 'error');

  // 无用户手势 / 未授权时 clipboard 的 Promise 可能**一直不落地**，
  // 不给超时就会「点了没反应」。退回 execCommand，不引入依赖。
  const legacy = () => {
    const box = el('textarea', { value: code, style: 'position:fixed;left:-9999px;top:0' });
    document.body.append(box);
    box.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch { copied = false; }
    box.remove();
    return copied ? done() : failed();
  };

  if (!(navigator.clipboard && navigator.clipboard.writeText)) { legacy(); return; }

  const timer = setTimeout(legacy, 1200);
  navigator.clipboard.writeText(code).then(
    () => { clearTimeout(timer); done(); },
    () => { clearTimeout(timer); legacy(); },
  );
}

export async function render(container, params) {
  const interviewId = params.id;
  const { root, main } = createShell(contextTitle('面试'));
  mount(container, root);
  mount(main, loadingBlock('正在加载面试…'));

  let detail;
  try {
    detail = await api.get(`/interviews/${interviewId}`);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('面试加载失败', error.message,
      el('button', { class: 'btn btn--primary', text: '返回列表', onClick: () => navigate('/interviews') }))));
    return;
  }

  if (!detail.questions.length) {
    mount(main, el('div', { class: 'panel' }, emptyState('这场面试没有题目',
      '题目在创建面试时生成。如果这里为空，说明出题那一步没有落库。')));
    return;
  }

  const editable = detail.status === 'ongoing';
  let currentIndex = pickInitialIndex(detail.questions);
  const saveStates = {};

  /* --------------------------- 状态操作 --------------------------- */

  /**
   * ⚠️ 评估页尚未搬进来，因此 `completed` / `evaluating` / `evaluated` 三态的
   * 「去评估 / 查看进度 / 查看报告」**暂时不渲染**。路由表里没有的路由不放在按钮上 ——
   * 点了只会「什么都没发生」。评估模块落地时把这三个按钮加回来。
   */
  async function transition(action, successMessage) {
    try {
      await api.post(`/interviews/${interviewId}/${action}`);
      toast.success(successMessage);
      render(container, params);
    } catch (error) {
      toast.error(error.message); // 状态机不允许的迁移，文案来自后端
    }
  }

  function buildActions() {
    if (detail.status === 'ongoing') {
      return [el('button', {
        class: 'btn btn--primary',
        text: '标记完成',
        onClick: () => transition('complete', '已标记完成'),
      })];
    }

    // completed 与 evaluated 都允许回退（evaluating 不允许 —— 后端状态机如此）
    if (detail.status === 'completed' || detail.status === 'evaluated') {
      return [el('button', {
        class: 'btn btn--ghost',
        text: '回退到进行中',
        onClick: () => transition('rollback', '已回退到进行中'),
      })];
    }

    return [];
  }

  /* ---------------------------- 题目导航 ---------------------------- */

  const navColumn = el('div', {});
  const editorColumn = el('div', {});
  const resumePanel = el('div', { class: 'panel' });
  const invitePanel = el('div', { class: 'panel' });

  function buildNav() {
    const answered = detail.questions.filter((q) => q.answer).length;
    return el(
      'aside',
      { class: 'qnav', 'aria-label': '题目导航' },
      el('div', { class: 'qnav-head' },
        el('span', { text: '题目' }),
        el('span', { class: 'qnav-count', text: `${answered} / ${detail.questions.length}` })),
      el('ol', { class: 'qnav-list' },
        detail.questions.map((question, index) =>
          el('li', {},
            el('button', {
              class: ['qnav-item',
                index === currentIndex ? 'is-current' : '',
                question.answer ? 'is-answered' : ''].filter(Boolean).join(' '),
              type: 'button',
              'aria-current': index === currentIndex ? 'true' : null,
              onClick: () => { currentIndex = index; repaint(); },
            },
              el('span', { class: 'qnav-num', text: String(question.seq) }),
              // 标题给完整题干：导航列放不下，但鼠标停一下要能看到
              el('span', { class: 'qnav-dim', text: question.dimension, title: question.content }),
              el('span', { class: 'qnav-mark', text: question.answer ? '已答' : '待答' }),
            ),
          ),
        )),
    );
  }

  /* ---------------------------- 单题编辑 ---------------------------- */

  function saveAnswer(question, textarea, stateNode) {
    saveStates[question.interview_question_id] = 'saving';
    stateNode.className = 'save-state is-saving';
    stateNode.textContent = SAVE_LABELS.saving;

    api.post(`/interviews/${interviewId}/answers`, {
      interview_question_id: question.interview_question_id,
      content: textarea.value,
    })
      .then((updated) => {
        question.answer = updated.answer;
        question.recorded_at = updated.recorded_at;
        question.answer_source = updated.answer_source;
        saveStates[question.interview_question_id] = 'saved';
        stateNode.className = 'save-state is-saved';
        stateNode.textContent = SAVE_LABELS.saved;
        // 只重画导航 —— 重画编辑区会把光标从输入框里踢出去
        clear(navColumn);
        navColumn.append(buildNav());
      })
      .catch((error) => {
        saveStates[question.interview_question_id] = 'failed';
        stateNode.className = 'save-state is-failed';
        stateNode.textContent = SAVE_LABELS.failed;
        toast.error(error.message);
      });
  }

  function buildEditor() {
    const question = detail.questions[currentIndex];
    const state = saveStates[question.interview_question_id] || 'idle';

    const stateNode = el('span', {
      class: `save-state${state === 'saved' ? ' is-saved' : ''}`,
      text: SAVE_LABELS[state],
    });

    const textarea = el('textarea', {
      class: 'textarea',
      id: 'answer-input',
      maxlength: '10000', // 与后端 content ≤ 10000 对齐
      placeholder: editable ? '边听边记。留空表示候选人未作答，评估时按 0 分处理。' : '',
      readOnly: !editable,
      value: question.answer ?? '',
    });

    if (editable) {
      // 失焦保存即可 —— 不做输入防抖，避免高频请求
      textarea.addEventListener('blur', () => {
        if (textarea.value === (question.answer ?? '')) return; // 没改就不发请求
        saveAnswer(question, textarea, stateNode);
      });
    }

    const actions = editable
      ? el('div', { class: 'editor-actions' },
          el('button', {
            class: 'btn btn--ghost',
            text: '保存回答',
            onClick: () => saveAnswer(question, textarea, stateNode),
          }),
          el('button', {
            class: 'btn btn--quiet',
            text: '清空',
            onClick: async () => {
              // 清空会立刻把已录入的回答存成空，且没有撤销 ——
              // 与删除岗位 / 题目一样属于「拿走东西」，先问一句
              const ok = await confirmModal({
                title: '清空这道题的回答？',
                message: '清空后会立即保存为空，等同于候选人未作答（评估按 0 分计）。原来的内容无法恢复。',
                confirmLabel: '清空',
              });
              if (!ok) return;
              textarea.value = '';
              saveAnswer(question, textarea, stateNode);
            },
          }),
          el('span', { class: 'hint', text: '离开输入框时会自动保存' }),
          el('span', { style: 'margin-left:auto' }, stateNode))
      : el('div', { class: 'editor-actions' },
          // 「评估中」不允许回退到进行中（后端状态机如此），所以这句话要对状态负责
          el('span', { class: 'hint', text: detail.status === 'evaluating'
            ? '评估进行中，回答已锁定；等评估结束后可回退到进行中再修改。'
            : '需先回退到进行中才能修改回答' }));

    return el('section', { class: 'editor' },
      el('div', { class: 'editor-head' },
        el('span', { class: 'editor-seq', text: String(question.seq) }),
        dimTag(question.dimension),
        sourceTag(question.source),
      ),

      el('p', { class: 'editor-question', text: question.content }),

      // 「为什么选这道题」只对按简历匹配来的题显示，普通题没有这个字段
      question.source === 'resume_match' && question.match_reason
        ? el('p', { class: 'match-reason' },
            el('b', { text: '为什么选这道题：' }),
            question.match_reason)
        : null,

      el('div', { class: 'editor-answer-head' },
        el('label', { class: 'field-label', for: 'answer-input', text: '候选人回答' }),
        el('span', { class: 'hint' },
          question.recorded_at ? `最后录入 ${formatDateTime(question.recorded_at)}` : ''),
      ),
      textarea,
      actions,

      el('div', { class: 'editor-pager' },
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '上一题',
          disabled: currentIndex === 0,
          onClick: () => { currentIndex -= 1; repaint(); },
        }),
        el('button', {
          class: 'btn btn--ghost btn--sm',
          text: '下一题',
          disabled: currentIndex === detail.questions.length - 1,
          onClick: () => { currentIndex += 1; repaint(); },
        }),
      ),
    );
  }

  /* ---------------------- 参考区：候选人简历 ---------------------- */

  async function runMatch(button) {
    // 补题会**累加**新题（「幂等」只指不产生重复题目），连点会追加多批 —— 必须防连点
    button.disabled = true;
    button.textContent = '匹配中…';
    try {
      const result = await api.post(`/interviews/${interviewId}/questions/match`);
      if (result.added_count === 0) {
        toast.info('未匹配到新的题目'); // 200，不是错误
      } else {
        // 必须报本场总数：只报增量时 HR 连点几次会以为界面在重复加同一批题
        toast.success(`本次新增 ${result.added_count} 题，本场共 ${result.total_questions} 题`);
      }
      render(container, params); // 重新拉详情，让新题与匹配理由出现在导航与编辑区
    } catch (error) {
      toast.error(error.message); // 409 / 502 都用后端文案
      button.disabled = false;
      button.textContent = '按简历补题';
    }
  }

  async function loadResume() {
    const canMatch = detail.status === 'ongoing' && detail.resume_id != null;
    const matchButton = el('button', {
      class: 'btn btn--ghost btn--sm',
      text: '按简历补题',
      disabled: !canMatch,
      title: detail.resume_id == null
        ? '该面试尚未关联简历'
        : detail.status !== 'ongoing' ? '当前状态不可补题' : '按候选人简历从题库再补几道题',
      onClick: () => runMatch(matchButton),
    });

    // 标题先立起来、正文随后填 —— 加载期间不该是一块没有名字的空白面板
    const body = el('div', {});
    clear(resumePanel);
    resumePanel.append(
      panelHead('候选人简历', detail.resume_id == null ? '尚未关联' : null, [matchButton]),
      body,
    );
    body.append(loadingBlock('正在读取简历…'));

    let resume = null;
    let failure = null;
    try {
      resume = await api.get(`/interviews/${interviewId}/resume`);
    } catch (error) {
      failure = error;
    }

    clear(body);

    if (failure && failure.status !== 404) {
      body.append(el('div', { class: 'panel-body' },
        el('p', { class: 'field-error', text: failure.message })));
      return;
    }
    if (!resume) {
      // 404 是「候选人还没做这件事」，不是「出问题了」—— 两者表现必须明显不同
      body.append(el('div', { class: 'panel-body' },
        el('p', { class: 'prose' }, '候选人尚未提交简历。候选人可在其端内录入并关联，之后可据此补充面试题。')));
      return;
    }

    body.append(
      el('div', { class: 'panel-body', style: 'padding-bottom:0' },
        el('div', { class: 'dossier-label', text: resume.title }),
        el('div', { class: 'dossier-meta' },
          resume.candidate_name ? el('span', { text: resume.candidate_name }) : null,
          resume.candidate_contact ? el('span', { text: resume.candidate_contact }) : null,
          // HR 据此判断手上这份是不是最新的（候选人改简历后需重新触发补题）
          el('span', { text: `最后更新 ${formatDateTime(resume.updated_at)}` })),
      ),
      el('p', { class: 'resume-body', text: resume.content }),
    );
  }

  /* ---------------------- 参考区：作答邀请 ---------------------- */

  async function revokeInvitation(invitation) {
    const ok = await confirmModal({
      title: '撤销这张邀请码？',
      message: invitation.status === 'accepted'
        ? '这位候选人已经接受了邀请。撤销会立刻切断他在候选人端对本场面试的访问 —— 这是收回访问权的唯一手段。'
        : '撤销后这张邀请码立即失效，不能再用于激活。已签发的其他邀请不受影响。',
      confirmLabel: '撤销',
    });
    if (!ok) return;
    try {
      await api.del(`/interviews/${interviewId}/invitations/${invitation.id}`);
      toast.success('邀请已撤销');
      loadInvitations();
    } catch (error) {
      toast.error(error.message);
    }
  }

  async function loadInvitations() {
    const canCreate = detail.status === 'ongoing';
    const createButton = el('button', {
      class: 'btn btn--primary btn--sm',
      text: '生成邀请码',
      disabled: !canCreate,
      title: canCreate ? '生成一张 7 天有效、一次性使用的邀请码' : '只有进行中的面试才能发邀请',
      onClick: async () => {
        createButton.disabled = true;
        createButton.textContent = '生成中…';
        try {
          await api.post(`/interviews/${interviewId}/invitations`);
          toast.success('邀请码已生成，复制后发给候选人');
          loadInvitations();
        } catch (error) {
          toast.error(error.message);
        } finally {
          createButton.disabled = false;
          createButton.textContent = '生成邀请码';
        }
      },
    });

    const body = el('div', {});
    clear(invitePanel);
    invitePanel.append(panelHead('作答邀请', null, [createButton]), body);
    body.append(loadingBlock('正在读取邀请…'));

    let invitations = [];
    try {
      invitations = await api.get(`/interviews/${interviewId}/invitations`);
    } catch (error) {
      clear(body);
      body.append(el('div', { class: 'panel-body' }, el('p', { class: 'field-error', text: error.message })));
      return;
    }

    clear(body);

    if (!invitations.length) {
      body.append(el('div', { class: 'panel-body' },
        el('p', { class: 'prose' }, canCreate
          ? '还没有邀请码。生成一张发给候选人，他就能在候选人端激活账号并在线作答。'
          : '这场面试没有发过邀请码。')));
      return;
    }

    body.append(el('div', {}, invitations.map((invitation) => {
      const actions = [];
      // 只有待接受的码值得复制 —— 已撤销/已过期的复制出去也用不了
      if (invitation.status === 'pending') {
        actions.push(el('button', {
          class: 'btn btn--quiet btn--sm', text: '复制', onClick: () => copyCode(invitation.code),
        }));
      }
      if (invitation.status !== 'revoked') {
        actions.push(el('button', {
          class: 'btn btn--quiet btn--sm', text: '撤销', onClick: () => revokeInvitation(invitation),
        }));
      }

      return el('div', { class: 'invite-item' },
        el('div', { class: 'invite-top' },
          el('span', { class: 'code', text: invitation.code }),
          el('span', {
            class: `tag ${INVITE_TAG[invitation.status] ?? 'tag--off'}`,
            text: INVITE_LABELS[invitation.status] ?? invitation.status,
          }),
          actions.length ? el('div', { class: 'invite-actions' }, actions) : null),
        el('div', { class: 'invite-meta' },
          el('span', { text: `创建于 ${formatDateTime(invitation.created_at)}` }),
          el('span', { text: `有效期至 ${formatDate(invitation.expires_at)}` }),
          invitation.accepted_at
            ? el('span', { text: `已接受${invitation.candidate_username ? ` · ${invitation.candidate_username}` : ''}（${formatDateTime(invitation.accepted_at)}）` })
            : null),
      );
    })));
  }

  /* ------------------------------- 组装 ------------------------------- */

  function repaint() {
    clear(navColumn);
    clear(editorColumn);
    navColumn.append(buildNav());
    editorColumn.append(buildEditor());
  }

  mount(
    main,
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
            : `创建于 ${formatDateTime(detail.created_at)}`),
      ),
      el('div', { class: 'page-head-actions' },
        el('button', { class: 'btn btn--ghost', text: '返回列表', onClick: () => navigate('/interviews') }),
        buildActions()),
    ),

    // 状态由状态轨表达，不再另加一个状态标签 —— 那会把同一件事说两遍
    statusRail(detail.status),

    el('div', { class: 'detail-layout' }, navColumn, editorColumn),
    el('div', { class: 'detail-extras' }, resumePanel, invitePanel),
  );

  repaint();
  loadResume();
  loadInvitations();
}
