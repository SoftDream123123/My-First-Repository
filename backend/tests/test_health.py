"""健康检查与全局错误响应格式测试。"""


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_no_auth_required(client):
    """健康检查无需 token。"""
    assert client.get("/api/health").status_code == 200


def test_validation_error_shape(client):
    """请求体校验失败 → 400（而非 FastAPI 默认的 422），且为三字段格式。"""
    resp = client.post("/api/auth/login", json={"username": "only-username"})
    assert resp.status_code == 400

    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "VALIDATION_ERROR"
    assert isinstance(body["message"], str) and body["message"]


def test_validation_error_detail_has_fields(client):
    resp = client.post("/api/auth/login", json={})
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    fields = body["detail"]["fields"]
    assert isinstance(fields, list) and fields
    assert all("field" in f and "message" in f for f in fields)


def test_unauthorized_error_shape(client):
    """未携带 token → 401，三字段格式。"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401

    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "UNAUTHORIZED"


def test_unhandled_exception_shape(client):
    """未预期异常 → 500，三字段格式，且响应体不含堆栈。"""
    from app.main import app

    @app.get("/api/_test_unhandled")
    def _boom():  # pragma: no cover - 仅供本测试触发
        raise RuntimeError("internal detail that must not leak")

    resp = client.get("/api/_test_unhandled")
    assert resp.status_code == 500

    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "INTERNAL_ERROR"
    assert body["detail"] is None

    raw = resp.text
    assert "Traceback" not in raw
    assert "internal detail that must not leak" not in raw
