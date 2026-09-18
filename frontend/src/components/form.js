/**
 * 表单字段级报错（API 文档 §12.1）。
 *
 * 前端本地校验与后端 400 的 `detail.fields` 走**同一条出口** —— 错误落在具体
 * 字段下方，而不是弹一句「请求参数不合法」让人猜是哪个字段错了。
 *
 * 出口只写一次，四个表单（登录 / 岗位 / 题库 / 面试）共用。
 */

import { el } from '../dom.js';

/** 字段下方的错误占位（默认隐藏）。 */
export function fieldError() {
  return el('p', { class: 'field-error', hidden: true });
}

/**
 * 把「请求体字段名 → 错误节点」的映射包成一个小工具。
 *
 * 字段名必须与后端 `detail.fields[].field` 一致
 * （`username` / `name` / `jd` / `content` / `candidate_name` …）。
 */
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

    /**
     * 后端 400 → 落到具体字段。命中返回 true，调用方就不再弹通用 toast
     * （同一个错误不说两遍）；非字段类错误（409 重名等）返回 false。
     */
    fromServer(error) {
      const fields = error.detail?.fields;
      if (error.code !== 'VALIDATION_ERROR' || !Array.isArray(fields)) return false;

      let matched = false;
      for (const item of fields) {
        if (show(item.field, item.message)) matched = true;
      }
      return matched;
    },
  };
}
