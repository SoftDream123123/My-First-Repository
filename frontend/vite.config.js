import { defineConfig } from 'vite';

/**
 * 开发期把 /api 代理到后端（module-07 §7）。
 *
 * 前端代码一律使用相对路径 /api/... —— 开发期走代理、构建产物部署到同域后
 * 路径不变，两种环境都不需要处理 CORS。后端的 CORS_ORIGINS 仍保留作兜底。
 */
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
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
