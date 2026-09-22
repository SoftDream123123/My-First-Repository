"""FastAPI 应用装配：实例、CORS、全局异常处理器、路由注册、健康检查。"""

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="AI 智能面试助手 API",
    description="HR/面试官助手 —— 出题、记录、评估、报告",
    version="0.1.0",
)

# ---- CORS（前后端分离；开发期前端经 Vite 代理，此处为不经代理时的兜底）----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------- 全局异常处理器 ----------------------------

# 字段级校验文案的中文对照表。
#
# 为什么要有它：pydantic 的词条是英文（`String should have at least 8 characters`），
# 而它会经 `detail.fields[].message` **直接显示在表单那个字段的下方**
# （前端 `components/form.js` 的 `fieldErrors().fromServer`）。所以不译的话，
# 用户看到的是英文。约束值从 `err["ctx"]` 取，让人知道该改到多少。
#
# 未命中的 type 一律**保留原文**：宁可露出英文，也不要盖掉未知错误的细节。
_VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "缺少必填字段",
    "string_too_short": "长度不足，至少需要 {min_length} 个字符",
    "string_too_long": "长度超出上限，最多 {max_length} 个字符",
    "too_short": "数量不足，至少需要 {min_length} 项",
    "too_long": "数量超出上限，最多 {max_length} 项",
    "greater_than": "取值必须大于 {gt}",
    "greater_than_equal": "取值不能小于 {ge}",
    "less_than": "取值必须小于 {lt}",
    "less_than_equal": "取值不能大于 {le}",
    "int_parsing": "必须是整数",
    "float_parsing": "必须是数字",
    "bool_parsing": "必须是布尔值",
    "string_type": "必须是字符串",
    "list_type": "必须是数组",
    "dict_type": "必须是对象",
    "literal_error": "取值不在允许范围内",
    "enum": "取值不在允许范围内",
    "string_pattern_mismatch": "格式不符合要求",
    "json_invalid": "不是合法的 JSON",
}


def _field_message(err: dict[str, Any]) -> str:
    """把 pydantic 的一条错误译成可直接展示的中文（未命中则保留原文）。"""
    # 自定义校验器 `raise ValueError("中文文案")` 走 value_error：pydantic 会给它
    # 加上 `Value error, ` 前缀，剥掉即可 —— 文案本身已经是中文。
    if err.get("type") == "value_error":
        return str(err.get("msg", "")).removeprefix("Value error, ")

    template = _VALIDATION_MESSAGES.get(err.get("type", ""))
    if template is None:
        return err.get("msg", "")

    # ctx 里带约束值（min_length / max_length / ge …）。缺键时退回原文，
    # 不要因为文案模板出错而丢掉整条错误信息。
    try:
        return template.format(**(err.get("ctx") or {}))
    except (KeyError, IndexError, ValueError):
        return err.get("msg", "")


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """业务异常 → 统一三字段响应。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI 参数校验失败（默认 422）→ 统一收口为 400 VALIDATION_ERROR。"""
    fields = [
        {
            "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
            "message": _field_message(err),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数不合法",
            "detail": {"fields": fields},
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """未预期异常兜底：记完整堆栈到日志，对外只给通用文案，不泄漏堆栈。"""
    logger.exception("未预期异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "detail": None,
        },
    )


# ------------------------------- 健康检查 -------------------------------


@app.get("/api/health", tags=["系统"], summary="健康检查（无需鉴权）")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------- 路由注册 -------------------------------
# 顺序按模块依赖方向：auth → position → question → resume → interview → evaluation
# ai 模块不注册路由（它是被调用的能力包，无对外端点）。


def _register_routers() -> None:
    from app.auth.router import router as auth_router

    app.include_router(auth_router, prefix="/api")

    from app.position.router import router as position_router

    app.include_router(position_router, prefix="/api")

    from app.question.router import router as question_router

    app.include_router(question_router, prefix="/api")

    # 候选人侧路由：与 HR 端点在 URL 上不重叠（/candidate/* 前缀），
    # 守卫也不同，故单独注册。
    from app.question.candidate_router import router as question_candidate_router

    app.include_router(question_candidate_router, prefix="/api")

    # 简历：由候选人单侧写入，被 interview 与 practice 单向依赖，
    # 因此注册在 interview 之前（顺序与依赖方向一致）。
    from app.resume.router import router as resume_router

    app.include_router(resume_router, prefix="/api")

    from app.interview.router import router as interview_router

    app.include_router(interview_router, prefix="/api")

    from app.interview.candidate_router import router as interview_candidate_router

    app.include_router(interview_candidate_router, prefix="/api")

    from app.evaluation.router import router as evaluation_router

    app.include_router(evaluation_router, prefix="/api")

    from app.evaluation.candidate_router import router as evaluation_candidate_router

    app.include_router(evaluation_candidate_router, prefix="/api")

    # 刷题是独立的业务线（不依赖 interview），放最后注册。
    from app.practice.router import router as practice_router

    app.include_router(practice_router, prefix="/api")


_register_routers()

# 启动期校验 AI Provider 配置（fail fast）：
# PROVIDER_NAME 取值非法、或选了 openai 却没配 Key，都在此直接失败，
# 而不是等到第一次调用 AI 才报错。
from app.ai.factory import validate_provider_config  # noqa: E402

validate_provider_config()


# --------------------------- 前端静态托管（可选） ---------------------------
# 前端构建产物 frontend/dist 存在时，由后端一并托管，于是**一个进程、一个端口**
# 就能打开完整应用 —— 根目录的「一键启动.bat」依赖这一点。
#
# 不存在时静默跳过：后端仍可单独作为纯 API 运行（pytest / smoke_e2e / 前端 dev
# 服务器经 Vite 代理联调都不受影响）。
#
# 为什么只挂 /assets 与 / 两个入口，而不是 StaticFiles 挂在 "/"：
# Starlette 按注册顺序匹配，Mount("/") 会兜住一切路径，此后**再动态注册的路由
# 都会被它抢先吞掉**（测试套件里 @app.get("/api/_test_unhandled") 就是这么失效的，
# 表现为 404 而非预期的 500）。前端是 hash 路由，服务端实际只需要这两个入口，
# 精确挂载既不牺牲功能，也不改变全局路由语义。
_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_INDEX_HTML = _DIST_DIR / "index.html"

if _INDEX_HTML.is_file():
    _assets_dir = _DIST_DIR / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend_index() -> FileResponse:
        return FileResponse(_INDEX_HTML)

    logger.info("前端静态托管已启用：%s", _DIST_DIR)
else:
    logger.info("未找到 %s，跳过前端托管（纯 API 模式）", _INDEX_HTML)
