/**
 * pages/candidate-resumes.js —— 我的简历
 *
 * 左索引 + 右案卷。简历正文是**一份文书**（纯文本粘贴、保留换行），所以右栏
 * 沿用案卷的读法，而不是把它塞进表格里截断。
 *
 * 关联动作（PRD §4.13）也放在这里：「这份简历用在哪几场面试上」是**这一份简历的
 * 属性**，所以与增删改查同处 —— 候选人不必先翻到某场面试才能接上。
 *
 * ⚠️ 本页依赖 `GET /candidate/interviews` 下发每场的 `resume_id`：
 * 没有它就只能盲勾，而且「解除关联」也无从判断该不该给。
 *
 * ⚠️ **正文字段绝不能加 `maxlength`**（module-22 §5.1）：`maxlength` 会让浏览器
 * **静默截断粘贴** —— 候选人以为整份简历存进去了，尾部其实已经丢了。这是最糟的
 * 一类数据丢失：无提示、不可察觉。改用「字数计数 + 超限禁用保存」。
 */

import { el, clear, mount } from '../dom.js';
import * as api from '../api.js';
import { toast } from '../components/toast.js';
import { confirmModal, openModal } from '../components/modal.js';
import { openResumeReview } from '../components/resume-review.js';
import { fieldError, fieldErrors } from '../components/form.js';
import {
  candidateStateTag, contextTitle, createShell, emptyState, formatDateTime, loadingBlock,
} from '../components/shell.js';

/**
 * 简历正文上限。
 *
 * ⚠️ **与后端 `RESUME_CONTENT_MAX_LENGTH` 保持一致，改一处必须改另一处** ——
 * 前端无法 import 后端配置，只能各写一份。与 `PASS_THRESHOLD`（6.5）同一处理方式，
 * 是本项目已有的先例；`resume-form.test.js` 里有一条守门断言把这个值钉住，
 * 至少让改动成为一个**需要显式修改测试的动作**，而不是静默漂移。
 */
export const RESUME_CONTENT_MAX_LENGTH = 20000;

/**
 * 正文长度状态。`length` **不做去空白** —— 计数要反映用户实际看到的长度。
 */
export function contentLengthState(content, maxLength = RESUME_CONTENT_MAX_LENGTH) {
  const length = String(content ?? '').length;
  return { length, over: length > maxLength };
}

/**
 * 能否提交。标题与正文都要求**去空白后非空**，正文长度另受上限约束。
 * 可选字段（姓名 / 联系方式）不参与判定。
 */
export function canSubmitResume({ title, content, maxLength = RESUME_CONTENT_MAX_LENGTH }) {
  const rawContent = String(content ?? '');
  return String(title ?? '').trim() !== ''
    && rawContent.trim() !== ''
    && rawContent.length <= maxLength;
}

/**
 * 上传文件的体积上限（字节），默认 5 MB。
 *
 * ⚠️ **与后端 `RESUME_UPLOAD_MAX_BYTES` 保持一致，改一处必须改另一处** ——
 * 与上面的 `RESUME_CONTENT_MAX_LENGTH` 同一处理方式（前端无法 import 后端配置），
 * `resume-form.test.js` 里有一条守门断言把这个值钉住。
 *
 * 为什么前端也要判：后端那道拦在**请求体已经收完之后**（Starlette 会先缓冲整个
 * 请求体），只有这一道能在请求**发出前**拦住大文件。
 */
export const RESUME_UPLOAD_MAX_BYTES = 5 * 1024 * 1024;

/** 体积判定。`over` 为真时应当**不发请求**，直接给文案。 */
export function uploadSizeState(fileSize, maxBytes = RESUME_UPLOAD_MAX_BYTES) {
  const size = Number(fileSize) || 0;
  return { size, over: size > maxBytes };
}

/**
 * 由文件名推出简历标题：去掉最后一个扩展名并去首尾空白。
 *
 * `"简历.docx"` → `"简历"`；`"a.b.c.pdf"` → `"a.b.c"`；`"无扩展名"` → 原样；
 * 空 / `null` → `''`。不做文件名清洗 —— 浏览器给的 `File.name` 已是纯名称，
 * 且它只会被写进 `title` 字段（后端还有 100 字符上限与去空白校验兜底）。
 */
