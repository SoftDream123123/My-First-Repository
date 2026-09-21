/**
 * components/form.js —— 字段级报错
 *
 * 前端本地校验与后端 400 的 `detail.fields` 走**同一条出口**：错误落在具体
 * 字段下方，而不是弹一句「请求参数不合法」让人猜是哪个字段错了。
 */

import { el } from '../dom.js';

export function fieldError() { return el('p', { class: 'field-error', hidden: true }); }

export function fieldErrors(nodes) {
  function show(field, message) {
    const node = nodes[field];
    if (!node) return false;
    node.textContent = message;
    node.hidden = false;
    return true;
  }

  return {
    show,
    clear() {
      for (const node of Object.values(nodes)) {
        node.textContent = '';
        node.hidden = true;
      }
    },
    /** 后端 400 → 落到具体字段。命中返回 true，调用方就不再弹通用 toast。 */
    fromServer(error) {
      const fields = error.detail?.fields;
      if (error.code !== 'VALIDATION_ERROR' || !Array.isArray(fields)) return false;
      let matched = false;
      for (const item of fields) if (show(item.field, item.message)) matched = true;
      return matched;
    },
  };
}
