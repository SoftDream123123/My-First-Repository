"""端到端冒烟：对真实运行中的服务走通 PRD §5.3 的三条核心流程，外加候选人侧与刷题侧。

用法：

    1) 直连后端（后端单独跑在 8000）
       cd backend
       python -m uvicorn app.main:app --port 8000 --workers 1
       python scripts/smoke_e2e.py

    2) 经前端开发服务器（联调：前端 5173 + 后端 8000 都在跑）
       cd backend
       python scripts/smoke_e2e.py http://127.0.0.1:5173/api

    目标地址也可以用环境变量 SMOKE_BASE 指定，命令行参数优先。
    两种跑法覆盖的是同一套断言 —— 区别只在于请求是直连后端，还是先经 Vite 的
    `/api` 代理再落到后端。后者才能验证代理配置与前端侧的同源假设。
"""

import json
import os
import sys
import time

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000/api"
OK = "[OK]"
FAIL = "[FAIL]"

failures: list[str] = []


def resolve_base() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1].rstrip("/")
    return os.environ.get("SMOKE_BASE", DEFAULT_BASE).rstrip("/")


def check(label: str, condition: bool, extra: str = "") -> None:
    print(f"{OK if condition else FAIL} {label}{(' — ' + extra) if extra else ''}")
    if not condition:
        failures.append(label)


