/**
 * 弹窗（module-07 §6）。
 * Esc 关闭；提交中禁用关闭 —— 避免重复提交。
 */

import { el, mount } from '../dom.js';

/**
 * 打开弹窗。
 * 返回 { close, setBusy, root }。
 */
export function openModal({ title, body, footer, wide = false, onClose }) {
  const overlay = el('div', { class: 'modal-overlay' });
  let busy = false;

  const close = () => {
    if (busy) return; // 提交中不允许关闭
    document.removeEventListener('keydown', onKeydown);
    overlay.remove();
    if (onClose) onClose();
  };

  const onKeydown = (event) => {
    if (event.key === 'Escape') close();
  };

  const panel = el(
    'div',
    { class: `modal${wide ? ' modal--wide' : ''}`, role: 'dialog', 'aria-modal': 'true' },
    el('div', { class: 'modal-head' }, el('div', { class: 'modal-title', text: title })),
    el('div', { class: 'modal-body' }, body),
    footer ? el('div', { class: 'modal-foot' }, footer) : null,
  );

  overlay.append(panel);
  overlay.addEventListener('mousedown', (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener('keydown', onKeydown);
  document.body.append(overlay);

  // 焦点进第一个可交互元素，键盘用户不必手动 Tab 进来
  const firstField = panel.querySelector('input, select, textarea, button');
  if (firstField) firstField.focus();

  return {
    root: panel,
    close,
    setBusy(value) {
      busy = value;
      overlay.querySelectorAll('button, input, select, textarea').forEach((node) => {
        node.disabled = value;
      });
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
