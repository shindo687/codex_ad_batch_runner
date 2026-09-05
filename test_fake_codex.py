#!/usr/bin/env python3
"""Fake codex for v4pro loop plumbing tests.

Replaces the codex binary (``--codex-command 'python3 .../test_fake_codex.py'``)
so the full controller/agent/git/GitHub loop can be exercised with real
repositories and real Issue comments but zero codex API cost.

Behavior per role (role detected from the stdin prompt):

- coder:    writes a correct numkit package WITHOUT the module docstring
            (the reviewer will fail it), runs tests, commits.
- review:   runs the tests for real, audits numkit/__init__.py for a module
            docstring, writes review_report.md + review_result.json.
            No docstring -> FAIL (one fix request); docstring -> PASS.
- fix:      adds the module docstring, re-runs tests, commits.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

prompt = sys.stdin.read()

MODE = os.environ.get("FAKE_CODEX_MODE", "")

AD_HINT = "Keep every deliverable and piece of evidence under"
REVIEW_HINT = "Write two files into"
FIX_HINT = "update the evidence under"


def find_artifacts_dir() -> Path:
    for phrase in (REVIEW_HINT, AD_HINT, FIX_HINT):
        m = re.search(phrase + r"\s*:?\s*(\S+)", prompt)
        if m:
            return Path(m.group(1).rstrip(":"))
    return Path("artifacts")


def run_tests(workdir: Path, log_path: Path) -> int:
    p = subprocess.run(["python3", "-m", "unittest", "discover"], cwd=str(workdir),
                       text=True, capture_output=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((p.stdout or "") + "\n" + (p.stderr or ""), encoding="utf-8")
    return p.returncode


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={p.returncode}: {p.stderr.strip()}")
    return p.stdout.strip()


def coder() -> None:
    # 与真流程一致：工作目录开头是空的，coder 自己从 GitHub 克隆仓库。
    m = re.search(r"git clone (\S+)", prompt)
    repo_url = m.group(1) if m else ""
    if repo_url.endswith("."):
        repo_url = repo_url[:-1].rstrip()
    if repo_url and not Path(".git").exists():
        # 克隆到当前目录（当前目录必须为空，与 remote_agent 的检查一致）
        git("clone", "--quiet", repo_url, ".")
    base = Path("numkit")
    base.mkdir(exist_ok=True)
    tests = Path("tests")
    tests.mkdir(exist_ok=True)
    (tests / "__init__.py").write_text("", encoding="utf-8")
    Path(".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (base / "__init__.py").write_text(
        'def add(a, b):\n    return a + b\n\n'
        'def safe_div(a, b):\n    if b == 0:\n        raise ValueError("safe_div: division by zero")\n'
        '    return a / b\n\n'
        'def fib(n):\n    if isinstance(n, bool) or not isinstance(n, int):\n'
        '        raise ValueError("fib: n must be an integer")\n'
        '    if n < 0:\n        raise ValueError("fib: n must be >= 0")\n'
        '    if n == 0:\n        return 0\n'
        '    a, b = 0, 1\n'
        '    for _ in range(n - 1):\n        a, b = b, a + b\n'
        '    return b if n >= 1 else 0\n\n'
        'def fact(n):\n'
        '    if isinstance(n, bool) or not isinstance(n, int):\n'
        '        raise ValueError("fact: n must be an integer")\n'
        '    if n < 0:\n        raise ValueError("fact: n must be >= 0")\n'
        '    out = 1\n'
        '    for k in range(2, n + 1):\n        out *= k\n'
        '    return out\n',
        encoding="utf-8")
    (tests / "test_numkit.py").write_text(
        'import unittest\nimport numkit\n\n\n'
        'class TestNumkit(unittest.TestCase):\n'
        '    def test_add(self):\n        self.assertEqual(numkit.add(2, 3), 5)\n'
        '    def test_safe_div_ok(self):\n        self.assertEqual(numkit.safe_div(6, 3), 2.0)\n'
        '    def test_safe_div_zero(self):\n'
        '        with self.assertRaisesRegex(ValueError, "division by zero"):\n'
        '            numkit.safe_div(1, 0)\n'
        '    def test_fib(self):\n        self.assertEqual([numkit.fib(n) for n in range(8)], [0, 1, 1, 2, 3, 5, 8, 13])\n'
        '    def test_fib_negative(self):\n'
        '        with self.assertRaisesRegex(ValueError, ">= 0"):\n'
        '            numkit.fib(-3)\n'
        '    def test_fact(self):\n        self.assertEqual(numkit.fact(5), 120)\n'
        '    def test_fact_negative(self):\n'
        '        with self.assertRaisesRegex(ValueError, ">= 0"):\n'
        '            numkit.fact(-1)\n', encoding="utf-8")
    Path("README.md").write_text(
        "# numkit\n\nFunctions: add, safe_div, fib, fact.\n\n"
        "Errors: safe_div raises ValueError on zero divisor; fib/fact raise\n"
        "ValueError on negative or non-integer input.\n\n"
        "Run the tests: `python3 -m unittest`\n", encoding="utf-8")
    artifacts = find_artifacts_dir()
    rc = run_tests(Path("."), artifacts / "test_run_coder.log")
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "summary_coder.md").write_text(
        f"commands run:\n- python3 -m unittest  (exit {rc})\n"
        f"- git status / git log showing commit of files\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "feat: implement numkit package with tests")
    git("push", "-u", "origin", "main")
    if rc != 0:
        print(f"note: unit tests exit {rc}", file=sys.stderr)


def review() -> None:
    artifacts = find_artifacts_dir()
    rc = run_tests(Path("."), artifacts / "review_test.log")
    init = Path("numkit/__init__.py")
    has_docstring = init.is_file() and init.read_text(encoding="utf-8").lstrip().startswith('"""')
    head = git("rev-parse", "HEAD")
    git_status = git("status", "--porcelain")
    m = re.search(r"round-(\d+)", prompt)
    round_no = int(m.group(1)) if m else -1
    status = "PASS" if (rc == 0 and has_docstring and not git_status.strip()) else "FAIL"
    fix_requests = []
    if status == "FAIL":
        if not has_docstring:
            fix_requests.append({
                "id": "R1-docstring",
                "check": "code quality: module docstring",
                "observed": "numkit/__init__.py has no module docstring",
                "expected": "a one-line module docstring describing the package",
                "command": "python3 -c \"import numkit; print(numkit.__doc__)\"",
                "path": "numkit/__init__.py",
            })
    evidence = [{
        "item": "tests",
        "status": "PASS" if rc == 0 else "FAIL",
        "command": "python3 -m unittest discover",
        "totals": "see review_test.log",
        "path": str(artifacts / "review_test.log"),
    }]
    report_lines = [
        f"# review report: commit {head}",
        f"- clean tree: {'yes' if not git_status.strip() else 'NO'}\n",
        f"- module docstring present: {'yes' if has_docstring else 'no'}",
        f"- python3 -m unittest discover exit code: {rc}",
        f"- log: {artifacts / 'review_test.log'}\n",
        f"REVIEW_STATUS: {status}",
    ]
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "review_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    import json
    verdict = {"status": status,
               "commit": head, "round": round_no,
               "summary": "all checks pass" if status == "PASS" else "missing module docstring",
               "fix_requests": fix_requests, "evidence": evidence}
    (artifacts / "review_result.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fix() -> None:
    # 与真流程一致：先与 GitHub 同步，确保起点 = origin/main。
    git("fetch", "origin")
    git("reset", "--hard", "origin/main")
    init = Path("numkit/__init__.py")
    text = init.read_text(encoding="utf-8")
    if not text.lstrip().startswith('"""'):
        init.write_text('"""numkit: tiny numeric helpers for the v4pro loop test."""\n' + text,
                        encoding="utf-8")
    artifacts = find_artifacts_dir()
    rc = run_tests(Path("."), artifacts / "test_run_fix.log")
    git("add", "-A")
    git("commit", "-m", "fix: add numkit module docstring (review round fix)")
    git("push", "-u", "origin", "main")
    if rc != 0:
        print(f"note: unit tests exit {rc}", file=sys.stderr)


def main() -> int:
    if MODE == "infra_pollute":
        # 场景 9：coder 基础设施故障剧本 —— 模拟 agent 在 coder 工作区里留下
        # 半成品文件后断线（秒死 + 标记字命中 infralike），逼 controller 走
        # R1 的 clean-dir 清理后再 failover。若没清理，下一位 coder 会永远卡
        # "workdir not empty"。
        Path("half_done.py").write_text("# polluted by a dying coder\n", encoding="utf-8")
        print("Connection error.")
        return 3
    if "You are an independent REVIEWER" in prompt:
        review()
    elif "You are the FIXER" in prompt:
        fix()
    else:
        coder()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())