def login(client: httpx.Client, username: str, password: str) -> dict[str, str]:
    """登录并返回可直接用的鉴权头；失败时返回空 dict（调用方的 check 会记下来）。"""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        return {}
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    base = resolve_base()
    print(f"目标：{base}\n")

    # trust_env=False：本机装了系统级 HTTP 代理（注册表里的 127.0.0.1:7890），
    # httpx 默认会读它并把**回环地址的请求也交给代理**转发。代理能到 IPv4 回环、
    # 到不了 IPv6 回环 —— 于是目标一旦被解析成 ::1 就统统拿到 502。
    # 冒烟打的是本机服务，本就不该经代理。
    client = httpx.Client(base_url=base, timeout=60.0, trust_env=False)
    suffix = str(int(time.time()))

    # ---------------- 流程：登录 ----------------
    resp = client.post(
        "/auth/login", json={"username": "admin", "password": "admin12345"}
    )
    check("登录返回 200", resp.status_code == 200, str(resp.status_code))
    if resp.status_code != 200:
        print(resp.text)
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

    # ---------------- 报告导出（DOCX） ----------------
    resp = client.get(
        f"/interviews/{interview_id}/report/export",
        params={"format": "docx"},
        headers=headers,
    )
    check("报告导出 200", resp.status_code == 200, str(resp.status_code))
    check(
        "导出为 DOCX（ZIP 魔数 PK）",
        resp.content[:2] == b"PK" and len(resp.content) > 1000,
        f"{len(resp.content)} 字节",
    )
    check(
        "导出带 Content-Disposition 文件名",
        "filename" in resp.headers.get("content-disposition", ""),
        resp.headers.get("content-disposition", "")[:70],
    )

    # ==========================================================================
    #  第二段：候选人侧 + 刷题侧（联调重点 —— 走真实的路由与权限守卫）
    # ==========================================================================

    # ---------------- 候选人自助注册与登录 ----------------
    candidate_name = f"cand_{suffix}"
    candidate_password = "cand12345"
    resp = client.post(
        "/auth/register",
        json={"username": candidate_name, "password": candidate_password},
    )
    check("候选人注册 201", resp.status_code == 201, str(resp.status_code))
    check("注册响应不含 password_hash", "password_hash" not in resp.text)
    check("注册角色为 candidate", resp.json().get("role") == "candidate", str(resp.json().get("role")))

    cand = login(client, candidate_name, candidate_password)
    check("候选人登录成功", bool(cand))

    # ---------------- 候选人可见岗位（只含有题的） ----------------
    resp = client.get("/candidate/positions", headers=cand)
    check("候选人岗位列表 200", resp.status_code == 200, str(resp.status_code))
    visible_ids = [p["id"] for p in resp.json()]
    check("新建的岗位对候选人可见", position_id in visible_ids, str(visible_ids[:6]))

    # ---------------- 简历 CRUD ----------------
    resp = client.post(
        "/candidate/resumes",
        json={
            "title": f"简历-{suffix}",
            "content": "五年后端经验，熟悉 Python / MySQL / Redis，主导过订单系统重构。",
            "candidate_name": "张三",
            "candidate_contact": "zhangsan@example.com",
        },
        headers=cand,
    )
    check("创建简历 201", resp.status_code == 201, str(resp.status_code))
    resume_id = resp.json()["id"]

    resp = client.get(f"/candidate/resumes/{resume_id}", headers=cand)
    check("简历详情 200", resp.status_code == 200, str(resp.status_code))

    resp = client.put(
        f"/candidate/resumes/{resume_id}",
        json={"content": "五年后端经验，熟悉 Python / MySQL / Redis / Kafka。"},
        headers=cand,
    )
    check("更新简历 200", resp.status_code == 200, str(resp.status_code))
    check(
        "更新落到内容上",
        "Kafka" in resp.json().get("content", ""),
        resp.json().get("content", "")[:40],
    )

    # ---------------- 准备提纲（HR 侧，仅 ongoing/completed 可生成） ----------------
    resp = client.post(
        "/interviews",
        json={
            "position_id": position_id,
            "candidate_name": "李四",
            "candidate_contact": "lisi@example.com",
        },
        headers=headers,
    )
    check("创建第二个面试 201", resp.status_code == 201, str(resp.status_code))
    invited_interview = resp.json()["id"]

    resp = client.post(f"/interviews/{invited_interview}/prep", headers=headers)
    check("生成准备提纲 200", resp.status_code == 200, str(resp.status_code))

    resp = client.get(f"/interviews/{invited_interview}/prep", headers=headers)
    check("读取准备提纲 200", resp.status_code == 200, str(resp.status_code))
    check(
        "提纲含三个字段",
        {"outline", "focus_points", "question_plan"} <= set(resp.json()),
        str(list(resp.json())[:6]),
    )

    # 三部分都是**对象数组**（不是字符串数组），且必须整体覆盖式全传（API 文档 §8.14）
    resp = client.put(
        f"/interviews/{invited_interview}/prep",
        json={
            "outline": [
                {"seq": 1, "phase": "开场", "duration_min": 5, "notes": "自我介绍"},
                {"seq": 2, "phase": "项目深挖", "duration_min": 30, "notes": "订单系统重构"},
            ],
            "focus_points": [
                {"dimension": "专业能力", "point": "重构的取舍", "reason": "简历自述主导过重构"},
            ],
            "question_plan": [
                {
                    "question": "重构中最大的技术风险是什么？",
                    "intent": "考察风险识别",
                    "follow_ups": ["如果重来一次会怎么改？"],
                },
            ],
        },
        headers=headers,
    )
    check("更新准备提纲 200", resp.status_code == 200, str(resp.status_code))
    check(
        "更新后 edited_at 非空",
        resp.json().get("edited_at") is not None,
        str(resp.json().get("edited_at")),
    )

    # ---------------- 邀请码：HR 生成 → 候选人匿名激活 ----------------
    resp = client.post(f"/interviews/{invited_interview}/invitations", headers=headers)
    check("生成邀请码 201", resp.status_code == 201, str(resp.status_code))
    invite_code = resp.json().get("code")
    check("邀请码非空", bool(invite_code), str(invite_code))

    resp = client.get(f"/interviews/{invited_interview}/invitations", headers=headers)
    check("邀请列表 200", resp.status_code == 200, str(resp.status_code))
    check("邀请状态为 pending", resp.json()[0]["status"] == "pending", resp.json()[0]["status"])

    # accept 是全项目**唯一**的公开写端点：此时候选人还没有登录态。
    # 它只负责「绑定」，**不下发 token** —— 前端拿到 200 后再走一次 /auth/login
    # （见 src/pages/candidate-activate.js）。这里照同一条路径验证。
    invited_name = f"invited_{suffix}"
    invited_password = "invited12345"
    resp = client.post(
        f"/candidate/invitations/{invite_code}/accept",
        json={"username": invited_name, "password": invited_password},
    )
    check("凭邀请码激活 200", resp.status_code == 200, str(resp.status_code))
    check(
        "激活回报面试 id 与摘要",
        resp.json().get("interview_id") == invited_interview and "interview" in resp.json(),
        str(list(resp.json())),
    )
    activated = login(client, invited_name, invited_password)
    check("激活后可用该账号登录", bool(activated))
    check("重复激活被拒 (409)", client.post(
        f"/candidate/invitations/{invite_code}/accept",
        json={"username": f"dup_{suffix}", "password": "dup12345678"},
    ).status_code == 409)

    # ---------------- 候选人视角看面试 ----------------
    resp = client.get("/candidate/interviews", headers=activated)
    check("候选人面试列表 200", resp.status_code == 200, str(resp.status_code))
    check(
        "刚激活的面试在列表里",
        invited_interview in [i["id"] for i in resp.json()],
        str([i["id"] for i in resp.json()]),
    )

    resp = client.get(f"/candidate/interviews/{invited_interview}", headers=activated)
    check("候选人面试详情 200", resp.status_code == 200, str(resp.status_code))
    detail = resp.json()
    cand_questions = detail.get("questions") or detail.get("interview_questions") or []
    check("候选人拿到题目列表", len(cand_questions) > 0, f"{len(cand_questions)} 题")
    if cand_questions:
        print(f"   题目字段：{list(cand_questions[0])}")

    # ---------------- 关联简历 + 按简历补题 ----------------
    # 简历有主：只能用**自己**的那一份，挂别人的会被 403（API 文档 §10.7 的第一条）
    resp = client.post(
        "/candidate/resumes",
        json={
            "title": f"应邀简历-{suffix}",
            "content": "三年后端经验，做过订单系统的读写分离与缓存改造。",
        },
        headers=activated,
    )
    check("激活账号创建简历 201", resp.status_code == 201, str(resp.status_code))
    invited_resume_id = resp.json()["id"]

    resp = client.put(
        f"/candidate/interviews/{invited_interview}/resume",
        json={"resume_id": invited_resume_id},
        headers=activated,
    )
    check("候选人关联简历 200", resp.status_code == 200, str(resp.status_code))

    resp = client.put(
        f"/candidate/interviews/{invited_interview}/resume",
        json={"resume_id": resume_id},  # 上一位候选人的简历
        headers=activated,
    )
    check("关联他人简历被拒 (403)", resp.status_code == 403, str(resp.status_code))

    resp = client.get(f"/candidate/interviews/{invited_interview}", headers=activated)
    check(
        "详情回显已关联的简历",
        resp.json().get("resume_id") == invited_resume_id,
        str(resp.json().get("resume_id")),
    )

    resp = client.get(f"/interviews/{invited_interview}/resume", headers=headers)
    check("HR 可见候选人简历 200", resp.status_code == 200, str(resp.status_code))
    check(
        "HR 读到的是刚刚挂上的那份",
        resp.json().get("resume_id") == invited_resume_id,
        str(resp.json().get("resume_id")),
    )
    # HR 不该知道这份简历属于哪个 user（API 文档 §13.8）
    check("HR 视图不泄漏 created_by", "created_by" not in resp.text)

    resp = client.post(
        f"/interviews/{invited_interview}/questions/match",
        json={"count": 2},
        headers=headers,
    )
    check("按简历补题 200", resp.status_code == 200, str(resp.status_code))
    check(
        "补题回报实际追加数",
        resp.json().get("added_count") == 2,
        str(resp.json().get("added_count")),
    )

    # ---------------- 候选人作答 → 交卷 → 反馈 ----------------
    resp = client.get(f"/candidate/interviews/{invited_interview}", headers=activated)
    detail = resp.json()
    cand_questions = detail.get("questions") or detail.get("interview_questions") or []
    q_key = next(
        (k for k in ("interview_question_id", "id", "question_id") if cand_questions and k in cand_questions[0]),
        None,
    )
    check("题目项带可作答的 id 字段", q_key is not None, str(list(cand_questions[0]) if cand_questions else []))

    answered = 0
    for question in cand_questions:
        resp = client.post(
            f"/candidate/interviews/{invited_interview}/answers",
            json={"interview_question_id": question[q_key], "content": answer_text},
            headers=activated,
        )
        answered += resp.status_code == 200
    check("候选人逐题作答全部 200", answered == len(cand_questions), f"{answered}/{len(cand_questions)}")

    resp = client.get(f"/candidate/interviews/{invited_interview}/feedback", headers=activated)
    check(
        "未评估前反馈不可读（403/404/409）",
        resp.status_code in (403, 404, 409),
        str(resp.status_code),
    )

    resp = client.post(f"/candidate/interviews/{invited_interview}/submit", headers=activated)
    check("候选人交卷 200", resp.status_code == 200, str(resp.status_code))
    submit_result = resp.json()
    check(
        "交卷结果含提交时刻与作答数",
        {"submitted_at", "answered_count"} <= set(submit_result),
        str(submit_result),
    )
    check(
        "交卷作答数 = 已答题数",
        submit_result.get("answered_count") == len(cand_questions),
        f"{submit_result.get('answered_count')}/{len(cand_questions)}",
    )
    first_submitted_at = submit_result.get("submitted_at")

    # 交卷是**幂等**的：重复交卷 200，且 submitted_at 保持第一次的值
    resp = client.post(f"/candidate/interviews/{invited_interview}/submit", headers=activated)
    check("重复交卷 200（幂等）", resp.status_code == 200, str(resp.status_code))
    check(
        "重复交卷不刷新 submitted_at",
        resp.json().get("submitted_at") == first_submitted_at,
        str(resp.json().get("submitted_at")),
    )

    # 关键契约：交卷**不推进**面试状态 —— 何时算完成由 HR 决定
    resp = client.get(f"/interviews/{invited_interview}", headers=headers)
    check(
        "交卷后面试仍是 ongoing（状态由 HR 推进）",
        resp.json().get("status") == "ongoing",
        str(resp.json().get("status")),
    )

    resp = client.post(f"/interviews/{invited_interview}/evaluate", headers=headers)
    check(
        "未完成时不可评估 (409)",
        resp.status_code == 409,
        str(resp.status_code),
    )

    # HR 标记完成 → 才能评估
    resp = client.post(f"/interviews/{invited_interview}/complete", headers=headers)
    check("HR 标记完成 200", resp.status_code == 200, str(resp.status_code))

    resp = client.post(f"/interviews/{invited_interview}/evaluate", headers=headers)
    check("HR 评估邀请来的面试 202", resp.status_code == 202, str(resp.status_code))
    invited_stream = resp.json()["stream_url"].removeprefix("/api")
    with client.stream("GET", invited_stream, headers=headers) as response:
        for line in response.iter_lines():
            if line.startswith("data: ") and '"evaluated"' in line:
                break

    resp = client.get(f"/candidate/interviews/{invited_interview}/feedback", headers=activated)
    check("候选人读反馈 200", resp.status_code == 200, str(resp.status_code))
    check(
        "反馈不含去留判断",
        not any(k in resp.text for k in ("hire", "reject", "通过", "淘汰", "拒绝")),
        resp.text[:80],
    )

    # ---------------- 权限：候选人不得触碰 HR 端点 / 他人的数据 ----------------
    check("候选人访问 /interviews 被拒 (403)", client.get("/interviews", headers=activated).status_code == 403)
    check("候选人访问 /users 被拒 (403)", client.get("/users", headers=activated).status_code == 403)
    check(
        "候选人读他人简历被拒 (403/404)",
        client.get(f"/candidate/resumes/{resume_id}", headers=activated).status_code in (403, 404),
    )
    check(
        "候选人读他人面试被拒 (403/404)",
        client.get(f"/candidate/interviews/{interview_id}", headers=activated).status_code in (403, 404),
    )
    check(
        "HR 读候选人简历端点被拒 (403/404)",
        client.get(f"/candidate/resumes/{resume_id}", headers=headers).status_code in (403, 404),
    )

    # ---------------- 刷题侧全流程 ----------------
    resp = client.get("/practice/questions", headers=cand)
    check("取题 200", resp.status_code == 200, str(resp.status_code))
    bank = resp.json()
    check("取题返回 total + items 结构", {"total", "items"} <= set(bank), str(list(bank)[:5]))
    check("取题非空", len(bank.get("items", [])) > 0, str(bank.get("total")))

    resp = client.post("/practice/sessions", json={"size": 3, "resume_id": resume_id}, headers=cand)
    check("开始练习 201", resp.status_code == 201, str(resp.status_code))
    session = resp.json()["session"]
    session_id = session["id"]
    session_items = resp.json()["items"]
    check("会话题数 = 3", session["total"] == 3, str(session["total"]))
    check("会话状态 ongoing", session["status"] == "ongoing", session["status"])
    check("带入简历时回报匹配标志", "resume_match_applied" in resp.json())

    resp = client.get(f"/practice/sessions/{session_id}", headers=cand)
    check("会话详情 200", resp.status_code == 200, str(resp.status_code))

    first_item = session_items[0]["item_id"]
    resp = client.post(
        f"/practice/sessions/{session_id}/items",
        json={"item_id": first_item, "user_answer": "我通过引入二级缓存把 P99 从 800ms 降到 120ms。"},
        headers=cand,
    )
    check("提交作答 200", resp.status_code == 200, str(resp.status_code))
    check(
        "作答回报进度",
        resp.json().get("progress", {}).get("answered_count") == 1,
        str(resp.json().get("progress")),
    )

    resp = client.post(f"/practice/items/{first_item}/rescore", headers=cand)
    check("对未判分题重判 200", resp.status_code == 200, str(resp.status_code))

    resp = client.post(f"/practice/sessions/{session_id}/finish", headers=cand)
    check("结束练习 200", resp.status_code == 200, str(resp.status_code))
    summary = resp.json()
    check("小结状态 finished", summary.get("status") == "finished", str(summary.get("status")))
    check("小结含正确率与维度分解", {"accuracy", "by_dimension"} <= set(summary), str(list(summary)[:8]))

    resp = client.get("/practice/sessions", headers=cand)
    check("练习历史 200", resp.status_code == 200, str(resp.status_code))

    resp = client.get("/practice/wrong-book", params={"limit": 20}, headers=cand)
    check("错题本 200", resp.status_code == 200, str(resp.status_code))

    resp = client.get("/practice/stats", headers=cand)
    check("统计 200", resp.status_code == 200, str(resp.status_code))
    check("统计记到这次作答", resp.json().get("total_answered", 0) >= 1, str(resp.json().get("total_answered")))

    # ---------------- 错题本筛选 ----------------
    resp = client.get(
        "/practice/wrong-book",
        params={"limit": 20, "dimension": "专业能力"},
        headers=cand,
    )
    check("错题本按维度筛选 200", resp.status_code == 200, str(resp.status_code))

    # ---------------- 用户管理 ----------------
    new_hr = f"hr_{suffix}"
    resp = client.post(
        "/users",
        json={"username": new_hr, "password": "hr123456789", "role": "hr"},
        headers=headers,
    )
    check("创建 HR 账号 201", resp.status_code == 201, str(resp.status_code))
    new_hr_id = resp.json()["id"]

    resp = client.get("/users", headers=headers)
    check("用户列表 200", resp.status_code == 200, str(resp.status_code))
    check("用户列表不含密码", "password_hash" not in resp.text)

    resp = client.patch(f"/users/{new_hr_id}", json={"is_active": False}, headers=headers)
    check("停用账号 200", resp.status_code == 200, str(resp.status_code))
    check("停用后 is_active=false", resp.json().get("is_active") is False, str(resp.json().get("is_active")))
    check(
        "停用后无法登录 (401)",
        client.post("/auth/login", json={"username": new_hr, "password": "hr123456789"}).status_code == 401,
    )

    # ---------------- 数据隔离 ----------------
    resp = client.get("/auth/me", headers=headers)
    check("admin 可见全部面试", len(client.get("/interviews", headers=headers).json()) >= 2)

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
