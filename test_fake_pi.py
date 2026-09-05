#!/usr/bin/env python3
"""atfile-style 假 pi：验证 @prompt argv 传递链路 + fail-loud + A/B2 场景。（零 API）

默认剧本（无环境变量）—— 场景 5：
  最后一个 argv 必须是 '@<提示词文件>'，读出后直接退出码 3，
  模拟审查 agent 炸掉，期望终态 failed_review。

链完整性靠退出码区分：
  rc=3   提示词正确经 @文件 收到（agent 按剧本炸掉） -> 期望 failed_review
  rc=4   没有收到 @文件 参数（runner 装配出错）       -> 同样是 failed_review，
        但 rc 不同，可直接从日志看出装配失效而非剧本执行。

FAKE_PI_MODE 环境变量选择 A/B2 场景剧本（都要求先完整收到 @提示词，收不到一律 rc=4）：
  infra   打一行 "Connection error." 后 rc=3 —— A 标记字轨：真工作后断线的形态；
  zombie  整个会话沉睡 1 小时、不写任何文件 —— B2 假死探测样本
          （进程活着、工作区 mtime 停摆，等 controller 杀它换人）；
  ok      真审查员替身：实现 C.review 协议 —— 解析 @提示词，在工作区写入
          review_result.json + review_report.md 后 rc=0（真实验证链路）。
"""

import json
import os
import re
import sys
from pathlib import Path

MODE = os.environ.get("FAKE_PI_MODE", "scripted")

prompt_arg = [a for a in sys.argv[1:] if a.startswith("@")]
if not prompt_arg:
    sys.exit(4)
p = Path(prompt_arg[0][1:])
if not p.is_file():
    sys.exit(4)
try:
    prompt = p.read_text(encoding="utf-8")
except Exception:
    sys.exit(4)

if MODE == "infra":
    print("Connection error.")
    sys.exit(3)

if MODE == "zombie":
    # 睡到天荒地老不写盘：controller 的 B2 判死应该在 zombie_after_secs 后杀掉
    import time
    time.sleep(3600)
    sys.exit(3)

if MODE == "ok":
    # 真审查替身：跟真实 reviewer 一样从提示词里读出裁决文件的落盘位置
    # （提示词里写的是绝对路径：Write two files into <artifacts_dir>:）
    m = re.search(r"Write two files into (\S+):", prompt)
    artifacts = Path(m.group(1)).expanduser() if m else Path(os.getcwd())
    artifacts.mkdir(parents=True, exist_ok=True)
    rm = re.search(r"\"round\": (\d+)", prompt)
    round_no = int(rm.group(1)) if rm else 0
    cm = re.search(r"commit: ([0-9a-f]{40})", prompt)
    commit = cm.group(1) if cm else ""
    verdict = {"status": "FAIL", "commit": commit, "round": round_no,
               "summary": "numkit.conversions.__init__ 缺 docstring",
               "fix_requests": [{"id": f"R{round_no}-docstring", "check": "init docstring",
                                  "observed": "missing", "expected": "docstring",
                                  "command": "grep __init__", "path": "numkit/conversions/__init__.py"}]}
    if round_no >= 2:
        verdict = {"status": "PASS", "commit": commit, "round": round_no,
                   "summary": "fake review accepted", "fix_requests": []}
    (artifacts / "review_result.json").write_text(json.dumps(verdict), encoding="utf-8")
    (artifacts / "review_report.md").write_text(
        f"# fake review r{round_no}\n\n"
        f"REVIEW_STATUS: {verdict['status']}\n", encoding="utf-8")
    print(f"review r{round_no}: {verdict['status']} -> {artifacts}")
    sys.exit(0)

# 默认剧本
sys.exit(3)