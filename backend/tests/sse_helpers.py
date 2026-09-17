"""SSE 测试辅助：读取事件流、等待后台评估结束。

抽出来是因为 e2e 流程测试与 evaluation SSE 测试都需要同样的读流逻辑。
"""

import json
import time

from app.evaluation import stream

TERMINAL_EVENTS = ("done", "error")


def read_events(client, url, headers, stop_on=TERMINAL_EVENTS):
    """读取 SSE 流直到终结事件，返回 [(event_name, payload), ...]。"""
    events: list[tuple[str | None, dict]] = []
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        name = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                events.append((name, payload))
                if name in stop_on:
                    break
    return events


def wait_until_finished(interview_id, timeout=15.0):
    """等待后台评估任务脱离 RUNNING，返回其运行记录。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = stream.get_run(interview_id)
        if run is not None and run.status != stream.RUN_RUNNING:
            return run
        time.sleep(0.05)
    raise AssertionError("评估未在超时内结束")
