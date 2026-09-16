"""端到端冒烟：对真实运行中的 uvicorn 服务走通 PRD §5.3 的三条核心流程。

用法：先启动服务，再运行本脚本
    python -m uvicorn app.main:app --port 8000 --workers 1
    python scripts/smoke_e2e.py
"""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api"
OK = "[OK]"
FAIL = "[FAIL]"

failures: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    print(f"{OK if condition else FAIL} {label}{(' — ' + extra) if extra else ''}")
    if not condition:
        failures.append(label)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    client = httpx.Client(base_url=BASE, timeout=60.0)
    suffix = str(int(time.time()))

    # ---------------- 流程：登录 ----------------
    resp = client.post(
        "/auth/login", json={"username": "admin", "password": "admin12345"}
    )
    check("登录返回 200", resp.status_code == 200, str(resp.status_code))
    if resp.status_code != 200:
        return 1

    body = resp.json()
    check("响应含 token", bool(body.get("token")))
    check("响应不含 password_hash", "password_hash" not in resp.text)
    headers = {"Authorization": f"Bearer {body['token']}"}

    # ---------------- 流程①：岗位 + 题库 ----------------
    resp = client.post(
        "/positions",
        json={
            "name": f"后端工程师-{suffix}",
            "jd": "负责后端服务的设计、开发与维护，要求熟悉 Python、MySQL 与分布式系统。",
            "evaluation_dimensions": ["沟通能力", "专业能力", "逻辑思维"],
        },
        headers=headers,
    )
    check("创建岗位 201", resp.status_code == 201, str(resp.status_code))
    position_id = resp.json()["id"]

    for i, dimension in enumerate(["沟通能力", "专业能力", "逻辑思维"]):
        resp = client.post(
            "/questions",
            json={
                "position_id": position_id,
                "dimension": dimension,
                "content": f"请描述一次你在{dimension}方面解决复杂问题的经历（题库题目 {i + 1}）。",
            },
            headers=headers,
        )
        check(f"创建题目 {i + 1} 201", resp.status_code == 201, str(resp.status_code))

    resp = client.get("/questions", params={"position_id": position_id}, headers=headers)
    check("题库筛选返回 3 题", len(resp.json()) == 3, str(len(resp.json())))

    # ---------------- 流程①：创建面试（同步出题） ----------------
    resp = client.post(
        "/interviews",
        json={
            "position_id": position_id,
            "candidate_name": "张三",
            "candidate_contact": "zhangsan@example.com",
        },
        headers=headers,
    )
    check("创建面试 201", resp.status_code == 201, str(resp.status_code))
    if resp.status_code != 201:
        print(resp.text)
        return 1

    interview = resp.json()
    interview_id = interview["id"]

    check("状态为 ongoing", interview["status"] == "ongoing", interview["status"])
    check("题目数 = 8 (N=5 + M=3)", interview["question_count"] == 8, str(interview["question_count"]))

    seqs = [q["seq"] for q in interview["questions"]]
    check("seq 从 1 连续", seqs == list(range(1, 9)), str(seqs))

    # 题库只有 3 题（每维度 1 题），轮询抽满 3 题后差额转给 AI：
    # need_ai = M + (N - K) = 3 + (5 - 3) = 5
    sources = [q["source"] for q in interview["questions"]]
    check(
        "题库不足时由 AI 补齐（3 题库 + 5 AI）",
        sources == ["bank"] * 3 + ["ai"] * 5,
        str(sources),
    )
    check(
        "题库题排在 AI 题之前",
        sources.index("ai") == sources.count("bank"),
        str(sources),
    )

    check(
        "每题都有维度与题干快照",
        all(q["dimension"] and q["content"] for q in interview["questions"]),
    )

    resp = client.get("/questions", params={"position_id": position_id, "source": "ai"}, headers=headers)
    check("AI 题目已收录进题库", len(resp.json()) == 5, str(len(resp.json())))

    # ---------------- 流程②：录入回答 ----------------
    answer_text = (
        "我主导过一次订单系统的重构项目，通过引入 Redis 缓存与分库分表，"
        "把接口 P99 延迟从 800ms 降到 120ms，支撑了日均 500 万订单。"
    )
    for question in interview["questions"]:
        resp = client.post(
            f"/interviews/{interview_id}/answers",
            json={
                "interview_question_id": question["interview_question_id"],
                "content": answer_text,
            },
            headers=headers,
        )
        if resp.status_code != 200:
            check("保存回答 200", False, str(resp.status_code))
            break
    else:
        check("逐题保存回答 200", True)

    resp = client.get(f"/interviews/{interview_id}", headers=headers)
    check("详情已回答数 = 8", resp.json()["answered_count"] == 8, str(resp.json()["answered_count"]))

    resp = client.post(f"/interviews/{interview_id}/complete", headers=headers)
    check("标记完成 200", resp.status_code == 200, str(resp.status_code))
    check("状态变 completed", resp.json()["status"] == "completed", resp.json()["status"])
    check("completed_at 非空", resp.json()["completed_at"] is not None)

    resp = client.post(
        f"/interviews/{interview_id}/answers",
        json={
            "interview_question_id": interview["questions"][0]["interview_question_id"],
            "content": "完成后尝试修改",
        },
        headers=headers,
    )
    check("完成后禁止改回答 (409)", resp.status_code == 409, str(resp.status_code))

    # ---------------- 流程③：流式评估 ----------------
    resp = client.post(f"/interviews/{interview_id}/evaluate", headers=headers)
    check("触发评估返回 202", resp.status_code == 202, str(resp.status_code))
    # stream_url 是相对站点根的绝对路径（含 /api），而本客户端的 base_url 已含 /api
    stream_path = resp.json()["stream_url"].removeprefix("/api")

    events: list[tuple[str, dict]] = []
    with client.stream("GET", stream_path, headers=headers) as response:
        check("SSE 响应 200", response.status_code == 200, str(response.status_code))
        check(
            "Content-Type 为 text/event-stream",
            response.headers.get("content-type", "").startswith("text/event-stream"),
        )
        name = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[len("data: ") :])))
                if name in ("done", "error"):
                    break

    names = [n for n, _ in events]
    check(
        "事件序列 = 8×question + 3×dimension + report + done",
        names == ["question"] * 8 + ["dimension"] * 3 + ["report", "done"],
        str(names[:5]) + f" ... 共 {len(names)} 条",
    )

    question_events = [p for n, p in events if n == "question"]
    check("逐题事件含分数与评语", all("score" in p and "comment" in p for p in question_events))
    check(
        "逐题分均在 0-10",
        all(0.0 <= p["score"] <= 10.0 for p in question_events),
        str([p["score"] for p in question_events]),
    )

    report_event = next((p for n, p in events if n == "report"), {})
    check("报告事件含四项输出", {"overall_score", "conclusion", "strengths", "weaknesses"} <= set(report_event))

    # ---------------- 报告查询 ----------------
    resp = client.get(f"/interviews/{interview_id}/report", headers=headers)
    check("报告接口 200", resp.status_code == 200, str(resp.status_code))

    report = resp.json()
    check("总分在 0-10", 0.0 <= report["overall_score"] <= 10.0, str(report["overall_score"]))
    check("维度分覆盖 3 个维度", len(report["dimension_scores"]) == 3, str(len(report["dimension_scores"])))
    check("逐题明细 8 条", len(report["question_scores"]) == 8, str(len(report["question_scores"])))
    check(
        "逐题明细按 seq 升序",
        [q["seq"] for q in report["question_scores"]] == list(range(1, 9)),
    )
    check("结论非空", bool(report["conclusion"]))
    check("优点非空", bool(report["strengths"]))
    check("待改进非空", bool(report["weaknesses"]))

    print(f"\n   总分 {report['overall_score']}｜结论：{report['conclusion']}")

    # ---------------- 重新评估（替换语义） ----------------
    resp = client.post(f"/interviews/{interview_id}/evaluate", headers=headers)
    check("重新评估返回 202", resp.status_code == 202, str(resp.status_code))

    with client.stream("GET", stream_path, headers=headers) as response:
        for line in response.iter_lines():
            if line.startswith("data: ") and '"evaluated"' in line:
                break

    resp = client.get(f"/interviews/{interview_id}/report", headers=headers)
    check(
        "重新评估为替换语义（仍 8 条，不翻倍）",
        len(resp.json()["question_scores"]) == 8,
        str(len(resp.json()["question_scores"])),
    )

    # ---------------- 数据隔离 ----------------
    resp = client.get("/auth/me", headers=headers)
    check("admin 可见全部面试", len(client.get("/interviews", headers=headers).json()) >= 1)

    # ---------------- 权限与错误格式 ----------------
    resp = client.get("/interviews")
    check("无 token → 401", resp.status_code == 401, str(resp.status_code))
    check("401 为三字段格式", set(resp.json()) == {"code", "message", "detail"})

    resp = client.post("/positions", json={"name": ""}, headers=headers)
    check("非法请求体 → 400（非 422）", resp.status_code == 400, str(resp.status_code))

    print("\n" + "=" * 60)
    if failures:
        print(f"{FAIL} 共 {len(failures)} 项未通过：")
        for item in failures:
            print(f"     - {item}")
        return 1

    print(f"{OK} 端到端冒烟全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