export function titleFromFilename(filename) {
  const name = String(filename ?? '').trim();
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(0, dot).trim() : name;
}

/* --------------------------- 新建 / 编辑 --------------------------- */

/** 实时字数：越界立刻变红并禁用保存 —— 硬上限不能等提交被拒才知道。 */
function charCount(textarea, save) {
  const node = el('span', { class: 'char-count' });
  function paint() {
    const state = contentLengthState(textarea.value);
    node.textContent = `${state.length} / ${RESUME_CONTENT_MAX_LENGTH}`;
    node.className = `char-count${state.over ? ' is-over' : ''}`;
    // **只**在超限时禁用：标题或正文为空时保持可点，好让点下去能落到字段级报错
    // 上（禁用会把「为什么不能提交」这句话一起藏掉）
    save.disabled = state.over;
  }
  textarea.addEventListener('input', paint);
  paint();
  return node;
}

function resumeModal(resume, onDone) {
  const title = el('input', {
    class: 'input', id: 'resume-title', maxlength: '100', value: resume?.title ?? '',
  });
  const titleError = fieldError();
  const name = el('input', {
    class: 'input', id: 'resume-name', maxlength: '100', value: resume?.candidate_name ?? '',
  });
  const nameError = fieldError();
  const contact = el('input', {
    class: 'input', id: 'resume-contact', maxlength: '200',
    value: resume?.candidate_contact ?? '',
  });
  const contactError = fieldError();
  const content = el('textarea', {
    class: 'textarea textarea--tall', id: 'resume-content', value: resume?.content ?? '',
  });
  const contentError = fieldError();
  const errors = fieldErrors({
    title: titleError,
    content: contentError,
    candidate_name: nameError,
    candidate_contact: contactError,
  });

  const save = el('button', {
    class: 'btn btn--primary',
    text: resume ? '保存修改' : '创建简历',
  });
  const counter = charCount(content, save);

  /* --------------------------- 从文件导入 --------------------------- */
  // 解析出的文字只是**填进正文框**，还要候选人点保存才算数 —— 这一步刻意做成
  // 「导入 + 确认」，而不是「上传即建简历」：解析免不了有噪声，得让人过一眼。

  const fileInput = el('input', { type: 'file', id: 'resume-file', accept: '.docx,.pdf', hidden: true });
  const upload = el('button', { class: 'btn btn--sm', type: 'button', text: '上传文件' });

  upload.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    // 超限就**根本不发请求** —— 这是唯一能在请求发出前拦住大文件的地方
    if (uploadSizeState(file.size).over) {
      toast.error(`文件不能超过 ${RESUME_UPLOAD_MAX_BYTES / (1024 * 1024)} MB`);
      fileInput.value = '';
      return;
    }

    upload.disabled = true;
    upload.textContent = '解析中…';
    try {
      const form = new FormData();
      form.append('file', file);
      const parsed = (await api.postForm('/candidate/resumes/parse', form)).content;

      const keep = !String(content.value).trim() || await confirmModal({
        title: '替换当前正文',
        message: '正文框里已经有内容了，导入会把它们整体替换掉。确定吗？',
        confirmLabel: '替换',
        danger: false,
      });
      if (keep) {
        content.value = parsed;
        // ⚠️ 必须手动派发 input：字数计数与「超限禁用保存」都是事件驱动的
        // （`charCount` 里 addEventListener('input', ...)）。直接赋值不会触发，
        // 后果是计数器仍显示旧值、保存按钮不禁用 —— 候选人能提交一份超长正文，
        // 然后在提交时吃一个 422。
        content.dispatchEvent(new Event('input', { bubbles: true }));

        // 标题为空才填：已有内容一律不动（与正文的替换确认是两件独立的事）
        if (!String(title.value).trim()) title.value = titleFromFilename(file.name);

        const { length, over } = contentLengthState(parsed);
        if (over) {
          toast.error(`已解析出 ${length} 字，超过 ${RESUME_CONTENT_MAX_LENGTH} 字上限，请精简后再保存`);
        } else {
          toast.success(`已从文件解析出 ${length} 字，请确认后保存`);
        }
      }
    } catch (error) {
      toast.error(error.message);
    } finally {
      upload.disabled = false;
      upload.textContent = '上传文件';
      // 同一个文件连选两次（第一次失败后重试）时浏览器不会触发 change ——
      // value 没变。清空才能让第二次选择生效。
      fileInput.value = '';
    }
  });

  const handle = openModal({
    title: resume ? '编辑简历' : '新建简历',
    wide: true,
    body: el('div', {},
      el('div', { class: 'field' },
        el('label', { class: 'field-label', for: 'resume-title', text: '标题' }),
        title,
        el('p', { class: 'field-note', text: '给自己认的，比如「后端开发 · 主投版」。' }),
        titleError),

      el('div', { class: 'form-grid' },
        el('div', { class: 'field' },
          el('label', { class: 'field-label', for: 'resume-name', text: '姓名（可选）' }),
          name,
          nameError),
        el('div', { class: 'field' },
          el('label', { class: 'field-label', for: 'resume-contact', text: '联系方式（可选）' }),
          contact,
          contactError)),

      el('div', { class: 'field' },
        el('div', { class: 'field-head' },
          el('label', { class: 'field-label', for: 'resume-content', text: '简历正文' }),
          counter),
        content,
        el('p', {
          class: 'field-note',
          text: '直接粘贴纯文本，换行会原样保留。',
        }),
        el('div', { class: 'upload-row' },
          upload,
          fileInput,
          el('span', {
            class: 'upload-hint',
            text: `也可以上传 DOCX / PDF 解析出文字（不超过 ${RESUME_UPLOAD_MAX_BYTES / (1024 * 1024)} MB）`,
          })),
        contentError)),
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      save,
    ],
  });

  save.addEventListener('click', async () => {
    errors.clear();
    if (!String(title.value).trim()) { errors.show('title', '请填写标题'); title.focus(); return; }
    if (!String(content.value).trim()) { errors.show('content', '简历正文不能为空'); content.focus(); return; }
    if (contentLengthState(content.value).over) {
      errors.show('content', `简历正文不能超过 ${RESUME_CONTENT_MAX_LENGTH} 字符`);
      content.focus();
      return;
    }

    const body = {
      title: String(title.value).trim(),
      content: content.value,
      // ⚠️ 可选字段空输入提交**空串而不是 null**：`PUT` 是部分更新语义，
      // `null` 表示「不改」（API 文档 §11.4）—— 提交 null 的话，用户清空
      // 姓名/联系方式不会生效，而且界面上看不出为什么
      candidate_name: String(name.value).trim(),
      candidate_contact: String(contact.value).trim(),
    };
    handle.setBusy(true);
    try {
      if (resume) await api.put(`/candidate/resumes/${resume.id}`, body);
      else await api.post('/candidate/resumes', body);
      handle.close();
      toast.success(resume ? '已保存' : '已创建');
      onDone();
    } catch (error) {
      handle.setBusy(false);
      // 400 落到具体字段；422（正文超长，本地校验失效时的兜底）由后端给整句文案
      if (!errors.fromServer(error)) toast.error(error.message);
    }
  });
}

