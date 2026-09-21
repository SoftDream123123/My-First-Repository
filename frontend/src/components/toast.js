/**
 * components/toast.js —— 消息提示
 * 文案一律来自后端 message，前端不重新编造。
 */

import { el } from '../dom.js';

let stack = null;

function ensureStack() {
  if (!stack) {
    stack = el('div', { class: 'toast-stack', role: 'status', 'aria-live': 'polite' });
    document.body.append(stack);
  }
  return stack;
}

function show(message, variant, duration) {
  const node = el('div', { class: `toast${variant ? ` toast--${variant}` : ''}` }, message);
  ensureStack().append(node);
  setTimeout(() => {
    node.style.opacity = '0';
    setTimeout(() => node.remove(), 200);
  }, duration);
}

export const toast = {
  info: (message) => show(message, null, 3000),
  success: (message) => show(message, 'success', 3000),
  error: (message) => show(message, 'error', 5000), // 失败留久一点，让人读完
};
