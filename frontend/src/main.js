/**
 * 应用启动（module-07 §3）。
 */

import { isLive, setUnauthorizedHandler } from './api.js';
import { start } from './router.js';
import { toast } from './components/toast.js';

// 统一 401 处理：清 token + 跳登录。页面不必各自处理。
setUnauthorizedHandler(() => {
  toast.error('登录状态已失效，请重新登录');
  location.hash = '#/login';
});

const app = document.getElementById('app');
if (!app) {
  throw new Error('找不到挂载点 #app');
}

start(app);

// 原型模式下给个明确提示，避免误以为已经接上后端
if (!isLive()) {
  console.info(
    '%c原型模式%c 数据来自内存 mock。接真实后端：访问任意页面时加 ?live=1，或执行 localStorage.setItem("prototype.live","1")',
    'background:#f2c744;color:#16202b;padding:2px 6px;border-radius:3px;font-weight:600',
    'color:#5e6c7a',
  );
}
