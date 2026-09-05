#!/usr/bin/env python3
"""负面路径测试用假 codex：行为由环境变量 FAKE_BAD_MODE 控制。

FAKE_BAD_MODE:
  (空)             —— 和 test_fake_codex.py 完全一样（对照用）
  remote_ahead     —— coder 干完活 push 后，又在远端制造一个前端 commit，
                      并把本地 HEAD 回退一档（模拟远端漂移/本地落后）
  stale_review     —— reviewer 正常审完后，把 review_result.json 里的
                      commit 字段改写成错误值（模拟陈旧/串轮 verdict）
  fixer_fail       —— coder/review 正常（r1=FAIL），fixer 直接退出码 3
  coder_dirty      —— coder 正常提交后，再留下一个未提交的脏文件后退出 0

其余逻辑（写 numkit、真跑测试、提交）复用 test_fake_codex.py。
"""

import json
import os
import sys
from pathlib import Path

import test_fake_codex as F

MODE = os.environ.get("FAKE_BAD_MODE", "")
prompt = F.prompt  # test_fake_codex 导入时已从 stdin 读入


def bad_coder_remote_ahead() -> int:
    F.coder()  # 正常写码、commit、push
    # 制造“远端多一个 commit、本地落后一步”：
    F.git("commit", "--allow-empty", "-m", "ahead commit that the batch must reject")
    F.git("push", "-u", "origin", "main")
    F.git("reset", "--hard", "HEAD~1")
    return 0


def bad_coder_dirty() -> int:
    F.coder()  # 正常写码、commit、push
    (Path("numkit") / "stray_not_committed.py").write_text("# dirty file\n", encoding="utf-8")
    return 0


def bad_reviewer_stale() -> int:
    F.review()  # review() 会写 review_report.md + review_result.json
    artifacts = F.find_artifacts_dir()
    path = artifacts / "review_result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commit"] = "0" * 40  # 把被审 commit 改写成错误值（模拟陈旧 verdict）
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    if "You are an independent REVIEWER" in prompt:
        if MODE == "stale_review":
            return bad_reviewer_stale()
        F.review()
    elif "You are the FIXER" in prompt:
        if MODE == "fixer_fail":
            print("simulated fixer failure: exit 3", file=sys.stderr)
            return 3
        F.fix()
    else:
        if MODE == "remote_ahead":
            return bad_coder_remote_ahead()
        if MODE == "coder_dirty":
            return bad_coder_dirty()
        F.coder()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())