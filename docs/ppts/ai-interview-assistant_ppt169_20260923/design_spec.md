# AI 智能面试助手 · 技术解构 — Design Spec

> Human-readable design narrative — rationale, audience, style, color choices, content outline. Read once by downstream roles for context.
>
> Machine-readable execution contract: `spec_lock.md` (color / typography / icon / image short form). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep both in sync; on divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | ai-interview-assistant |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 35 pages |
| **Design Style** | B) General Consulting + engineering-grade technical |
| **Target Audience** | IT 行业技术评审（面试官 / 架构评审 / 团队交接）—— 懂 Web 后端，但不熟悉本项目 |
| **Use Case** | 技术答辩 / 项目汇报 / 团队交接宣讲，投影与屏幕阅读 |
| **Created Date** | 2026-09-23 |
| **Source Documents** | `sources/2026-09-15-ai-interview-assistant-mvp-design.md`（PRD）、`sources/产品说明书.md`、`sources/README.md`，以及仓库内 `docs/superpowers/specs/` 30 份模块计划书与 `backend/app/**` 实际源码 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 左右 64px，上下 48px |
| **Content Area** | 1152×624（标题区 1152×88，正文区 1152×496，页脚区 1152×40） |

---

## III. Visual Theme

### Theme Style

- **Style**: B) General Consulting + engineering-grade technical
- **Theme**: Light theme
- **Tone**: 克制、精密、工程感。信息密度优先，用留白与 1px 分隔线组织版面，而非成片的圆角卡片。
  全场视觉由**自有矢量图形**承担：序列图、架构图、流程图、状态机、表结构、源码块。

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | 页面底色 |
| **Secondary bg** | `#F2F6FA` | 卡片底、代码块底、表头行 |
| **Deep bg** | `#0B2E52` | 章节页底色（深墨蓝） |
| **Primary** | `#1565C0` | 页标题、结构线、图标主体、流程节点 |
| **Primary light** | `#E3EDF9` | 主色的浅色填充（标签底、泳道底） |
| **Accent** | `#F57C00` | 关键数据、重点数字、强调标注 |
| **Secondary accent** | `#00897B` | 次级强调、渐变过渡、对照第二系列 |
| **Body text** | `#1F2733` | 正文 |
| **Secondary text** | `#5A6B7D` | 注释、图注、表内说明 |
| **Tertiary text** | `#93A1B0` | 页脚、页码、源标注 |
| **Text on deep** | `#EAF2FB` | 深色章节页上的文字 |
| **Border/divider** | `#DCE5EE` | 卡片边、分隔线、表格线 |
| **Success** | `#2E7D32` | **「解法 / 验证通过」语义色** |
| **Warning** | `#C62828` | **「问题 / 缺陷」语义色** |

> **配色语义（本套的核心约定）**：第 ④ 段反复出现「遇到什么问题 / 如何解决」。
> 全篇固定 **问题 = `#C62828`（红）、解法 = `#2E7D32`（绿）**，跨页一致，读者一眼可辨。
> 此约定优先于 60-30-10 的角色分配；除这一对语义色外，单页彩色 ≤4 种。
> 正文对比度 ≥ 4.5:1（`#1F2733` on `#FFFFFF` ≈ 14.6:1；`#5A6B7D` on `#FFFFFF` ≈ 5.2:1）。

### Gradient Scheme

```xml
<!-- 章节页深底渐变 -->
<linearGradient id="deepGradient" x1="0%" y1="0%" x2="100%" y2="100%">
  <stop offset="0%" stop-color="#0B2E52"/>
  <stop offset="100%" stop-color="#1565C0"/>
</linearGradient>

<!-- 页眉装饰（浅色页） -->
<linearGradient id="headerRule" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#1565C0"/>
  <stop offset="100%" stop-color="#1565C0" stop-opacity="0"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: modern CJK sans（同族 + 字重对比）+ 等宽代码。单一无衬线族保证密集技术版面内聚、投影清晰；`Consolas` 承载源码与标识符。

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei", "PingFang SC"` | — | `sans-serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Arial`（加粗 700） | `sans-serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks** (CSS `font-family` strings, one per role):

- Title: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: same as Body（靠 `font-weight` 700 而非换族实现强调）
- Code: `Consolas, Courier New, monospace`

> **Stack ordering rationale**: 本套是 **CJK 主导**的技术文档（几乎每个标注都是中文），
> 因此中文字体族前置 —— 拉丁字形走 Microsoft YaHei 的内置拉丁，与中文同源同调，
> 不会在「中文句中夹英文标识符」时出现两套拉丁字形打架。`Arial` 仅作缺失兜底。
> 所有字体均为 Windows/macOS 预装，PPTX 无运行时回退风险。

### Font Size Hierarchy

**Baseline**: Body font size = **18px**（密集档 —— 本套每页信息点普遍 6 条以上，且第 ④ 段含源码与表结构）

| Purpose | Ratio to body | Current Project | Weight |
| ------- | ------------- | --------------- | ------ |
| Cover title (hero headline) | 2.5-5x | **64px** | Bold 700 |
| Chapter / section opener | 2-2.5x | **44px** | Bold 700 |
| Page title | 1.5-2x | **32px** | Bold 700 |
| Hero number (KPI) | 1.5-2x | **36px** | Bold 700 |
| Subtitle / lead | 1.2-1.5x | **24px** | SemiBold 600 |
| **Body content** | **1x** | **18px** | Regular 400 |
| Code block | 0.7-0.85x | **14px** | Regular 400 |
| Annotation / caption | 0.7-0.85x | **14px** | Regular 400 |
| Chart annotation | 0.7-0.85x | **13px** | Regular 400 |
| Page number / footnote | 0.5-0.65x | **11px** | Regular 400 |

---

## V. Layout Principles

### Page Structure

- **Header area**: 高 88px —— 页标题（32px）+ 主色下划线（3px，宽至内容区右缘渐隐）+ 右上角当前章节名（14px，`#93A1B0`）
- **Content area**: 高 496px —— 承载全部正文、图表、序列图、代码块
- **Footer area**: 高 40px —— 左：项目名（11px `#93A1B0`）；右：页码 `P/35`（11px `#93A1B0`）；中间可放 `#DCE5EE` 分隔线

### Layout Pattern Library (combine or break as content demands)

| Pattern | Suitable Scenarios |
| ------- | ----------------- |
| **Single column centered** | 封面、结语、单一论点页 |
| **Symmetric split (5:5)** | 问题 ↔ 解法对照、对照两组状态 |
| **Asymmetric split (3:7 / 2:8)** | 序列图/架构图为主 + 右侧阅读注释 |
| **Top-bottom split** | 上方流程图 + 下方要点、代码块 + 说明 |
| **Three/four column cards** | 平行能力点、技术栈、模块概览 |
| **Matrix grid (2×2)** | 双轴分类 |
| **Z-pattern / waterfall** | 问题 → 解法的手递手叙事（第 ④ 段反复使用） |
| **Center-radiating** | 核心概念 + 周边节点（模块依赖） |
| **Full-bleed + floating text** | 章节页（深底 + 浮层文字） |
| **Negative-space-driven** | 关键结论页 —— 一个论点 + 大量留白 |

> **节奏纪律**：本套是**密集技术文档**，绝大多数页为 `dense`。`breathing` 只出现在
> 5 处章节过渡页与 1 处结语页 —— 它们是真实的叙事停顿，不是凑数。**不得**在内容页
> 为了提高「呼吸感」而砍掉必要信息。

### Spacing Specification

**Universal**:

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Safe margin from canvas edge | 40-60px | 左右 64px / 上下 48px |
| Content block gap | 24-40px | 28px |
| Icon-text gap | 8-16px | 10px |

