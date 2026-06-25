import argparse
import json
import sys
import time
from urllib import request

# Windows CMD/PowerShell 默认 GBK，Open-AutoGLM 日志含 emoji，需强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str) -> dict:
    with request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--task", default="打开设置查看WLAN")
    args = parser.parse_args()

    created = post_json(f"{args.base}/tasks", {"task": args.task, "mode": args.mode})
    task_id = created["task_id"]
    print(f"created task_id={task_id} mode={args.mode}")

    last_log_count = 0
    while True:
        task = get_json(f"{args.base}/tasks/{task_id}")
        logs = task.get("logs", [])
        for line in logs[last_log_count:]:
            print(line)
        last_log_count = len(logs)
        status = task.get("status")
        if status in ("success", "failed"):
            print(f"final status={status}")
            if task.get("error"):
                print(f"error={task['error']}")
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
