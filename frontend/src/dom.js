/**
 * dom.js —— 极简 DOM 助手
 *
 * 存在的理由是把「后端文本一律经 textContent 写入」这条约束结构化：
 * 代码里根本不提供写 HTML 的入口，想犯错都没有路径。
 * 全工程 `innerHTML` 出现 0 次 —— 这不是靠自觉，是没有入口。
 */

/** el('div', { class: 'panel', text: '题干' }, child1, child2) */
export function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = String(value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node && key !== 'list') node[key] = value;
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

/** 递归追加子节点，自动跳过 null / undefined / false。 */
export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(node) { node.replaceChildren(); return node; }

export function mount(container, ...children) {
  clear(container);
  append(container, children);
  return container;
}