**Card-based layouts** (仅 `dense` 页使用):

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Card gap | 20-32px | 24px |
| Card padding | 20-32px | 24px |
| Card border radius | 8-16px | 8px |
| Single-row card height | 530-600px | 480px（内容区上限，留页脚） |
| Double-row card height | 265-295px each | 232px each |
| Three-column card width | 360-380px each | 358px each（含 16px 间隙） |

**Non-card containers** (`breathing` 页 / 深底章节页):

- 垂直节奏由**留白**承担，块间距放宽到 40-56px
- **Line-height**: 1.5× 正文字号（18px → 行高 27px）
- 深色章节页文字内缩，避让装饰性几何元素
- 面板造型：**白底 + 1px `#DCE5EE` 边 + 8px 圆角，无投影**。只有真正浮起的层（无）才用投影 —— 本套**不使用任何投影**

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `templates/icons/tabler-outline/`（描边风格，5037 个）
- **Chosen stylistic library**: `tabler-outline`，**stroke-width 固定 `2`**（全篇统一）
- **Brand library**: `simple-icons` —— **仅用于第 ③ 段技术栈页的真实品牌标识**（Python / FastAPI / MySQL / Vite / JavaScript 等）。不可用于任何通用图标。
- **Usage method**: SVG placeholder `<use data-icon="tabler-outline/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| 项目概览 / 总览 | `tabler-outline/dashboard` | P04, P18 |
| 发展历程 / 时间轴 | `tabler-outline/history` | P06 |
| 版本里程碑 | `tabler-outline/flag-3` | P06, P35 |
| 痛点 / 缺陷 | `tabler-outline/alert-triangle` | P04, P34 |
| 缺陷 / Bug | `tabler-outline/bug` | P26, P28, P30, P32 |
| 目标 / 定位 | `tabler-outline/target` | P04, P07 |
| 三类角色 | `tabler-outline/users` | P04, P31 |
| 角色权限 | `tabler-outline/user-shield` | P31 |
| 候选人账号 | `tabler-outline/user-check` | P10, P31 |
| HR / 岗位 | `tabler-outline/briefcase` | P04, P09 |
| 业务线 / 路由 | `tabler-outline/route` | P05, P11 |
| 演进 / 分支 | `tabler-outline/git-branch` | P06 |
| 依赖树 | `tabler-outline/binary-tree` | P16 |
| 分层 / 栈 | `tabler-outline/stack-2` | P15 |
| 层级 | `tabler-outline/layers-intersect` | P15 |
| 模块 / 包 | `tabler-outline/package` | P16, P19 |
| 组件 | `tabler-outline/puzzle` | P16 |
| 盒子 / 容器 | `tabler-outline/box` | P17 |
| AI 能力 | `tabler-outline/robot` | P20, P21 |
| AI 生成 | `tabler-outline/sparkles` | P20 |
| 模型 / 推理 | `tabler-outline/brain` | P21 |
| 模块结构 | `tabler-outline/sitemap` | P16 |
| 数据库 | `tabler-outline/database` | P14, P17 |
| 数据表 | `tabler-outline/table` | P17 |
| 图表 / 报告 | `tabler-outline/chart-bar` | P18 |
| 雷达图 | `tabler-outline/chart-radar` | P17, P24 |
| 流式 / SSE | `tabler-outline/wave-sine` | P24, P25 |
| 活动 / 心跳 | `tabler-outline/activity` | P24, P26 |
| 前瞻 / 展望 | `tabler-outline/telescope` | P35 |
| 增长 / 启动 | `tabler-outline/rocket` | P33, P35 |
| 重新评估 / 幂等 | `tabler-outline/refresh` | P21, P23, P26 |
| 重判 / 重试 | `tabler-outline/refresh-dot` | P23, P30 |
| 文件 / 简历 | `tabler-outline/file-text` | P29 |
| PDF 文件 | `tabler-outline/file-type-pdf` | P29, P30 |
| 上传 | `tabler-outline/upload` | P29 |
| 打印 / 导出 PDF | `tabler-outline/printer` | P29 |
| 下载 / 导出 DOCX | `tabler-outline/file-download` | P29 |
| 测试清单 | `tabler-outline/checklist` | P18, P33 |
| 测试管道 | `tabler-outline/test-pipe` | P18 |
| 实验 / 验证 | `tabler-outline/flask` | P18, P33 |
| 分支流程 | `tabler-outline/arrows-split` | P11 |
| 配置 | `tabler-outline/settings` | P14 |
| 调参 / 旋钮 | `tabler-outline/adjustments` | P14 |
| 代码 | `tabler-outline/code` | P14, P20, P22 |
| 代码块 | `tabler-outline/codeblock` | P20, P22, P24, P27, P29, P31 |
| 服务 / 后端 | `tabler-outline/server` | P14, P15 |
| 事务 / 已提交 | `tabler-outline/circle-check` | P21, P23, P26, P27 |
| 互斥 / 失败 | `tabler-outline/circle-x` | P26 |
| 流转箭头 | `tabler-outline/arrow-right` | P05, P09, P10, P11 |
| 步骤箭头 | `tabler-outline/chevron-right` | P09, P10 |
| 设计原则 / 洞见 | `tabler-outline/bulb` | P19, P33 |
| 权限 / 校验通过 | `tabler-outline/shield-check` | P31, P32 |
| 权限锁 | `tabler-outline/shield-lock` | P31 |
| 并发锁 | `tabler-outline/lock` | P27, P28 |
| 密钥 / 邀请码 | `tabler-outline/key` | P12, P27 |

**Brand marks (simple-icons, 仅 P14 技术栈页)**:

| 用途 | Icon Path |
| ---- | --------- |
| 后端语言 | `simple-icons/python` |
| Web 框架 | `simple-icons/fastapi` |
| 数据库 | `simple-icons/mysql` |
| 前端构建 | `simple-icons/vite` |
| 前端语言 | `simple-icons/javascript` |
| 标记语言 | `simple-icons/html5` |
| 样式 | `simple-icons/css3` |
| AI 接入 | `simple-icons/openai` |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P04 | comparison_table | `templates/charts/comparison_table.svg` | "Pick for 2-4 plans/products compared across many feature rows (dense matrix). Skip for pricing-tier marketing layout (use comparison_columns)." | 「痛点现状 vs 本产品应对」两列稠密对照表，5 行对齐 |
| P05 | vertical_pillars | `templates/charts/vertical_pillars.svg` | "Pick for 1×3 / 1×4 / 1×5 vertical column layout where each pillar = one independent category with title + bullets — PEST (Political/Economic/Social/Technological), four-pillar strategy overview, side-by-side independent categories. Skip for 2×2 quadrant (use quadrant_text_bullets), pricing tiers (use comparison_columns), or 2×2 parallel aspects (use labeled_card)." | 三条业务闭环并排（HR / 候选人 / 简历驱动），每柱带要点 |
| P06 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_chart) or vertical layout (use roadmap_vertical)." | MVP-1 → MVP-5 五个版本里程碑（2026-09-15 / 09-20 / 09-20 / 09-22 / 09-23） |
| P07 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | 「刻意不做的六条边界」逐条列出不做 + 允许的替代 |
| P09 | process_flow | `templates/charts/process_flow.svg` | "Pick for 3-8 sequential steps connected by simple arrows — approval workflows, customer onboarding, request handling, lifecycle stages. Skip if cyclical (use circular_stages) or stages produce named outputs (use pipeline_with_stages)." | HR 主线 7 步：建岗 → 建面试出题 → 准备 → 录答 → 完成 → 评估 → 报告 → 导出 |
| P10 | process_flow | `templates/charts/process_flow.svg` | "Pick for 3-8 sequential steps connected by simple arrows — approval workflows, customer onboarding, request handling, lifecycle stages. Skip if cyclical (use circular_stages) or stages produce named outputs (use pipeline_with_stages)." | 候选人主线 6 步：拿码 → 激活 → 录简历 → 关联 → 作答交卷 → 读反馈 |
| P11 | chevron_process | `templates/charts/chevron_process.svg` | "Pick for 3-6 phase methodology with chunky arrow-chain progression and deliverables per phase. Skip for <=2 phases or non-linear flow (use process_flow), or chain ending in an aggregate outcome wedge (use chevron_chain_with_tail)." | 简历驱动链路 6 阶段，与 P09/P10 的 process_flow 做视觉区分 |
| P14 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product highlights. Skip for sequential ordering (use numbered_steps) or hierarchical layers (use pyramid_chart)." | 技术栈八项能力卡（语言 / 框架 / 库 / 前端 / 分层 / AI / 部署 / 测试） |
| P15 | layered_architecture | `templates/charts/layered_architecture.svg` | "Pick for 3-4 horizontal architecture layers (presentation/service/data), 2-4 module cards per layer, each card = title + 1-line description (description required, even if source brief). Skip if no per-module descriptions (use icon_grid) or no horizontal layering (use module_composition)." | router → service → repository → MySQL 四层，逐层写职责一句话 |
| P17 | basic_table | `templates/charts/basic_table.svg` | "Pick for plain tabular text/number grid, 3-8 columns. Skip if cells need visual bars (use consulting_table) or qualitative scores (use harvey_balls_table)." | 16 张表按模块分组的实体—关键字段表 |
| P18 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, results-at-a-glance. Skip if metrics have target baselines (use bullet_chart) or single hero number (use gauge_chart)." | 工程规模四指标：1601 项后端测试 / 48 条接口路径 / 16 张表 / 10 个 package |
| P20 | basic_table | `templates/charts/basic_table.svg` | "Pick for plain tabular text/number grid, 3-8 columns. Skip if cells need visual bars (use consulting_table) or qualitative scores (use harvey_balls_table)." | AI 十能力 × 用途 × 调用方 三列契约表 |
| P33 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | 工程收获五条（架构约束可测试 / 契约先于实现 / 失败不静默降级 等） |
| P34 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | 已知局限与踩过的坑（五条，含原型与真实契约对不上的教训） |
| P35 | roadmap_vertical | `templates/charts/roadmap_vertical.svg` | "Pick for 4-8 milestones on a vertical timeline with status indicators. Skip for horizontal time emphasis (use timeline) or tasks with durations (use gantt_chart)." | V1.1 六项规划，带「规划中」状态指示 |

**no-template-match（自定义绘制，不得出现在 `spec_lock.page_charts`）**：

| Page | 内容 | Fallback 与理由 |
| ---- | ---- | --------------- |
| P12 | 两个状态机（面试 5 态 / 作答邀请 4 态） | 状态机不是环形、不是线性流程、不是时间轴：`circular_stages` 要求闭合循环（`Skip for linear flow`），`process_flow` 表达不了「未列出的迁移一律 409」这条反向约束。自定义「节点 + 有向边 + 合法迁移表」 |
| P16 | 十个模块的依赖有向图 | 依赖是一张 **DAG 而非水平分层**，套 `layered_architecture` 会丢掉「practice 不依赖 interview」「resume 不反向依赖任何业务模块」这两条本项目最关键的约束。自定义有向图，用虚线标出两条**禁止**的反向边 |
| P21, P23, P25, P26, P28, P30, P32 | 对象交互序列图、问题与解决 | **序列图**（生命线 + 激活条 + 编号消息）在 71 个模板中无对应项 —— 这是本套的技术核心图形，必须自定义绘制 |
| P19 | 第 ④ 段讲解路线图 | 六个模块的讲解顺序 + 每个模块的固定三段式（实现 / 序列图 / 问题与解决），结构独特，自定义 |
| P22, P24, P27, P29, P31 | 模块源码级实现页 | 代码块 + 结构标注的组合版式，无匹配模板 |
| P01, P02, P03, P08, P13 | 封面 / 目录 / 章节页 | 结构页，自定义 |

**Runners-up considered**:

- `numbered_steps` | rejected for P09: summary 明确 `Skip if steps need connector arrows (use process_flow)` —— HR 主线的七步之间是**有数据流转与依赖**的，必须用箭头连接器表达先后与产物流向，纯数字编号会丢掉这层信息。
- `layered_architecture` | rejected for P16: 模块依赖不是水平分层，而是有向无环图。强行套分层模板会让「practice 与 interview 解耦」和「resume 不反向依赖」这两条架构测试钉住的约束在图上消失 —— 而它们恰恰是这一段要证明的东西。
- `funnel_chart` | rejected for P06: MVP-1 → MVP-5 是**并列的版本里程碑**，不存在单调递减的转化损耗；funnel 的 summary 要求 `sequential conversion stages with monotonic drop-off`，套上去会凭空造出一个错误的「漏斗」语义。
- `comparison_columns` | rejected for P04: 该模板是定价 / 服务分层的**营销版式**（大卡片 + 价格位），而 P04 需要的是逐行对齐的**稠密对照矩阵**（5 行痛点 × 2 列），用大卡片会把 5 行内容撑爆或被迫截断。
- `quadrant_text_bullets` | rejected for P07: 「刻意不做的边界」是**并列的六条独立陈述**，不是 2×2 的双轴分类；强行放进四象限需要捏造两个分类轴，属于为套模板而改内容。

---

## VIII. Image Resource List

**本套不使用任何图片（Approach A）。**

全部视觉由**自有矢量图形**承担：序列图、架构图、流程图、依赖图、状态机、表结构、源码块、KPI 卡。
这是一个刻意的选择，理由有三：

1. **零获取风险** —— 不需要 AI 生成或网络检索，Phase B 可直接进入 SVG 生成
2. **投影与打印无损** —— 图形始终矢量锐利，不存在位图缩放糊化
3. **无 CJK 文字失真** —— 本套几乎每张图都带中文标注（生命线名、节点名、注释），而 AI 生图的中文渲染不可靠

> 因此 `spec_lock.md` 不含 `images` 段，也不含 `image_rendering` / `image_palette` 两行。

---

## IX. Content Outline

### Part 0: 开篇

#### Slide 01 - 封面

- **Layout**: Full-bleed 深墨蓝渐变（`deepGradient`）+ 居中浮层标题；右下角极简装饰几何（等距细线网格）
- **Title**: AI 智能面试助手
- **Subtitle**: 技术解构 —— 架构、模块与工程取舍
- **Info**: 35 页 · 技术答辩 · 2026-09-23

#### Slide 02 - 目录

- **Layout**: 单列 + 左侧编号列；五项主线，右侧标注起止页
- **Title**: 目录
- **Content**:
  - 01 项目概述与背景（P03–P07）
  - 02 业务流程（P08–P12）
  - 03 技术栈（P13–P18）
  - 04 核心模块技术讲解（P19–P32）
  - 05 收获与展望（P33–P35）

### Part 1: 项目概述与背景

#### Slide 03 - 章节页 01 项目概述与背景

- **Layout**: Full-bleed + floating text；深底；左侧大号「01」
- **Title**: 项目概述与背景
- **Subtitle**: 它解决什么问题，从哪来，边界画在哪

#### Slide 04 - 产品定位与它解决的问题

- **Layout**: Top-bottom split —— 上方一句话定位带（含三类角色标签）；下方两张对照表
- **Visualization**: comparison_table (见 VII)
- **Content**:
  - 定位：单机部署的**双端** Web 应用，AI 辅助真人面试官完成「出题 → 记录 → 评估 → 报告」闭环
  - 三类角色：`admin`（系统管理）/ `hr`（日常使用者，不可自助注册）/ `candidate`（终端用户）
  - 痛点 → 应对 五行对照：出题靠人肉翻题库 → 按维度抽题 + AI 按 JD 补题；记录散落 → 统一落库 + 题目快照；写报告耗时 → 三阶段流式评估同一套 0–10 分制；候选人杳无音信 → 脱敏反馈；无题可练 → 复用同一题库做刷题闭环

#### Slide 05 - 三条业务闭环

- **Layout**: 三栏 vertical_pillars；每栏顶部图标 + 标题 + 步骤链 + 底部产能标签
- **Visualization**: vertical_pillars (见 VII)
- **Content**:
  - **HR 闭环**：建岗位 → 建面试并同步出题 → 记录回答 → 标记完成 → 流式评估 → 报告与导出
  - **候选人闭环**：凭邀请码激活 → 录简历 → 在线作答交卷 → 读脱敏反馈
  - **简历驱动链路**（把两端缝起来的那条线）：HR 发码 → 候选人激活并关联简历 → HR 读简历并补题 → 准备 → 评估 → 报告
  - 一句话结论：简历由**候选人单侧提交**，被 HR 侧（补题）与候选人侧（刷题推荐）**两个方向消费**

#### Slide 06 - 前世今生：MVP-1 → MVP-5 演进

- **Layout**: 横向 timeline，**五个**里程碑节点；下方两行「新增模块 / 新增依赖」
- **Visualization**: timeline (见 VII)
- **Content**:
  - **MVP-1（2026-09-15）** HR 侧闭环：auth / position / question / interview / evaluation / ai 六模块，461 条用例验证
  - **MVP-2（2026-09-20）** 候选人侧：新增 `candidate` 角色、作答邀请、在线作答、脱敏反馈、`practice` 新模块
  - **MVP-3（2026-09-20）** 简历驱动与导出：`resume` 新模块、按简历补题、准备助手、DOCX 导出（新增依赖 `python-docx`）
  - **MVP-4（2026-09-22）** 简历上传解析与 AI 评估：新增 `pypdf` + `python-multipart`，新增能力 `evaluate_resume`，**不改任何表结构**
  - **MVP-5（2026-09-23）** 手机验证码登录：新增 `sms` 包；`auth` 加手机号登录与 `accept` 免密分支；**加 1 表 1 列**（`phone_verification_code` + `user.phone`）；**无新依赖**（短信先只实现 Mock）
  - 一条贯穿始终的约束：**技术栈全程不变**（原生前端 + FastAPI + MySQL，不引入新框架与中间件）

#### Slide 07 - 刻意画出的边界

- **Layout**: 单列 vertical_list，六条编号项；每条「不做 X」+ 灰色小字「但 Y 是允许的」
- **Visualization**: vertical_list (见 VII)
- **Content**:
  - 保留简历原文件 → **不做**；上传仅取文字、不落盘，要留原件请本地自存
  - 后端生成 PDF → **不做**；PDF 由浏览器打印生成（`window.print()`），代价是不支持脱离浏览器的后台导出
  - 候选人查看逐题分与雷达图 → **默认不下发**；由配置项 `CANDIDATE_FEEDBACK_LEVEL` 决定是否放开**总分**
  - 邮件 / 通知 → **不做**；邀请码在系统内展示与复制，由 HR 自行转达
  - 流式出题 → **不做**；只有评估环节是 SSE 流式，出题与准备提纲都是同步整批返回
  - 多 worker 部署 → **不做**；SSE 运行注册表与刷题限流计数都在进程内，`--workers 1` 是硬性要求

### Part 2: 业务流程

#### Slide 08 - 章节页 02 业务流程

- **Layout**: Full-bleed + floating text；左侧大号「02」
- **Title**: 业务流程
- **Subtitle**: 两条主线、一条缝合线、两个状态机

#### Slide 09 - HR 主线：出题 → 记录 → 评估 → 报告

- **Layout**: 横向 process_flow 七步；每步下方一行输入/产出注记；底部三条易踩规则
- **Visualization**: process_flow (见 VII)
- **Content**:
  - 建岗位（名称 + JD + 评估维度）→ 新建面试（同步出题：题库抽 5 + AI 补 3）→（可选）生成准备提纲 →（可选）发邀请码 → 逐题录入/修订回答 → 标记完成 → 触发流式评估 → 读报告 → 导出 DOCX / 打印 PDF
  - 易踩点一：**出题后不能换题 / 删题**，补题是唯一的加题例外且只追加
  - 易踩点二：发邀请码只在 `ongoing` 可行，`completed` 及之后提前拦截（409）
  - 易踩点三：重新评估失败**退回 `evaluated`**，旧报告不丢 —— 回退目标由「库里有没有旧报告」决定

#### Slide 10 - 候选人主线：激活 → 简历 → 作答 → 反馈

- **Layout**: 横向 process_flow 六步；右侧竖排注释「交卷不推进面试状态」
- **Visualization**: process_flow (见 VII)
- **Content**:
  - 拿到邀请码 → 打开激活页（**公开端点，无需先登录**）→ 凭码激活并绑定面试 → 登录候选人端 → 录入简历（粘贴或上传 DOCX / PDF 解析）→ 关联到这场面试 → 逐题作答（实时保存）→ 交卷（幂等，写 `submitted_at`）→ 等待 HR 收口 → 读脱敏反馈
  - 关键取舍：**候选人作答不进入面试状态机** —— 交卷只锁定候选人通道，面试是否完成仍由 HR 决定
  - 账号复用规则：用户名已被 `candidate` 占用必须**密码一致**才复用；被禁用账号**不得复用绑定**

#### Slide 11 - 简历驱动链路

- **Layout**: 横向 chevron_process 六阶段，带阶段产出物；底部一条「谁写入、谁消费」的所有权注记
- **Visualization**: chevron_process (见 VII)
- **Content**:
  - HR 建面试 → 发邀请码 → 候选人激活 → 候选人录简历 → **候选人**将简历关联到面试（`PUT /candidate/interviews/{id}/resume`）→ HR 读到简历 → 按简历补题（`POST /interviews/{id}/questions/match`）→ 准备 → 面试 → 评估 → 报告
  - 核心事实：简历**由候选人单侧提交**，出现在面试创建之后，因此关联动作也由候选人发起
  - 这是 **HR 能看到候选人简历的唯一通路**；同一份简历可被多场面试与多次练习复用

#### Slide 12 - 两个状态机

- **Layout**: 上下两条独立状态轨 —— 上：面试 5 态有向图（含回退边）；下：作答邀请 4 态；右侧竖排合法迁移表
- **Visualization**: 自定义（no-template-match，见 VII）
- **Content**:
  - **面试状态机**：`draft → ongoing → completed → evaluating → evaluated`；回退边 `completed → ongoing`、`evaluated → ongoing`、`evaluated → evaluating`；失败回退 `evaluating → {completed(无旧报告), evaluated(有旧报告)}`
  - **作答邀请状态机**（与面试状态**解耦**）：`pending → accepted / revoked / expired`；`expired` **读取时派生、不落库**；`accepted → revoked` 有意允许，是切断候选人访问的唯一手段
  - **表中未列出的迁移一律 409**，并在 `detail` 给出 `{from, to}`

### Part 3: 技术栈

#### Slide 13 - 章节页 03 技术栈

- **Layout**: Full-bleed + floating text；左侧大号「03」
- **Title**: 技术栈
- **Subtitle**: 选型、分层、模块边界与数据模型

#### Slide 14 - 技术栈总览

- **Layout**: 2×4 icon_grid —— 八张能力卡，每卡一个品牌/通用图标 + 标题 + 一句话选型理由
- **Visualization**: icon_grid (见 VII)
- **Content**:
  - 后端语言：**Python 3.11+**（本机验证于 3.13）
  - Web 框架：**FastAPI** —— 纯 API，不渲染页面
  - 数据库：**MySQL 8.0+**（JSON 列与 ENUM 需 8.0+），单一库 16 张表
  - 前端：原生 **HTML + CSS + JavaScript**，**Vite** 构建 —— 无 UI 框架、无图表库、无状态管理库
  - 架构：前后端分离；开发期经 Vite 代理，演示期由后端托管（同源，无 CORS）
  - 分层：`router → service → repository → MySQL`，严格单向依赖
  - AI：抽象 Provider 接口，`mock` / `openai` 可配置切换 —— **无 Key 也能完整演示与测试**
  - 部署：单机同源 `127.0.0.1:8000`，**必须 `--workers 1`**

#### Slide 15 - 后端严格分层

- **Layout**: layered_architecture 四层横向堆叠；每层 2–4 张模块卡（标题 + 一句话职责）；右侧竖排「禁止」清单
- **Visualization**: layered_architecture (见 VII)
- **Content**:
  - **router 层**：HTTP 端点 —— 参数校验、鉴权（角色守卫）、统一响应包装。**不做数据访问**
  - **service 层**：业务逻辑 —— 流程编排、事务、调用 AI Provider。**不直接执行 SQL**
  - **repository 层**：数据访问 —— CRUD，对接 MySQL。**是最底层，不依赖上层**
  - **ai 包**：能力抽象 —— 只接收原始值，被 interview / evaluation / practice 调用
  - 约束由测试钉住（`tests/test_architecture.py`）：router 不得引用 repository；repository 不得依赖 service / router；service 不得出现 `db.execute`；`ai` 不依赖任何业务模块；`core` 对业务模块只有函数体内延迟导入

#### Slide 16 - 十个模块与依赖方向

- **Layout**: 自定义有向图 —— 中心 `core` + `ai · sms` 基础设施，外围 7 个业务模块；实线为允许依赖，**两条红色虚线标出被架构测试明确禁止的反向边**
- **Visualization**: 自定义（no-template-match，见 VII）
- **Content**:
  - 十个 package：`core` / `auth` / `position` / `question` / `resume` / `interview` / `evaluation` / `practice` / `ai` / `sms`
  - 两条最关键的约束：
    - **`resume` 只被依赖、不反向依赖任何业务模块** —— 简历由候选人单侧写入，被 `interview`（补题）与 `practice`（推荐）单向依赖。若反向引用，会把 `practice ↔ interview` 的循环依赖引进来
    - **`practice` 不依赖 `interview`** —— 刷题与真实面试完全解耦，两条业务线各有各的记录表
  - 其余：`ai` 与 `sms` 合画**同一个框**（两者结构完全同构：可切换的能力提供方、不反向依赖任何业务模块；`ai` 被 interview / evaluation / practice 调用，`sms` 被 auth 调用）；`evaluation` 读 `interview` 的回答生成报告；各业务模块均依赖 `auth` 做鉴权与数据隔离

#### Slide 17 - 数据模型：16 张表与快照设计

- **Layout**: basic_table —— 按模块（auth / position / question / resume / interview / evaluation / practice）分组，列：实体 / 关键字段；右侧竖排「五个快照字段」说明
- **Visualization**: basic_table (见 VII)
- **Content**:
  - 16 张表按包分组列出（`user` / `phone_verification_code` / `position` / `question` / `resume` / `interview` / `interview_question` / `answer` / `interview_invitation` / `interview_prep` / `question_score` / `dimension_score` / `report` / `candidate_feedback` / `practice_session` / `practice_item`）
  - **`user.phone` 可空且唯一**（MVP-5）：可空是因为绝大多数账号没有手机号；唯一是因为一个号只能绑一个账号。MySQL 唯一索引允许多个 NULL，所以两个要求可以同时满足，不需要额外机制
  - **`phone_verification_code` 存哈希不存明文**（MVP-5）：`sha256(salt + code)`；一次性消费，新码发出即作废旧码；**不做后台清理**，过期与否在读取时现算
  - **快照字段是「题库删改不影响历史」的前提**：`content_snapshot` / `dimension_snapshot` / `source_snapshot` / `options_snapshot` / `reference_answer_snapshot`
  - **`candidate_feedback` 独立成表而非给 `report` 加列**：两份文本受众不同、可见性规则不同。独立成表让可见性边界落在**表**这一层 —— HR 报告接口**结构上读不到**候选人字段
  - 两处刻意缺失：**不设 `updated_at`**（报告重评即整行重建）、**不存总分**（改档位不需要重新生成反馈）

#### Slide 18 - 工程规模

- **Layout**: 1×4 kpi_cards —— 四个大数字；下方一行「测试不需要网络、不需要任何 API Key」
- **Visualization**: kpi_cards (见 VII)
- **Content**:
  - **1601** 项后端测试（`python -m pytest` 全部走 Mock Provider）
  - **48** 条接口路径 / 64 个 method-route
  - **16** 张数据表 / **10** 个 package
  - **128** 项端到端冒烟断言（对真实运行中的服务走通全链路）
  - 补充：前端另有 145 项 Vitest 单测 + 8 个浏览器端 Mock 联调台（合计 700+ 断言），并做过 33 次**变异检查**（把缺陷植回去，断言必须失败）

### Part 4: 核心模块技术讲解

#### Slide 19 - 章节页 04 核心模块技术讲解

- **Layout**: Full-bleed + floating text；下方六个模块的编号索引
- **Title**: 核心模块技术讲解
- **Subtitle**: 六个模块 × 固定三段式 —— 实现 → 序列图 → 问题与解决
- **Content**:
  - ① `ai` Provider 抽象 ② `interview` 出题组装 ③ `evaluation` 流式评估
  - ④ `interview` 作答邀请并发 ⑤ `resume` 上传解析 ⑥ `auth` 权限守卫
  - 讲解纪律：每个模块都给**源码级**实现要点 + **对象交互序列图** + **真实遇到的一个问题及其解法**

#### Slide 20 - 模块① ai：Provider 抽象与十能力契约

- **Layout**: 左侧代码块（抽象基类签名）+ 右侧三栏要点；下方三列能力分组
- **Content**:
  - **契约核心**：`AIProvider(ABC)` 十个抽象方法，覆盖三条业务线 —— HR 侧（出题 → 逐题评分 → 多维评分 → 汇总报告）、候选人侧（补参考答案 / 刷题判分 / 脱敏反馈）、简历驱动（按简历匹配题目 / 生成准备提纲 / 简历匹配度评估）
  - **最重要的一条设计约束**：全部方法**只接收原始值**（`str` / `list[str]` / `float` / 本模块 dataclass），**不接收任何 ORM 对象**
  - 收益一：`ai` 不依赖 position / question / interview / evaluation 任何业务模块，守住依赖单向
  - 收益二：Mock 实现可以**在完全不起数据库的情况下被单测**
  - **工厂**：`get_provider()` 按配置返回实现并缓存单例；`validate_provider_config()` 在启动期校验，配置有误**直接启动失败**（fail fast），而不是等第一次调用 AI 才报错
  - 源码位置：`backend/app/ai/base.py`（401 行）/ `factory.py` / `mock_provider.py` / `openai_provider.py`

#### Slide 21 - 模块① ai：序列图与「只挑不生成」的结构性保证

- **Layout**: 上方序列图（evaluation → factory → AIProvider → MockProvider/OpenAIProvider）；下方左右对照：问题（红）/ 解法（绿）
- **Content**:
  - **序列图**：`evaluation.service.evaluate_interview` → `get_provider()`（单例缓存）→ `provider.evaluate_answer(...)` → Mock 规则生成 / OpenAI httpx 调用 → 返回 `QuestionScoreResult` → 回调 `on_event` 发布 SSE 事件
  - **问题**：AI 有可能「编造」一道题库里根本不存在的题，用它冒充匹配结果 —— 让 HR 以为这道题是从自己题库里挑的
  - **解法（两层结构性保证，不靠 prompt 自觉）**：
    - 返回类型 `MatchedQuestion` **只有 `question_id` 与 `reason`，没有题面字段** —— 「编造一道新题」在结构上**无从表达**，即使模型返回了题面也无处安放
    - 解析时用**池内 id 集合**过滤，池外 id 一律丢弃；若模型返回了内容却一条都没留下，**抛错而不是静默返回空数组** —— 「没有」与「坏了」必须可区分
  - **问题**：真实 Provider 调用失败时，要不要自动降级到 Mock？
  - **解法**：**绝不降级**。静默降级会把规则模板的输出伪装成 AI 评估结果，既误导用户又掩盖故障。失败即 `502 AI_PROVIDER_ERROR`，由用户重试

#### Slide 22 - 模块② interview：出题组装的确定性抽取

- **Layout**: 左侧代码块（`_round_robin_pick` + `_assemble_questions`）；右侧要点栏
- **Content**:
  - **目标**：从题库按岗位维度抽 N 题（默认 5）+ AI 按 JD 补 M 题（默认 3），合并成题目列表并写内容快照
  - **抽取算法 round-robin**（`_round_robin_pick`）：按维度轮询、**组内按 id 升序**，保证各维度题目数尽量平均
  - **可预测性**是刻意追求的：相同数据状态下出题结果**完全确定**，因此测试可以直接断言抽到哪几题
  - **差额补足公式**：`need_ai = M + (N - K)`，K 为实际抽到的题库题数 —— **总题数恒为 N + M = 8**，题库不足时由 AI 补足差额
  - **防御**：AI 返回的维度若不在岗位维度列表内，丢弃该条
  - **事务边界**：建面试 + 出题组装 + 置 `ongoing` 在**同一事务**内，AI 出题失败则整体回滚 —— 要么面试创建成功且题目齐备，要么什么都没发生
  - 源码位置：`backend/app/interview/service.py:217-343`

#### Slide 23 - 模块② interview：序列图与 N+M 差额补题

- **Layout**: 上方序列图（HR → router → interview.service → question.service / ai → repository → MySQL）；下方左右对照：问题 / 解法
- **Content**:
  - **序列图**：`POST /interviews` → `interview.service.create_interview` → `position_service.get_position` → `_assemble_questions` → `question_service.list_candidates_for_position` → `_round_robin_pick` → `get_provider().generate_questions`（need_ai > 0 时）→ `question_service.bulk_create_from_ai` → `repository.create_questions` → 状态置 `ongoing` → `db.commit()`
  - **问题**：出题后题目列表写死了，没有换题 / 删题接口。但候选人的简历是在面试创建**之后**才提交的 —— 那时才知道该考什么，怎么办？
  - **解法**：把「按简历补题」设计为**唯一的加题例外**，且只追加、不改动既有题目；`seq` 续接本场最大值，`source_snapshot='resume_match'`，`match_reason` 写入 AI 给出的理由
  - **问题**：HR 连点几次「按简历补题」，会不会出一堆重复题？
  - **解法（幂等的准确含义）**：候选池**剔除本场已有的 `question_id`**，因此重复调用**不会产生重复题目**；但池子变小后 AI 会挑下一批，所以**每次调用都会再加 count 题** —— 这是有意允许的累加。响应回 `added_count` / `total_questions`，界面必须显示本场总数，否则连点几次会以为界面卡了

#### Slide 24 - 模块③ evaluation：三阶段编排与运行注册表

- **Layout**: 左侧三阶段纵向流；右侧代码块（`_evaluate_in_thread` + `publish_terminal`）；底部「先推后写」注记
- **Content**:
  - **三阶段编排**（`evaluate_interview`，同步回调实现）：逐题评分（`question` 事件）→ 多维评分（`dimension` 事件）→ 汇总报告（`report` 事件）
  - **先推后写**：结果在**最后一次性落库**（单事务）—— 数据库要么是上一次的完整结果、要么是这一次的完整结果，**永不存在混合态**；失败也不损失既有数据
  - **业务与传输分离**：业务编排是**同步**的（`service.py`），SSE 只是传输适配（`stream.py`）—— 两者分开，业务逻辑才能脱离异步设施单测
  - **运行注册表**（`_runs: dict[int, EvaluationRun]`）：`start_run` 起守护线程，**独立 DB 会话**（SQLAlchemy Session 非线程安全）；`EvaluationRun` 内含事件历史 `events` 与订阅者队列 `subscribers`
  - **注册表 TTL 300 秒**：保留是为了让断线重连能重放完整事件序列；过期后重连走 `_synthesize_from_db` 从库合成
  - 源码位置：`backend/app/evaluation/service.py` + `stream.py`（367 行）

#### Slide 25 - 模块③ evaluation：SSE 对象交互序列图

- **Layout**: 全幅序列图 —— 生命线：浏览器 / router / stream.start_run / 后台线程 / repository / MySQL；下方一行 SSE 事件契约
- **Content**:
  - **序列图（发起）**：HR 点「开始评估」→ `POST /evaluate` → `stream.start_run`（`remove_run` 丢弃上一轮 → `_create_run` 注册 → 起守护线程）→ **202 立即返回** SSE 地址
  - **序列图（订阅）**：浏览器 `fetch` 打开 `GET /evaluation/stream` → `stream_events` 在**同一把锁**内完成「订阅 + 取快照 + 读状态」→ 重放已推事件 → 转发新事件 → 终结事件后关闭
  - **序列图（后台）**：线程内 `evaluation_service.evaluate_interview(db, id, on_event=publish)` → 逐阶段 `publish` → `publish_terminal("done"/"error")` → `_schedule_eviction`
  - **SSE 事件契约**：`question`（按 seq 升序）→ `dimension` → `report` → `done` 或 `error`；`done` 与 `error` **互斥且必居其一**；每 **15 秒**一个 `: ping` 心跳防代理空闲断开
  - **前端注意**：SSE 需要 `Authorization` 头，因此**不能用浏览器原生 `EventSource`**（它无法设置自定义请求头），必须用 `fetch` + `ReadableStream` 手动解析分帧

#### Slide 26 - 模块③ evaluation：问题与解决

- **Layout**: 三组上下对照（问题红 / 解法绿），每组配一个最小示意；底部一行「重连重放是特性不是缺陷」
- **Content**:
  - **问题一：评估跑了一半，界面永远停在半截** —— 若「终结事件」与「运行状态」分两次写，读侧可能读到「状态已终结、终结事件尚未入列」的组合，推出一段**没有终结事件的截断流**，客户端既不报错也收不到 `done`/`error`
    - **解法**：`publish_terminal` 把**终结事件与运行状态在同一把锁内写入**；`stream_events` 也在同一把锁内读「事件列表 + 状态」，两边配合保证「状态已终结 ⇒ 终结事件必在重放序列中」
  - **问题二：订阅与取快照之间的空隙会漏事件** —— 若先取快照再订阅，两步之间 `publish` 的事件既不在快照里、也投递不到订阅者，客户端会看到**跳号**
    - **解法**：把「订阅 + 取快照 + 读状态」**合并进同一把锁**内原子完成
  - **问题三：客户端在重放期间断开，订阅者永久留在名单里** —— 之后每个事件都往没人消费的队列里投递，内存单调增长
    - **解法**：`try` **必须覆盖重放循环**，`finally` 里移除订阅者。若重放不在 `try` 内，生成器在 `yield` 处收到 `GeneratorExit` 时 `finally` 不会执行
  - **问题四：重评时上一轮的延时回收定时器会误删新一轮的运行记录** —— 于是重连的人拿不到进度
    - **解法**：`_evict_if_current` 做**身份校验**（`_runs.get(id) is run`），只回收仍是当前这一轮的记录
  - **问题五：进程重启遗留的孤儿评估**（状态卡在 `evaluating` 且注册表为空）—— **解法**：`heal_orphan` 以注册表为「评估是否真在跑」的唯一事实来源，按同一规则自愈
  - **重连会从头重放**是设计特性而非缺陷：前端因此必须**按 `interview_question_id` 覆盖**而非「来一条加一条」，否则进度会翻倍

#### Slide 27 - 模块④ interview：作答邀请的并发接受

- **Layout**: 左侧代码块（`accept_invitation` 的临界区）；右侧序列图（两个并发请求 + 面试行锁）；底部四态表格
- **Content**:
  - **邀请码安全属性**：高熵（`secrets.token_urlsafe(16)` → 22 个 URL-safe 字符、约 128 位熵）、**一次性接受**、有效期默认 7 天、可撤销
  - **四种失效原因**（码不存在 / 已撤销 / 已接受 / 已过期）返回**同一文案**，且响应不出现任何面试信息 —— 避免成为邀请码探测接口
  - **`accept` 是公开端点**：拿码的人往往**还没有账号**。要求他先登录才能激活，会让整条邀请链自相矛盾（没账号 → 没 token → 激活不了）。它是继 `/auth/login`、`/auth/register` 之后的第三个业务公开端点
  - **账号创建委托 auth**：`auth_service.create_candidate_account` —— 不在 interview 模块复制「用户名唯一性 / 密码哈希 / 角色约束」规则
  - **签名刻意不接 `user` 参数**：绑定到哪个账号由请求体的 username 决定，与调用者身份无关。签名里放一个不用的 `user` 会让人误以为「绑定的是当前登录者」
  - 源码位置：`backend/app/interview/service.py:1073-1141`

#### Slide 28 - 模块④ interview：问题与解决（并发绑定双写）

- **Layout**: 上方序列图（两个并发 accept 请求落在同一场面试）；下方左右对照：问题 / 解法；右侧「加锁位置为什么在这里」注记
- **Content**:
  - **问题**：同一候选人用**两条不同的码**并发接受同一场面试，仅靠「先查后写」在并发下会**双双通过** —— 结果是候选人列表里同一场面试出现两次
  - **解法**：用**面试行锁**（`SELECT … FOR UPDATE`）串行化同一场面试的接受，并在锁内以**当前读**复查
  - **为什么必须当前读**：本事务的快照可能早于并发事务的提交，**快照读会读不到并发事务刚写入的那条接受记录**，于是复核形同虚设
  - **加锁位置为什么在 `create_candidate_account` 之后**：新建账号会 `commit`，而 **`commit` 会释放本事务已持有的锁** —— 先加锁等于白加
  - **为什么锁面试行而不是邀请行**：对「尚不存在的接受记录」加锁只会拿到**间隙锁**，挡不住并发；面试行是这场绑定的真实归属，锁它才有意义
  - **拿锁后还要重新当前读邀请行**：确认它**仍是 `pending`**，挡住「同一条码被并发接受」

#### Slide 29 - 模块⑤ resume：上传取文字的纯转换端点

- **Layout**: 左侧代码块（`parse_resume_file` 四道校验）；右侧流程（上传 → 校验 → 解析 → 归一化 → 回填正文框 → 候选人确认保存）；底部「不落库不落盘」注记
- **Content**:
  - **职责收窄**：`POST /candidate/resumes/parse` 是**不落库、不落盘的纯转换端点** —— 不建简历、不改简历，服务器上不留那个文件
  - **因此简历表结构完全不变**：不新增文件路径字段、不存原文件、不存解析产物
  - **四道校验**（`parse_resume_file`）：① 扩展名白名单（`.docx` / `.pdf`）；② **文件头魔数复核**（PDF 以 `%PDF-` 开头、DOCX 是 ZIP 容器以 `PK\x03\x04` 开头）；③ 解析（DOCX 走 `python-docx`、PDF 走 `pypdf`）；④ 归一化后**非空**校验
  - **DOCX 表格也要取**：只取 `document.paragraphs` 会整块丢掉表格，而简历里的「教育经历」「工作经历」常做成表格 —— 必须按 body 子元素顺序遍历，段落与表格保持原有版序，并**递归取嵌套表格**
  - **归一化只做四件事**：统一换行、去行尾空白、折叠连续空行、去首尾空白。**不做重排** —— 任何「更聪明」的处理都会让系统偷偷改掉候选人的原文，而他看到的正文正是要被 AI 消费的内容
  - 源码位置：`backend/app/resume/parser.py`（190 行，纯函数模块：不接 session、不落盘、不读配置）

#### Slide 30 - 模块⑤ resume：问题与解决（上传的安全边界）

- **Layout**: 三组上下对照（问题红 / 解法绿）；底部一行「为什么这里可以写宽 except」
- **Content**:
  - **问题一：改了扩展名就能绕过类型检查** —— 扩展名由客户端提供，改个名字上传任意文件即可
    - **解法**：扩展名白名单之外，**再按文件头魔数复核**（`%PDF-` / `PK\x03\x04`），两道都过才解析
  - **问题二：ZIP bomb** —— 上传体积上限拦不住它：5 MB 的压缩包可以解出几个 GB。DOCX 本质是 ZIP
    - **解法**：单独设**解压后展开体积上限 50 MB**，用中央目录的 `file_size` 求和，**不解压** —— 因此这道检查本身不吃内存
  - **问题三：加密 PDF 被误判为损坏** —— 很多导出工具默认给 PDF 加**空密码**，只看 `is_encrypted` 会误伤一批正常文件
    - **解法**：判定条件改为「已加密 **且** 空密码解不开」，先尝试 `reader.decrypt("")`
  - **问题四：扫描件 PDF 解析出空字符串** —— 看起来像「解析成功但没内容」
    - **解法**：归一化后为空即报 400，文案点明「这可能是扫描件」并提示改用粘贴；`.doc` 旧格式、`.txt`、图片同样在类型检查处被点名拒收
  - **为什么这里可以写宽 `except`**：`pypdf` 与 `python-docx` 在损坏文件上抛出的异常谱系不稳定（`PdfReadError` / `DependencyError` / `ValueError` / xml 层各种异常），逐个枚举必然漏。此处兜底是安全的，因为本模块**不落库、不落盘** —— 宽捕获不会掩盖数据损坏，只会把「读不出来」如实告诉上传方

#### Slide 31 - 模块⑥ auth：权限守卫与数据隔离

- **Layout**: 左侧代码块（`require_roles` 依赖工厂）；右侧三条数据隔离路径表；底部「精确匹配、无继承」结论条
- **Content**:
  - **角色守卫**（`require_roles(*roles)`）：依赖工厂，返回一个 `Depends` 可用的依赖；**集合精确匹配，不做层级包含**
  - **不存在「admin 通吃」**：HR 侧路由必须**显式写出两个角色** `require_roles("admin", "hr")`，candidate 单独一个；admin **不能**调用候选人端接口，candidate **不能**调用 HR 端接口，两个方向都返回 403
  - **为什么显式列出**：显式是最容易评审的形式 —— 新增角色时不会有意外的放行。若做层级包含，加一个角色就可能悄悄放开一批端点
  - **守卫先于请求体校验**：即使 body 是空的，角色不符仍返回 403 而不是 400
  - **JWT 载荷中不放角色**：角色每次请求从数据库回读，因此「改角色 / 禁用账号」**立即生效**，不必等 token 过期
  - **三条数据隔离路径**：admin 返回 `None` 不过滤；hr 按 `created_by == 自己`；candidate 按资源归属（练习 / 简历）与**「持有该面试的有效邀请」**
  - **core 不反向依赖业务模块**：`core/deps.py` 对 `auth.models.User` 采用**函数体内延迟导入**，类型标注走 `if TYPE_CHECKING`
  - 源码位置：`backend/app/core/deps.py`（79 行）

#### Slide 32 - 模块⑥ auth：问题与解决（候选人隔离判据）

- **Layout**: 左侧「错误做法」灰块 vs 右侧「正确做法」蓝块；下方三组最小示意；底部一行结论
- **Content**:
  - **问题**：加入 `candidate` 角色后，原有的 HR 侧路由**只校验「已登录」** —— 候选人 token 可以直接调用 HR 接口
    - **解法**：权限守卫**收紧为多角色判定**，HR 侧全部接口显式校验 `admin` / `hr`，候选人侧校验 `candidate`。这是本期**强制项**，不是可选项
  - **问题**：候选人数据隔离**不能复用 `created_by` 判据** —— 候选人不是面试的创建者（那是 HR），按 `created_by` 过滤会让候选人**看不到自己的任何面试**
    - **解法**：候选人侧新增「**持有该面试的有效邀请**」这条独立校验路径（`get_interview_for_candidate`），不引入新机制，复用既有的邀请链
  - **问题**：用户名已被 `candidate` 占用时，直接复用账号会怎样？
    - **解法**：**必须校验密码一致**才复用（不符即 401「用户名或密码错误」）。否则「知道对方用户名」就等价于能把他人的账号绑到自己的邀请上，进而读到对方的面试。用户名已被 `hr` / `admin` 占用则 409（沿用「用户名已被占用」语义）
  - **问题**：被禁用的候选人账号能不能被复用绑定？
    - **解法**：**不得复用**（401）。绑定会消耗掉一次性邀请码，而该账号此后 `login` 与 `get_current_user` 都拒绝它 —— 候选人永远打不开这场面试，HR 也无法重新发码

### Part 5: 收获与展望

#### Slide 33 - 工程收获

- **Layout**: 单列 vertical_list 五条；每条编号 + 标题 + 一句话；右侧竖排佐证（测试 / 文件位置）
- **Visualization**: vertical_list (见 VII)
- **Content**:
  - **架构约束要能被测试钉住，而不是靠自觉** —— `test_architecture.py` 直接检查「router 不得引用 repository」「service 不得出现 `db.execute`」。写在文档里的约束会腐化，写成测试的不会
  - **让不该发生的事在结构上无从表达** —— `MatchedQuestion` 只有 id 与理由，没有题面字段；`CandidateFeedbackOut` 是白名单模型，分数不在里面就**根本没发给浏览器**。靠「前端不渲染」实现脱敏等于把分数发出去再要求它别看
  - **失败要显式，不要静默降级** —— 真实 Provider 失败不降级到 Mock，而是 502；AI 判分失败不阻塞作答，标记为「未判分」并可重判。「没有」与「坏了」必须可区分，否则线上只剩一种症状，无法定位
  - **先写设计契约，再写实现** —— 30 份模块计划书先定签名与字段表，再落代码。前端重建期抓到的五处「原型与真实契约对不上」，根因都是照着原型的内存 mock 写字段名，而不是对着接口文档核一遍
  - **测试方法本身要能被审查** —— 前端测试台曾用 `buttonIn(page,'登录')` 取按钮，取到的是文档顺序靠前的模式切换控件，两条断言全绿但什么都没测到。**「绿」可能只是「没测」的另一种说法**

#### Slide 34 - 已知局限与踩过的坑

- **Layout**: 单列 vertical_list 五条；每条「局限」+ 灰色小字「代价 / 缓解手段」
- **Visualization**: vertical_list (见 VII)
- **Content**:
  - **单进程部署是硬约束** —— SSE 运行注册表与刷题限流计数都在进程内，必须 `--workers 1`。要支持多 worker 须改用 Redis pub/sub 或 Celery + 结果后端
  - **评估与作答都不留历史版本** —— 同一面试只保留最近一次评估结果；HR 覆盖候选人作答时只保留最新内容
  - **邀请码明文存储** —— HR 需在系统内复制。缓解手段是长码 + 短有效期 + 一次性 + 可撤销
  - **刷题推荐只从池内挑** —— 候选池是 `min(size×4, 100)` 条，超出池上限时排在后面的题永远进不了推荐
  - **上传体积上限拦不住「服务器已收完请求体」** —— Starlette 在进入视图函数前已把请求体缓冲下来，`read(limit+1)` 省的是**我们的**内存，不是服务器的；真正在请求发出前拦住大文件的是**前端那道 `file.size` 预检**
  - **一条测试方法上的教训** —— 变异检查（把缺陷植回去、断言必须失败）至今做了 33 次，抓出 5 个真 bug + 6 处原型与真实契约的偏差。其中一个是**看截图看出来的，断言当时是绿的**

#### Slide 35 - 展望与结语

- **Layout**: 左侧 roadmap_vertical 六项规划（带「规划中」状态）；右侧结语区（大字号一句话 + 项目定位回扣）
- **Visualization**: roadmap_vertical (见 VII)
- **Content**:
  - **V1.1 规划**：报告分享链接 / 语音与视频面试、录音转写 / 保留简历原文件与「回看原件」/ 多候选人横向对比 / 后端 PDF 生成（脱离浏览器的批量导出）/ 候选人端导出自己的脱敏反馈
  - **结语**：一个把「出题工具」与「刷题 App」简单拼装**区分开**的产品 —— 简历由候选人单侧提交，同时驱动 HR 侧的补题与候选人侧的推荐，把原本互不相干的两端缝成一个闭环
  - 收束一句：**AI 在其中始终扮演辅助角色** —— 每一个 AI 产物都有人确认（HR 确认参考答案、确认准备提纲、确认最终报告）

---

## X. Speaker Notes Requirements

- **File naming**: 与 SVG 同名（`01_cover.svg` → `notes/01_cover.md`），主文档 `notes/total.md` 用 `#` 标题行分页
- **Total duration**: 约 40–45 分钟（35 页，技术页平均 60–90 秒，章节页 15–20 秒）
- **Notes style**: formal / 技术讲解型 —— 结论先行，术语首现给定义，避免项目内部行话（如「案卷工作台」「脊」）外泄
- **Presentation purpose**: instruct（技术解构与交接）
- **Audience calibration**: 讲给**懂 Web 后端但不熟悉本项目**的评审。每页备注需包含：本页结论、支撑要点、以及一个「如果被追问」的预备回答
- **第 ④ 段特别要求**：每个模块的备注必须点明「这里为什么要这么设计」，而不只是「这里做了什么」

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency uses `fill-opacity` / `stroke-opacity`; `rgba()` FORBIDDEN
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`
6. FORBIDDEN: `textPath`, `animate*`, `script`
7. Text characters: write typography & symbols as raw Unicode (em dash `—`, en dash `–`, `©`, `®`, `→`, NBSP, etc.); HTML named entities (`&nbsp;`, `&mdash;`, `&copy;`, `&reg;` …) are FORBIDDEN. XML reserved chars in text MUST be escaped as `&amp;` `&lt;` `&gt;` `&quot;` `&apos;` (e.g. `R&amp;D`, `error &lt; 5%`)
8. `marker-start` / `marker-end` conditionally allowed: `<marker>` must be in `<defs>`, `orient="auto"`, shape must be triangle / diamond / circle
9. `clipPath` conditionally allowed **only on `<image>` elements** — 本套不使用图片，因此 `clipPath` 全场禁用

### PPT Compatibility Rules:

- `<g opacity="...">` FORBIDDEN (group opacity); set on each child element individually
- Inline styles only; external CSS and `@font-face` FORBIDDEN
- **本套专属**：所有图标走 `tabler-outline`（`stroke-width: 2`）+ 技术栈页的 `simple-icons` 品牌标识；两库不可混用于同一概念

### 本套额外纪律

1. **不用投影** —— 所有面板为「白底 + 1px `#DCE5EE` 边 + 8px 圆角」
2. **序列图三要素必须齐全** —— 生命线（含参与者名）、激活条、带编号与方向的消息箭头；消息文字 13–14px
3. **代码块** —— `Consolas` 14px，背景 `#F2F6FA`，1px `#DCE5EE` 边；**代码必须来自真实源码**（行号与文件路径标注），不得凭空编写
4. **问题/解决语义色** —— 问题用 `#C62828`、解法用 `#2E7D32`，全篇一致，不得混用
5. **快照/实现事实优先于 PRD** —— 描述实现时以 `backend/app/**` 为准（产品说明书 §「本文的可信度基础」明确：与代码冲突时以代码为准）
