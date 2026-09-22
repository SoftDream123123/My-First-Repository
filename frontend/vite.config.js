import { defineConfig } from 'vite';

/**
 * 开发期把 /api 代理到后端（module-07 §7）。
 *
 * 前端代码一律使用相对路径 /api/... —— 开发期走代理、构建产物部署到同域后
 * 路径不变，两种环境都不需要处理 CORS。后端的 CORS_ORIGINS 仍保留作兜底。
 *
 * 两处 127.0.0.1 是**刻意写死的**，不要改回 localhost：
 *   1. `server.host` —— Vite 默认 host 是 localhost，Node 会把它解析成 IPv6 的
 *      `::1` 并**只监听那一个地址**。后果是 `http://127.0.0.1:5173` 浏览器直接
 *      连不上，且本机上装了系统级代理（127.0.0.1:7890）的工具——包括 Python 的
 *      httpx——会把请求交给代理，而代理连不到 IPv6 回环，于是统统拿到 502。
 *   2. `proxy.target` —— 同理，避免 Node 把 localhost 解析成 ::1，而后端 uvicorn
 *      只监听 IPv4 的 127.0.0.1。
 * 两边都写死 IPv4，地址解析不再依赖运行时的 DNS 偏好。
 */
export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  // 下面这段由 Vitest 读取（Vite 本身忽略未知的顶层键），
  // 因此 `npm run dev` 不需要 vitest 参与，`npm test` 也不需要单独一份配置。
  test: {
    // 只测纯函数（SSE 分帧解析、雷达图几何）—— 无需 DOM 环境
    include: ['src/__tests__/**/*.test.js'],
  },
});