/* ------------------------------ 删除 ------------------------------ */

async function removeResume(resume, onDone) {
  const ok = await confirmModal({
    title: '删除这份简历？',
    message: `《${resume.title}》删除后无法恢复。它如果已经被面试或练习关联，删除会被拒绝。`,
    confirmLabel: '删除',
  });
  if (!ok) return;
  try {
    await api.del(`/candidate/resumes/${resume.id}`);
    toast.success('已删除');
    onDone();
  } catch (error) {
    toast.error(error.message); // 409 的文案来自后端（被引用不可删），前端不重编
  }
}

/* ---------------------------- 用于面试 ----------------------------
   一场面试只挂一份简历，因此「这份用在哪几场」只能一场一次 PUT（PRD §4.13）。
   勾上 = 本场改用这份；取消勾 = 本场不用简历 —— 但**只在这一场当前用的确实是
   这份时**才给取消（用着别的简历时，改由那一份的「用于面试」去换，否则会误把
   别人的关联解除掉）。 */

function useForInterviewsModal(resume, interviews, resumes, onDone) {
  const changed = new Map();
  const body = el('div', {});

  if (!interviews.length) {
    body.append(emptyState('还没有可关联的面试',
      '被邀请并接受之后，那场面试才会出现在这里。'));
  }

  for (const interview of interviews) {
    const linked = interview.resume_id ?? null;
    const isMine = linked === resume.id;
    const other = linked != null && !isMine ? resumes.find((r) => r.id === linked) : null;
    const frozen = interview.status !== 'ongoing';

    let note;
    if (frozen) note = '本场面试已结束，关联已冻结';
    else if (isMine) note = '本场现在用的就是这份简历';
    else if (other) note = `本场现在用的是《${other.title}》`;
    else note = '本场还没有关联简历';

    const box = el('input', { type: 'checkbox', checked: isMine, disabled: frozen });
    const row = el('label', { class: `pick-row${isMine ? ' is-picked' : ''}` },
      box,
      el('div', { class: 'pick-row-body' },
        el('div', { class: 'pick-row-title', text: interview.position_name }),
        el('div', { class: 'pick-row-note', text: note })));

    if (!frozen) {
      box.addEventListener('change', () => {
        row.classList.toggle('is-picked', box.checked);
        changed.set(interview.id, box.checked ? resume.id : null);
      });
    }
    body.append(row);
  }

  const save = el('button', { class: 'btn btn--primary', text: '保存' });
  const handle = openModal({
    title: '这份简历用在哪些面试？',
    body,
    footer: [
      el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => handle.close() }),
      save,
    ],
  });

  save.addEventListener('click', async () => {
    if (!changed.size) { handle.close(); return; }
    handle.setBusy(true);
    try {
      for (const [interviewId, resumeId] of changed) {
        // 解除时必须**显式提交 `{"resume_id": null}`** —— 该字段是必填的，
        // 靠省略字段表达「解除」会被后端判成缺字段 400（API 文档 §10.7）
        await api.put(`/candidate/interviews/${interviewId}/resume`, { resume_id: resumeId });
      }
      handle.close();
      // 中性措辞：解除关联时「已关联简历」那句话就成了错话，因此不带方向
      toast.success('已更新关联');
    } catch (error) {
      // 逐场提交，中途失败会留下**部分成功**。关掉弹窗并重载，让界面与事实一致 ——
      // 比留着勾选状态更不容易让人误判「已经生效」
      handle.close();
      toast.error(error.message);
    }
    onDone();
  });
}

