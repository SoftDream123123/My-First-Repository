/**
 * components/modal.js —— 弹窗
 *
 * Esc 关闭；提交中禁用「用户发起的关闭」—— 避免结果无处安放。
 *
 * ⚠️ `close()` 本身**不受 busy 影响**：请求成功后必须能关掉弹窗。
 * （这条是踩过的坑：早期版本让 close() 也在 busy 时直接 return，
 * 结果四个页面的创建/编辑弹窗在提交成功之后全都关不掉，只能刷新页面。）
 */

import { el } from '../dom.js';

export function openModal({ title, body, footer, wide = false, onClose }) {
  const overlay = el('div', { class: 'modal-overlay' });
  let busy = false;

  function onKeydown(event) { if (event.key === 'Escape') closeByUser(); }
  function dismiss() {
    document.removeEventListener('keydown', onKeydown);
    overlay.remove();
    if (onClose) onClose();
  }
  function closeByUser() { if (!busy) dismiss(); }

  const panel = el(
    'div',
    { class: `modal${wide ? ' modal--wide' : ''}`, role: 'dialog', 'aria-modal': 'true' },
    el('div', { class: 'modal-head' }, el('div', { class: 'modal-title', text: title })),
    el('div', { class: 'modal-body' }, body),
    footer ? el('div', { class: 'modal-foot' }, footer) : null,
  );

  overlay.append(panel);
  overlay.addEventListener('mousedown', (event) => { if (event.target === overlay) closeByUser(); });
  document.addEventListener('keydown', onKeydown);
  document.body.append(overlay);

  const firstField = panel.querySelector('input, select, textarea, button');
  if (firstField) firstField.focus();

  return {
    root: panel,
    close: dismiss,
    setBusy(value) {
      busy = value;
      overlay.querySelectorAll('button, input, select, textarea').forEach((node) => { node.disabled = value; });
    },
  };
}

/** 二次确认。返回 Promise<boolean>。 */
export function confirmModal({ title, message, confirmLabel = '删除', danger = true }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      handle.close();
      resolve(value);
    };
    const handle = openModal({
      title,
      body: el('p', { class: 'prose', text: message }),
      footer: [
        el('button', { class: 'btn btn--ghost', text: '取消', onClick: () => finish(false) }),
        el('button', {
          class: `btn ${danger ? 'btn--danger' : 'btn--primary'}`,
          text: confirmLabel,
          onClick: () => finish(true),
        }),
      ],
      onClose: () => finish(false),
    });
  });
}
