"""FastAPI 应用装配：实例、CORS、全局异常处理器、路由注册、健康检查。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
            "message": err.get("msg", ""),
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
# 顺序按模块依赖方向：auth → position → question → interview → evaluation
# ai 模块不注册路由（它是被调用的能力包，无对外端点）。


def _register_routers() -> None:
    from app.auth.router import router as auth_router

    app.include_router(auth_router, prefix="/api")

    from app.position.router import router as position_router

    app.include_router(position_router, prefix="/api")

    from app.question.router import router as question_router

    app.include_router(question_router, prefix="/api")

    from app.interview.router import router as interview_router

    app.include_router(interview_router, prefix="/api")


_register_routers()
