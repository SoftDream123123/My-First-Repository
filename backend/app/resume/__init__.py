"""resume 模块：候选人侧纯文本简历。

本包被 interview / practice 单向依赖，自身**不依赖任何业务模块** ——
这是 PRD §9 的分层不变量（避免引入 practice ↔ interview 循环）。
"""
