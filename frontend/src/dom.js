/**
 * 极简 DOM 助手。
 *
 * 存在的理由是把 module-07 §6 的 XSS 约束结构化：
 * 所有来自后端的文本一律经 textContent 写入，代码里根本不提供
 * "setHTML" 这类入口，想犯错都没有路径。
 */

/**
 * 创建元素。
 *   el('div', { class: 'panel', text: '题干' }, child1, child2)
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined) continue;

    if (key === 'class') {
      node.className = value;
    } else if (key === 'text') {
      // 唯一的文本写入路径 —— 永远不解析为 HTML
      node.textContent = String(value);
    } else if (key === 'dataset') {
      Object.assign(node.dataset, value);
    } else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node && key !== 'list') {
      node[key] = value;
    } else {
      node.setAttribute(key, String(value));
    }
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

/** 清空容器。 */
export function clear(node) {
  node.replaceChildren();
  return node;
}

/** 渲染到容器。 */
export function mount(container, ...children) {
  clear(container);
  append(container, children);
  return container;
}

/** 片段，用于条件渲染。 */
export function frag(...children) {
  const f = document.createDocumentFragment();
  append(f, children);
  return f;
}

/** 条件：cond 为真时返回节点，否则返回 null。 */
export function when(cond, node) {
  return cond ? node : null;
}