/* ------------------------------ 页面 ------------------------------ */

export async function render(container) {
  const { root, main } = createShell(contextTitle('我的简历'));
  mount(container, root);
  mount(main, loadingBlock('正在加载你的简历…'));

  let resumes = [];
  let interviews = [];
  try {
    // 「用于面试」要拿每场的 resume_id 才能回显与解除，因此两份一起取
    [resumes, interviews] = await Promise.all([
      api.get('/candidate/resumes'),
      api.get('/candidate/interviews'),
    ]);
  } catch (error) {
    mount(main, el('div', { class: 'panel' }, emptyState('加载失败', error.message,
      el('button', {
        class: 'btn btn--primary',
        text: '重新加载',
        onClick: () => render(container),
      }))));
    return;
  }

  let currentId = resumes.length ? resumes[0].id : null;
  const reload = () => render(container);
  const newButton = (cls) => el('button', {
    class: cls,
    text: '新建简历',
    onClick: () => resumeModal(null, reload),
  });

  const head = el('div', { class: 'page-head' },
    el('div', {},
      el('h1', { text: '我的简历' }),
      el('p', { class: 'page-lede' },
        '简历只由你自己录入。招聘方看不到任何简历，除非你把某一份关联到那场面试 —— 关联之后，对方才能按它补题。')),
    el('div', { class: 'page-head-actions' }, newButton('btn btn--primary')));

  if (!resumes.length) {
    mount(main, head, el('div', { class: 'panel' }, emptyState(
      '还没有简历',
      '把简历正文粘贴进来就行（纯文本，不做文件上传）。关联到面试后招聘方才能按它补题，刷题时也能按它推荐题目。',
      newButton('btn btn--primary'))));
    return;
  }

  const listBody = el('div', { class: 'split-list-body' });
  const dossier = el('div', { class: 'panel' });
  const split = el('div', { class: 'split' },
    el('div', { class: 'split-list' }, listBody), dossier);

  const usedBy = (resumeId) => interviews.filter((i) => i.resume_id === resumeId);

  function paintList() {
    clear(listBody);
    for (const resume of resumes) {
      const used = usedBy(resume.id);
      listBody.append(el('button', {
        class: `split-item${resume.id === currentId ? ' is-active' : ''}`,
        type: 'button',
        onClick: () => { currentId = resume.id; paintList(); paintDossier(); },
      },
        el('div', { class: 'split-item-name', text: resume.title }),
        el('div', {
          class: 'split-item-meta',
          text: `${used.length ? `用于 ${used.length} 场面试` : '尚未用于面试'} · 更新于 ${formatDateTime(resume.updated_at)}`,
        })));
    }
  }

  function paintDossier() {
    clear(dossier);
    const resume = resumes.find((r) => r.id === currentId);
    if (!resume) {
      dossier.append(emptyState('请选择一份简历', '左侧选中后，这里显示它的正文与关联情况。'));
      return;
    }
    const used = usedBy(resume.id);

    dossier.append(
      el('div', { class: 'dossier-head' },
        el('div', {},
          el('h2', { class: 'dossier-title', text: resume.title }),
          el('div', { class: 'dossier-meta' },
            resume.candidate_name ? el('span', { text: resume.candidate_name }) : null,
            resume.candidate_contact ? el('span', { text: resume.candidate_contact }) : null,
            el('span', { text: `更新于 ${formatDateTime(resume.updated_at)}` }))),
        el('div', { class: 'dossier-actions' },
          el('button', { class: 'btn btn--ghost', text: '编辑', onClick: () => resumeModal(resume, reload) }),
          el('button', {
            class: 'btn btn--ghost',
            text: '用于面试',
            onClick: () => useForInterviewsModal(resume, interviews, resumes, reload),
          }),
          el('button', { class: 'btn btn--ghost', text: '删除', onClick: () => removeResume(resume, reload) }))),

      el('div', { class: 'dossier-section' },
        el('div', { class: 'dossier-label', text: '用于面试' }),
        used.length
          ? el('div', {}, used.map((interview) => {
              // 入口放在这里而不是候选人答题页：简历的关联与查看本来就都在本页
              // （F9/F10 的既定决定），评估是「这份简历用在那场岗位」的属性，
              // 放进答题页会让同一件事有两个入口。
              //
              // 不需要前置禁用：这一行只在已关联时存在。唯一可能的 409 是
              // 「岗位未定义评估维度」，那是部署配置问题，前端无从预知 ——
              // 原样报出来比猜一个禁用态更诚实。
              const reviewButton = el('button', {
                class: 'btn btn--ghost btn--sm',
                text: '评估匹配度',
                title: 'AI 评估这份简历与该场岗位的匹配度（每次点击重新评估，结果不保存）',
                // 把按钮本身交给弹窗管忙态：每次评估都真调一次 AI，连点就是几次调用
                onClick: () => openResumeReview({
                  interviewId: interview.id, side: 'candidate', button: reviewButton,
                }),
              });
              return el('div', { class: 'used-row' },
                el('span', { class: 'used-row-name', text: interview.position_name }),
                candidateStateTag(interview),
                reviewButton);
            }))
          : el('p', { class: 'meta', text: '还没有关联到任何面试。点上面的「用于面试」挑一场。' })),

      el('div', { class: 'dossier-section' },
        el('div', { class: 'dossier-label', text: '简历正文' }),
        el('p', { class: 'dossier-text', text: resume.content })));
  }

  paintList();
  paintDossier();
  mount(main, head, split);
}
