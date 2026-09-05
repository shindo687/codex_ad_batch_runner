#!/usr/bin/env python3
"""v4pro minimal controller: schedule tiny generic tasks on remote hosts.

One task at a time per host.  Each task walks the loop

    coder writes code      -> push + Ready
    reviewer (separate     -> REVIEW PASS|FAIL            (separate _reviewer dir)
    subdir)                    |
        FAIL & rounds left -> fixer amends in the coder dir -> Ready -> review
        PASS               -> merge gate -> MERGE -> accepted

This is the deliberately simplest runnable version of the batch runner.  It
is generic: the task text defines the work (could be a tiny Python package or
a real AD workload later); the controller only orchestrates dirs, git/GitHub
and review evidence.  All GitHub operations run on the worker host through
remote_agent.py, where the ``gh`` credentials live.

State: state/controller_state.json (this file only tracks the machine; every
piece of task evidence lives under the remote work root).
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_TASKS_CSV = ROOT / "tasks.csv"
DEFAULT_TASKS_DIR = ROOT / "tasks"
STATE_PATH = ROOT / "state" / "controller_state.json"
LOG_PATH = ROOT / "state" / "controller.log"

# 三个干活角色：coder（写码）、fix（修复员）、review（审查员）。
# 每个角色必须被显式指定 agent 列表，绝不缩回某个默认实现。
AGENT_ROLES = ("coder", "fix", "review")
AGENT_STYLES = ("stdin", "atfile", "argvfile")  # 提示词传递方式，见 remote_agent.runner_script

# 基础设施死亡判定（A：failover 依据之一）。注意只收“断通路”类短语，
# 不感冒丝级重合：真干砸的场景（剧本炸、测试失败断言）不应命中这些词。
AGENT_INFRA_MARKERS = (
    "connection error", "connection refused", "connection reset", "connection closed",
    "internal server error", "service unavailable", "rate limit", "429",
    "404 not found", "upstream", "proxy error", "network is unreachable",
    "temporarily unavailable", "econnrefused", "econnreset",
)


def infralike(outcome: Dict[str, Any]) -> bool:
    """rc≠0 的死因分类：infra（可换 agent 重开）vs real（真干砸，fail-loud）。

    双轨：
      1. 秒死规则：干活 <120 秒且日志 <1KiB（没来得及产出真内容）；
      2. 标记规则：日志尾含断通路短语（中途断线也会中，如 17 分钟后的
         Connection error）。
    duration 未知（缺失）时一律不当 infra —— 不能证明是 infra 就按 real 算，
    保持 fail-loud 不被软化。
    """
    duration = outcome.get("duration_seconds")
    if isinstance(duration, (int, float)) and duration < 120:
        if int(outcome.get("log_bytes") or 0) < 1024:
            return True
    tail = str(outcome.get("log_tail") or "").lower()
    return any(m in tail for m in AGENT_INFRA_MARKERS)


def _spec_list(cfg: Dict[str, Any], role: str, value: Any) -> List[Dict[str, Any]]:
    """把 roles 里的单值/列表值 + presets 解析成一列 agent 规格。"""
    presets = (cfg.get("agents") or {}).get("presets") or {}
    if isinstance(value, (list, tuple)):
        raw_names = [str(v).strip() for v in value]
    else:
        raw_names = [n.strip() for n in str(value or "").split(",")]
    names = [n for n in raw_names if n]
    if not names:
        raise SystemExit(
            f"agents: role {role!r} 没有显式指定 agent。"
            f"请在 config.json 的 agents.roles.{role} 或 tasks.csv 的 {role}_agent 列里指定（支持逗号列表）-> 中止")
    specs = []
    for name in names:
        spec = presets.get(name)
        if not spec:
            raise SystemExit(f"agents: role {role!r} 引用了未知 preset {name!r} -> 中止")
        style = str(spec.get("style") or "stdin").strip()
        if style not in AGENT_STYLES:
            raise SystemExit(f"agents: preset {name!r} 的 style {style!r} 不在 {AGENT_STYLES} -> 中止")
        cmd = str(spec.get("cmd") or "").strip()
        if not cmd:
            raise SystemExit(f"agents: preset {name!r} 的 cmd 为空 -> 中止")
        specs.append({"name": name, "cmd": cmd, "style": style,
                      "probe": spec.get("probe", {}) if isinstance(spec.get("probe"), dict) else {}})
    return specs


def resolve_agents(cfg: Dict[str, Any], task: "Task", role: str) -> List[Dict[str, Any]]:
    """把角色解析成最终执行的 agent 规格列表（有序 = 失效依序项）。

    优先级（都是显式配置，缺了就失败）：
      1. 命令行 --codex-command 全局覆盖（测试桩专用，作用于全部角色）；
      2. tasks.csv 里该行的 {role}_agent 列（指向 config.json agents.presets 里的名字）；
      3. config.json agents.roles.{role}（本批的默认指派，列表/单值/逗号串皆可）。
    """
    if cfg.get("codex_command"):
        return [{"name": "codex", "cmd": str(cfg["codex_command"]), "style": "stdin", "probe": {}}]
    roles_map = (cfg.get("agents") or {}).get("roles") or {}
    value: Any = (task.agents or {}).get(role, "").strip() or roles_map.get(role)
    return _spec_list(cfg, role, value)


def resolve_agent(cfg: Dict[str, Any], task: "Task", role: str) -> Dict[str, Any]:
    """兼容接口：取列表第一个，只暴露 {name, cmd, style}（历史单测用法）。"""
    spec = resolve_agents(cfg, task, role)[0]
    return {"name": spec["name"], "cmd": spec["cmd"], "style": spec["style"]}

TERMINAL_PHASES = {"accepted", "failed", "failed_timeout", "failed_publish",
                   "failed_review", "failed_fix", "blocked", "stopped"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stderr),
              logging.FileHandler(LOG_PATH, encoding="utf-8")],
)
LOGGER = logging.getLogger("v4pro")


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


@dataclass
class Task:
    task_id: str
    project: str
    worker: str
    task_file: Path
    timeout_minutes: int = 45
    max_fix_rounds: int = 3
    seed_url: str = ""
    seed_ref: str = ""  # "" = seed 仓库的默认分支（映射到任务仓的 main）
    # csv 行内按角色的 agent 覆盖（coder_agent/fix_agent/review_agent 列），可选
    agents: Dict[str, str] = field(default_factory=dict)

    @property
    def codex_timeout_seconds(self) -> int:
        return self.timeout_minutes * 60


@dataclass
class Host:
    """local or an ssh worker alias like adm1."""
    name: str
    remote_agent_dir: str = "~/codex_v4pro"
    python: str = "python3"
    pre_cmd: str = ""  # 每条 ssh 命令前注入（如补 PATH / source env 文件）；由 config hosts.<name>.pre_cmd 提供

    @property
    def is_local(self) -> bool:
        return self.name == "local"

    @staticmethod
    def remote_quote(s: str) -> str:
        """远端 shell 双引号包裹，并让 ~/$HOME 由远端展开（单引号会冻结展开）。

        入参都是 config 里的可信路径；只转义反斜杠与双引号。
        """
        if s.startswith("~"):
            s = "$HOME" + s[1:]
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def build_remote(pre_cmd: str, python: str, agent_path: str, cmd: str, payload_stdin: bool,
                     finish_marker: str = "") -> str:
        """构造远端命令串（含可选前缀），供单测与 agent() 共用。

        注意：python 与 agent_path 用 remote_quote 包裹（双引号语义，防 ~/$HOME 被冻结）。
        """
        out = (pre_cmd.rstrip() + " ") if pre_cmd.strip() else ""
        out += f"{Host.remote_quote(python)} {Host.remote_quote(agent_path)} {cmd}"
        if payload_stdin:
            out += " --payload-stdin"
        if finish_marker:
            out += f" >&2 && echo {Host.remote_quote(finish_marker)}"
        return out

    def agent_path(self) -> str:
        if self.is_local:
            return str(ROOT / "remote_agent.py")
        # 非 local：~ 留给远端 shell 展开（本地 expanduser 会把自己机器的 $HOME 路径推到 Linux）
        return self.remote_agent_dir.rstrip("/") + "/remote_agent.py"

    def sync_agent(self) -> None:
        if self.is_local:
            return  # runs straight from the working copy
        agent = ROOT / "remote_agent.py"
        remote_dir = self.remote_agent_dir  # 绝对路径或 ~/...都由远端展开
        rd_q = self.remote_quote(remote_dir)
        script = (
            f"mkdir -p {rd_q} && cat > {rd_q}/remote_agent.py "
            f"&& chmod +x {rd_q}/remote_agent.py"
        )
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.name, script],
                           input=agent.read_bytes(), capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(f"sync to {self.name} failed: {(p.stderr or p.stdout).decode(errors='replace').strip()[-400:]}")

    def agent(self, cmd: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 60) -> Dict[str, Any]:
        args = [self.python, self.agent_path(), cmd]
        if payload is not None:
            args.append("--payload-stdin")
        if self.is_local:
            p = subprocess.run([self.python, self.agent_path(), cmd, *(["--payload-stdin"] if payload is not None else [])],
                               input=json.dumps(payload) if payload is not None else None,
                               text=True, capture_output=True, timeout=timeout)
        else:
            remote = self.build_remote(self.pre_cmd, self.python, self.agent_path(), cmd,
                                       payload is not None)
            p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.name, remote],
                               input=json.dumps(payload) if payload is not None else None,
                               text=True, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise RuntimeError(f"{self.name}: agent {cmd} shell-rc={p.returncode}: {(p.stderr or p.stdout).strip()[-400:]}")
        try:
            return json.loads(p.stdout.strip())
        except ValueError:
            raise RuntimeError(f"{self.name}: agent {cmd} did not return JSON: {p.stdout.strip()[-300:]!r}")

    def cat(self, remote_path: str) -> str:
        """Read a known task file back (no gh, no secrets involved)."""
        if self.is_local:
            return Path(os.path.expanduser(remote_path)).read_text(encoding="utf-8")
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.name,
                            f"cat {self.remote_quote(remote_path)}"],
                           text=True, capture_output=True, timeout=30)
        if p.returncode != 0:
            raise RuntimeError(f"{self.name}: cat {remote_path} failed: {p.stderr.strip()[-300:]}")
        return p.stdout


class Runner:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.hosts: Dict[str, Host] = {}
        self.tasks: List[Task] = []
        self.state: Dict[str, Dict[str, Any]] = {}

    # ---------------- setup ----------------

    def host(self, name: str) -> Host:
        if name not in self.hosts:
            per_host = dict(self.cfg.get("hosts", {}).get(name, {}))
            self.hosts[name] = Host(name=name,
                                    remote_agent_dir=per_host.get("remote_agent_dir", self.cfg["remote_agent_dir"]),
                                    python=per_host.get("python", self.cfg.get("remote_python", "python3")),
                                    pre_cmd=per_host.get("pre_cmd", ""))
        return self.hosts[name]

    def load_tasks(self) -> None:
        csv_path = Path(self.cfg["tasks_csv"])
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        tasks = []
        for row in rows:
            tid = str(row.get("task_id") or "").strip()
            if not tid:
                continue
            tf = Path(str(row.get("task_file") or "").strip())
            if not tf:
                continue
            if not tf.is_absolute():
                tf = ROOT / tf
            agents = {}
            for role in AGENT_ROLES:
                col = str(row.get(f"{role}_agent") or "").strip()
                if col:
                    agents[role] = col
            tasks.append(Task(
                task_id=tid,
                project=str(row.get("project") or "").strip() or f"task{tid}",
                worker=str(row.get("worker") or "").strip() or self.cfg["workers"][0],
                task_file=tf,
                timeout_minutes=int(row.get("timeout_minutes") or self.cfg.get("timeout_minutes", 45)),
                max_fix_rounds=int(row.get("max_fix_rounds") or self.cfg.get("max_fix_rounds", 3)),
                seed_url=str(row.get("seed_url") or "").strip(),
                seed_ref=str(row.get("seed_ref") or "").strip(),
                agents=agents,
            ))
        self.tasks = tasks
        for t in tasks:
            if not t.task_file.is_file():
                raise RuntimeError(f"task {t.task_id}: task file missing: {t.task_file}")

    def load_state(self) -> None:
        data = read_json(STATE_PATH, {"schema": 1, "tasks": {}})
        self.state = data.get("tasks") or {}

    def save_state(self) -> None:
        # 原子写入：先写临时文件再 rename，读方永远看不到半截 JSON。
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"schema": 1, "tasks": self.state},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, STATE_PATH)

    # ---------------- naming ----------------

    def repo_name(self, task: Task) -> str:
        return f"{task.project}{self.cfg['repo']['suffix']}"

    def repo_url(self, task: Task) -> str:
        return f"https://github.com/{self.cfg['repo']['owner']}/{self.repo_name(task)}.git"

    def work_root(self) -> str:
        return os.path.expanduser(str(self.cfg["work_root"]))

    def coder_dir(self, task: Task) -> str:
        return f"{self.work_root().rstrip('/')}/{self.repo_name(task)}"

    def reviewer_root(self, task: Task) -> str:
        return f"{self.work_root().rstrip('/')}/{self.repo_name(task)}_reviewer"

    def task_dir(self, task: Task) -> str:
        return f"{self.work_root().rstrip('/')}/tasks/task-{task.task_id}"

    def artifacts_dir(self, task: Task) -> str:
        return f"{self.task_dir(task)}/artifacts"

    def remote_policy(self) -> str:
        return f"{self.host('adm1').remote_agent_dir}/policy/{Path(self.cfg['policy_file']).name}" if self.cfg.get("policy_file") else ""

    # ---------------- payloads ----------------

    def base_payload(self, task: Task) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "project": task.project,
            "work_root": self.work_root(),
            "task_dir": self.task_dir(task),
            "coder_dir": self.coder_dir(task),
            "reviewer_root": self.reviewer_root(task),
            "artifacts_dir": self.artifacts_dir(task),
            "repo_name": self.repo_name(task),
            "repo_url": self.repo_url(task),
            "seed": {"url": task.seed_url, "ref": task.seed_ref},
            "gh": dict(self.cfg["repo"]),
            "codex_command": self.cfg.get("codex_command", ""),
            "timeout_seconds": task.codex_timeout_seconds,
        }

    def coder_prompt(self, task: Task, issue_number: int, issue_body: str) -> str:
        policy_line = ""
        if self.cfg.get("policy_file"):
            policy_line = (f"- Read and obey this policy before working: {self.remote_policy()}\n")
        return f"""{issue_body}

==== v4pro batch execution metadata (must be followed) ====
- 以上任务正文是 controller 从 GitHub issue #{issue_number} 原样读取后交给你的；GitHub 上的这份是任务的唯一事实来源。
- Your working directory is {self.coder_dir(task)} and it is currently EMPTY. It will be the repository root.
  First clone the task repository from GitHub yourself:
      git clone {self.repo_url(task)} .
  Then work inside this directory.
- Work on git branch `main`. Focused commits with clear messages; record `git status`, branch and HEAD around your edits. Before finishing you MUST push: `git push origin main` (the machine verifies GitHub is up to date; a missing push fails the batch loudly).
- If git complains about author identity, set LOCAL user.name/user.email only (e.g. "v4pro coder"/"v4pro+coder@local"): never put any credential into git config or files.
- Do NOT create other repositories or issues (this repository and Issue were created by the system). Never commit credentials, keys, tokens, caches or logs.
- Keep every deliverable and piece of evidence under: {self.artifacts_dir(task)}
- Tests must actually run: write down exact commands, totals and exit codes. "Tests not run" is a failure.
{policy_line}
- This prompt and your logs are kept in {self.task_dir(task)}/logs/. Do not put passwords, API keys or tokens in any file you write.
""".strip()

    def review_prompt(self, task: Task, commit: str, prev: str, round_no: int) -> str:
        body = task.task_file.read_text(encoding="utf-8")
        prev_line = f"- Diff baseline (previous reviewed commit): {prev}\n" if prev else "- Diff baseline: the first commit of the repository.\n"
        return f"""You are an independent REVIEWER for v4pro task {task.task_id} ({task.project}).

The implementer pushed this commit to GitHub. You must NOT modify the coder repository.

Your working directory was cloned from the GitHub repository (verified on origin/main before cloning):
    repo: {self.repo_url(task)}
    commit: {commit}
    checkout: {reviewer_root_round(self, task, round_no)}
{prev_line}

Do this:
1. Record the branch, HEAD, whether the tree is clean, that `git remote -v` points to the GitHub repository above, and the diff from the baseline.
2. Re-run the tests required by the task (below). Record exact commands, totals, exit codes.
3. Check every acceptance criterion in the task text, and every previous fix request (if called with fix requests, they are in this prompt).
4. Write two files into {self.artifacts_dir(task)}:
   a. review_report.md  - the full readout; must end with exactly one line `REVIEW_STATUS: PASS` / `REVIEW_STATUS: FAIL` / `REVIEW_STATUS: BLOCKED`.
   b. review_result.json - machine verdict with schema:
      {{"status": "PASS|FAIL|BLOCKED", "summary": "...",
        "commit": "{commit}", "round": {round_no},
        "fix_requests": [{{"id": "R{round_no}-name", "check": "...", "observed": "...", "expected": "...", "command": "...", "path": "..."}}],
        "evidence": [{{"item": "...", "status": "PASS|FAIL", "command": "...", "totals": "...", "path": "..."}}]}}
   `commit` and `round` must be EXACTLY the values given above. A verdict that
   does not state the exact reviewed commit and round is treated as stale and the task is blocked.
   The machine posts this verdict to the GitHub Issue; malformed or missing JSON = BLOCKED.
5. Exit 0 only after both files are written; exit nonzero if the review cannot be completed.

You are a verifier, not a second implementer: a green worker exit code, an unrun test or a claimed result without the actual command/output is never a PASS.

==== task text under review ====
{body}
""".strip()

    def fix_prompt(self, task: Task, fix_requests: List[Dict[str, Any]], round_no: int) -> str:
        reqs = json.dumps(fix_requests, ensure_ascii=False, indent=2)
        return f"""You are the FIXER for v4pro task {task.task_id} ({task.project}).

The independent reviewer FAILED commit review round {round_no}. Fix the code in the implementer repository (your working directory):
    {self.coder_dir(task)}

Rules:
0. Sync with GitHub first: in your working directory run `git fetch origin && git reset --hard origin/main`; your starting point must be exactly what GitHub holds.
1. Read the fix requests below (also saved to {self.artifacts_dir(task)}/fix_request.json).
2. Modify ONLY the implementer repository in your working directory. Use git: focused commits with clear messages that reference the reviewed commit and review round.
3. Re-run the affected tests; record commands, totals, exit codes and update the evidence under {self.artifacts_dir(task)}.
4. Do NOT delete or move earlier attempt logs or artifacts.
5. Exit 0 only after committing your fix AND pushing it: `git push origin main`.

==== fix requests ====
{reqs}

==== original task text ====
{task.task_file.read_text(encoding='utf-8')}
""".strip()

    # ---------------- remote steps ----------------

    def remote_start(self, task: Task, role: str, prompt: str, round_no: int,
                     commit: str = "", prev: str = "", fix_requests: Optional[List] = None) -> Optional[Dict[str, Any]]:
        """派工入口（A：探针预检 + 依序选人）。

        从角色 agent 列表里按失效轮转位置依次探活：探针不过的跳过；
        全都不健康时返回 None（step 里 park 计数，直到预算打满落终态）。
        """
        sid = task.task_id
        st = self.state.setdefault(sid, {})
        specs = resolve_agents(self.cfg, task, role)
        n = len(specs)
        idx = int(st.get(f"{role}_agent_idx") or 0) % n
        worker = self.host(task.worker)
        for offset in range(n):
            i = (idx + offset) % n
            spec = specs[i]
            if not self._agent_probe_ok(task, role, spec):
                LOGGER.warning("task %s: %s probe failed for agent=%s，试下一个", sid, role, spec["name"])
                continue
            st[f"{role}_agent_idx"] = i
            st["probe_fails"] = 0
            payload = self.base_payload(task)
            payload.update({"role": role, "prompt": prompt,
                            "round": round_no, "review_round": round_no, "fix_round": round_no,
                            "commit": commit, "previous_commit": prev,
                            "fix_requests": fix_requests or [],
                            "agent_cmd": spec["cmd"], "agent_style": spec["style"], "agent_name": spec["name"]})
            LOGGER.info("task %s: %s agent=%s (style=%s) round=%d", sid, role, spec["name"], spec["style"], round_no)
            st["current_agent"] = spec["name"]
            return worker.agent("start", payload)
        return None

    def _agent_probe_ok(self, task: Task, role: str, spec: Dict[str, Any]) -> bool:
        """预检一个候选 agent：preset 声明 probe.enabled=false 则直接采信
        （测试桩）；--codex-command 全局覆盖同理不加探针。否则在工人上跑
        迷你提示词，rc=0 且输出含 expect 才算健康。"""
        probe = spec.get("probe") or {}
        if probe.get("enabled") is False:
            return True
        if self.cfg.get("codex_command"):
            return True
        payload = {"task_dir": self.task_dir(task), "agent_cmd": spec["cmd"],
                   "agent_style": spec["style"],
                   "expect": str(probe.get("expect") or "OK"),
                   "probe_timeout_seconds": int(probe.get("timeout_seconds") or 60)}
        try:
            out = self.host(task.worker).agent("probe", payload, timeout=90)
        except RuntimeError as exc:
            LOGGER.warning("task %s: probe call failed: %s", task.task_id, exc)
            return False
        return bool(out.get("healthy"))

    def _infra_reopen(self, task: Task, role: str, reason: str) -> None:
        """基础设施死亡 → 换下一位 agent 重开同一轮（A/B2 共用）。

        failover 计数有上限（failover_cap），打满落失败终态：绝不静默
        无限换人。review 用 reopen_review_round 保持原轮号，不虚增轮次。
        """
        sid = task.task_id
        st = self.state.setdefault(sid, {})
        used = int(st.get("failovers") or 0)
        cap = int(self.cfg.get("failover_cap") or 3)
        if used >= cap:
            final = {"coder": "failed", "review": "failed_review", "fix": "failed_fix"}[role]
            st["phase"] = final
            st["error"] = f"{role} infra failure repeated {used} times (>= cap {cap}); last: {reason}"
            LOGGER.warning("task %s: %s", sid, st["error"])
            return
        specs = resolve_agents(self.cfg, task, role)
        st["failovers"] = used + 1
        st[f"{role}_agent_idx"] = (int(st.get(f"{role}_agent_idx") or 0) + 1) % len(specs)
        pending = {"coder": "coder_pending", "review": "review_pending", "fix": "fix_pending"}[role]
        st["phase"] = pending
        if role == "review":
            st["reopen_review_round"] = int(st.get("rounds") or 0)
        if role == "fix":
            st["reopen_fix"] = True  # 让 fix_pending 不清零本轮 failover 预算
        if role == "coder":
            # coder 的启动前提是空工作区（自己从 GitHub clone）：infra 死了
            # 的半成品不清掉，coder_pending 会永远卡 "workdir not empty"。
            # 清理由 worker 侧执行（远程 worker 上 controller 本机摸不到目录）。
            try:
                self.host(task.worker).agent(
                    "clean-dir", {"dir": self.coder_dir(task), "work_root": self.work_root()})
            except RuntimeError as exc:
                LOGGER.warning("task %s: clean-dir 失败（继续，下 tick 会再试）: %s", sid, exc)
        st["phase_ts"] = time.time()
        try:
            self.host(task.worker).agent("reset-phase", {"task_dir": self.task_dir(task), "phase": pending})
        except RuntimeError as exc:
            LOGGER.warning("task %s: reset-phase 失败（继续，下 tick 会再试）: %s", sid, exc)
        LOGGER.warning("task %s: %s INFRA 死亡（%s）-> failover #%d/%d，换下一位 agent -> %s",
                       sid, role, reason, used + 1, cap, pending)

    def _probe_stall(self, task: Task, role: str) -> None:
        """所有候选 agent 探针都不健康：本 tick 不派工，park 计数。
        连续 probe_fail_budget 次后落失败终态（fail-loud，不停摆到永远）。"""
        sid = task.task_id
        st = self.state.setdefault(sid, {})
        n = int(st.get("probe_fails") or 0) + 1
        st["probe_fails"] = n
        budget = int(self.cfg.get("probe_fail_budget") or 60)
        if n >= budget:
            final = {"coder": "failed", "review": "failed_review", "fix": "failed_fix"}[role]
            st["phase"] = final
            st["error"] = f"no healthy agent for role {role} after {n} probe rounds"
            LOGGER.warning("task %s: %s", sid, st["error"])
        else:
            LOGGER.warning("task %s: no healthy %s agent (%d/%d probes)；park，下 tick 再探",
                           sid, role, n, budget)

    def _zombie_triggered(self, task: Task, worker, role: str, remote: Dict[str, Any]) -> bool:
        """B2：工人假死探测。进程活着但整个工作区/日志最新写龄超过
        zombie_after_secs（默认 20 分钟）判僵尸 → 杀掉 → 走 infra failover。
        启动宽限 30 秒，避免会话刚 spawn 就误判。"""
        st = self.state.setdefault(task.task_id, {})
        liveness = remote.get("liveness") or {}
        age = liveness.get("newest_age_secs")
        if not liveness.get("proc_alive") or age is None:
            return False
        zombie_after = int(self.cfg.get("zombie_after_secs") or 1200)
        if age <= zombie_after:
            return False
        if time.time() - float(st.get("phase_ts") or 0) < 30:
            return False
        LOGGER.warning("task %s: %s zombie（进程活但 %d 秒无磁盘写入 > %d）→ kill + failover",
                       task.task_id, role, age, zombie_after)
        try:
            worker.agent("stop", {"task_dir": self.task_dir(task)})
        except RuntimeError as exc:
            LOGGER.warning("task %s: stop 失败: %s", task.task_id, exc)
        self._infra_reopen(task, role, reason=f"zombie: no disk writes for {int(age)}s")
        return True

    def remote_status(self, task: Task) -> Dict[str, Any]:
        return self.host(task.worker).agent("status", {"task_dir": self.task_dir(task)})

    def remote_prepare(self, task: Task) -> Dict[str, Any]:
        # GitHub 先行：建私有仓 + 发工作单 issue（正文 = 完整任务文本）。
        # 种子仓 mirror clone + push 在慢网络/大历史下可能几分钟，
        # 超时给到 30 分钟；同一 task 重启 prepare 有幂等保护（空仓接管）。
        payload = self.base_payload(task)
        payload.update({"task_text": task.task_file.read_text(encoding="utf-8"),
                        "issue_title": f"[v4pro] {task.project} task-{task.task_id}"})
        return self.host(task.worker).agent("prepare", payload, timeout=1800)

    def remote_issue_body(self, task: Task) -> str:
        # 忠于信息方向：coder 的任务文本从 GitHub 读回（而非本机文件）。
        out = self.host(task.worker).agent("issue-body", {"task_dir": self.task_dir(task)})
        body = str(out.get("body") or "")
        if not body:
            raise RuntimeError("issue body not on GitHub; prepare must create the work order first")
        return body

    def remote_publish(self, task: Task, commit: str, prev: str, round_no: int) -> Dict[str, Any]:
        payload = self.base_payload(task)
        payload.update({"commit": commit, "previous_commit": prev, "round": round_no,
                        "issue_title": f"[v4pro] {task.project} task-{task.task_id}"})
        return self.host(task.worker).agent("publish", payload)

    def remote_finalize_review(self, task: Task, commit: str, round_no: int) -> Dict[str, Any]:
        payload = self.base_payload(task)
        payload.update({"commit": commit, "round": round_no})
        return self.host(task.worker).agent("finalize-review", payload)

    def remote_accept(self, task: Task, commit: str, round_no: int) -> Dict[str, Any]:
        payload = self.base_payload(task)
        payload.update({"commit": commit, "round": round_no})
        return self.host(task.worker).agent("accept", payload)

    def read_review_result(self, task: Task) -> Dict[str, Any]:
        out = self.host(task.worker).agent("read-result", {"path": f"{self.artifacts_dir(task)}/review_result.json"})
        return out.get("result") or {}

    # ---------------- phase machine ----------------

    def _session_dead_recover(self, task: Task, worker, role: str) -> None:
        """外部环境会周期性杀死整个进程树（tmux server + codex 会话都在内）。
        控制器本身也因此重启过。检测到 *_running 阶段下属会话已死且超过
        宽限时间后：把阶段回退到同轮 pending，下一 tick 自动重开同一阶段。
        连续死超过 max_interrupts 次则落失败终态（fail-loud，不静默循环）。"""
        sid = task.task_id
        st = self.state.setdefault(sid, {})
        phase = st.get("phase")
        ok = worker.agent("alive", {"task_dir": self.task_dir(task)})
        alive = bool((ok or {}).get("alive"))
        if alive:
            return
        age = time.time() - float(st.get("phase_ts") or 0)
        if age < 120:
            return  # 启动宽限期：会话注册可能有数秒滞后，避免误判
        interrupts = int(st.get("interrupts") or 0)
        cap = int(self.cfg.get("max_interrupts") or 4)
        if interrupts >= cap:
            final = {"coder": "failed", "review": "failed_review", "fix": "failed_fix"}[role]
            st["phase"] = final
            st["error"] = (f"{role} session died {interrupts + 1} times "
                           f"(last: no liveness after {int(age)}s); giving up")
            LOGGER.warning("task %s: %s", sid, st["error"])
            return
        st["interrupts"] = interrupts + 1
        pending = {"coder": "coder_pending", "review": "review_pending", "fix": "fix_pending"}[role]
        if role == "review":
            # 同一 commit 同一轮重开：走 reopen 标志，review_pending 不虚增轮次
            st["reopen_review_round"] = int(st.get("rounds") or 0)
        if role == "coder":
            # coder 的启动前提是空工作区（自己从 GitHub clone）；
            # 死掉的会话留下半成品，必须清干净才能重开。清理由 worker 侧
            # 执行（远程 worker 上 controller 本机的 rmtree 摸不到目录）。
            try:
                worker.agent("clean-dir", {"dir": self.coder_dir(task), "work_root": self.work_root()})
            except RuntimeError as exc:
                LOGGER.warning("task %s: clean-dir 失败（继续，下 tick 会再试）: %s", sid, exc)
        worker.agent("reset-phase", {"task_dir": self.task_dir(task), "phase": pending})
        st["phase"] = pending
        LOGGER.warning("task %s: %s session dead (interrupt #%d/%d, age=%ds) -> %s; restart next tick",
                       sid, role, interrupts + 1, cap, int(age), pending)

    def step(self, task: Task) -> None:
        sid = task.task_id
        st = self.state.setdefault(sid, {"phase": "new"})
        phase = st.get("phase", "new")
        if phase in TERMINAL_PHASES:
            return
        worker = self.host(task.worker)
        try:
            if phase == "new":
                # GitHub 先行：建仓 + 发工作单 issue，之后才会启动 coder。
                res = self.remote_prepare(task)
                st["issue"] = res.get("issue")
                st["repo"] = res.get("repo")
                st["phase"] = "coder_pending"
                LOGGER.info("task %s (%s): prepared repo=%s issue=%s", sid, task.project,
                            st.get("repo"), (st.get("issue") or {}).get("number"))
            elif phase == "coder_pending":
                body = self.remote_issue_body(task)
                issue_no = int((st.get("issue") or {}).get("number") or 0)
                if self.remote_start(task, "coder", self.coder_prompt(task, issue_no, body), round_no=0) is None:
                    self._probe_stall(task, "coder")
                    return
                st["phase"] = "coder_running"
                st["phase_ts"] = time.time()
                st["coder_status"] = "running"
                LOGGER.info("task %s: coder started (task text = GitHub issue #%s body)", sid, issue_no)
            elif phase == "coder_running":
                remote = worker.agent("status", {"task_dir": self.task_dir(task)})
                rphase = str(remote.get("phase") or "")
                if rphase != "coder_done":
                    if self._zombie_triggered(task, worker, "coder", remote):
                        return
                    self._session_dead_recover(task, worker, "coder")
                    return
                rc = int(remote["coder_returncode"]) if remote.get("coder_returncode") is not None else -1
                if rc == 0:
                    st["coder_status"] = "success"
                    st["phase"] = "publish_pending"
                    LOGGER.info("task %s: coder done rc=0 -> publish", sid)
                elif rc == 124:
                    st["phase"] = "failed_timeout"
                    st["error"] = f"coder rc=124 超时"
                    LOGGER.warning("task %s: coder timeout", sid)
                else:
                    outcome = worker.agent("outcome", {"task_dir": self.task_dir(task), "role": "coder"})
                    if infralike(outcome):
                        self._infra_reopen(task, "coder", reason=f"rc={rc}, dur={outcome.get('duration_seconds')}s")
                        return
                    st["phase"] = "failed"
                    st["error"] = f"coder rc={rc}"
                    LOGGER.warning("task %s: coder failed rc=%s", sid, rc)
            elif phase == "publish_pending":
                head = worker.agent("git-head", {"coder_dir": self.coder_dir(task)})
                commit = head.get("commit")
                if not commit:
                    raise RuntimeError("coder repo has no HEAD")
                prev = str(st.get("last_ready_commit") or "")
                res = self.remote_publish(task, commit, prev, round_no=int(st.get("rounds") or 0))
                st["issue"] = res.get("issue")
                st["repo"] = res.get("repo")
                st["last_ready_commit"] = commit
                st["phase"] = "review_pending"
                LOGGER.info("task %s: published ready commit=%s issue=%s", sid, commit[:12], (res.get("issue") or {}).get("number"))
            elif phase == "review_pending":
                reopen_round = st.pop("reopen_review_round", None)
                if reopen_round is None:
                    round_no = int(st.get("rounds") or 0) + 1
                    st["rounds"] = round_no
                    st["failovers"] = 0
                    # 评审证据文件按轮次归档：先把上一轮的 review_* 挪到 round-N/
                    # 子目录，防止把旧一轮的 verdict 错读成新一整轮的。
                    worker.agent("prep-review", {"task_dir": self.task_dir(task), "round": round_no})
                else:
                    round_no = int(reopen_round)  # infra failover：同轮重开
                commit = str(st.get("last_ready_commit") or "")
                prev = str(st.get("last_review_commit") or "")
                if self.remote_start(task, "review", self.review_prompt(task, commit, prev, round_no),
                                     round_no=round_no, commit=commit, prev=prev) is None:
                    self._probe_stall(task, "review")
                    return
                st["phase"] = "review_running"
                st["phase_ts"] = time.time()
                st["current_review"] = {"commit": commit, "round": round_no}
                LOGGER.info("task %s: review r%d started for %s", sid, round_no, commit[:12])
            elif phase == "review_running":
                remote = worker.agent("status", {"task_dir": self.task_dir(task)})
                if str(remote.get("phase") or "") != "review_done":
                    if self._zombie_triggered(task, worker, "review", remote):
                        return
                    self._session_dead_recover(task, worker, "review")
                    return
                rc = int(remote["review_returncode"]) if remote.get("review_returncode") is not None else -1
                cur = st.get("current_review") or {}
                commit, round_no = cur.get("commit"), int(cur.get("round") or 0)
                if rc != 0:
                    if rc != 124:
                        outcome = worker.agent("outcome", {"task_dir": self.task_dir(task), "role": "review"})
                        if infralike(outcome):
                            self._infra_reopen(task, "review",
                                               reason=f"rc={rc}, dur={outcome.get('duration_seconds')}s, "
                                                      f"log={outcome.get('log_bytes')}B")
                            return
                    st["phase"] = "failed_review"
                    st["error"] = f"reviewer exited rc={rc}, commit {commit}"
                    LOGGER.warning("task %s: reviewer rc=%s", sid, rc)
                    return
                result = self.read_review_result(task)
                status = str(result.get("status") or "BLOCKED").upper()
                # 防御：verdict 必须写明它审的是哪个 commit / 第几轮；对不上就是
                # 陈旧或串轮的文件，绝不能当作本轮结果继续推进。
                if (str(result.get("commit") or "") != commit
                        or int(result.get("round") or -1) != round_no):
                    st["phase"] = "failed_review"
                    st["error"] = (f"verdict commit/round mismatch: expected {commit[:12]} r{round_no},"
                                   f" got {str(result.get('commit'))[:12] if result.get('commit') else '-'} r{result.get('round')}")
                    LOGGER.warning("task %s: %s", sid, st["error"])
                    return
                st["last_review_commit"] = commit if status != "PASS" else st.get("last_review_commit")
                LOGGER.info("task %s: review r%d=%s", sid, round_no, status)
                self.remote_finalize_review(task, commit, round_no)
                if status == "PASS":
                    st["phase"] = "accept_pending"
                elif status == "FAIL":
                    fixes = int(st.get("fix_count") or 0)
                    if fixes < task.max_fix_rounds:
                        st["fix_requests"] = result.get("fix_requests") or []
                        st["failovers"] = 0
                        st["phase"] = "fix_pending"
                    else:
                        st["phase"] = "failed_review"
                        st["error"] = f"review FAIL after {fixes} fix rounds"
                else:
                    st["phase"] = "blocked"
                    st["error"] = f"reviewer verdict {status}: {result.get('summary')}"
            elif phase == "fix_pending":
                round_no = int(st.get("rounds") or 0)
                reqs = st.get("fix_requests") or []
                if not st.pop("reopen_fix", False):
                    st["failovers"] = 0  # 新一轮修复：重置本轮 failover 预算
                if self.remote_start(task, "fix", self.fix_prompt(task, reqs, round_no),
                                     round_no=round_no, fix_requests=reqs) is None:
                    self._probe_stall(task, "fix")
                    return
                st["phase"] = "fix_running"
                st["phase_ts"] = time.time()
                LOGGER.info("task %s: fixer started (round %s, %d requests)", sid, round_no, len(reqs))
            elif phase == "fix_running":
                remote = worker.agent("status", {"task_dir": self.task_dir(task)})
                if str(remote.get("phase") or "") != "fix_done":
                    if self._zombie_triggered(task, worker, "fix", remote):
                        return
                    self._session_dead_recover(task, worker, "fix")
                    return
                rc = int(remote["fix_returncode"]) if remote.get("fix_returncode") is not None else -1
                if rc != 0:
                    if rc != 124:
                        outcome = worker.agent("outcome", {"task_dir": self.task_dir(task), "role": "fix"})
                        if infralike(outcome):
                            self._infra_reopen(task, "fix",
                                               reason=f"rc={rc}, dur={outcome.get('duration_seconds')}s, "
                                                      f"log={outcome.get('log_bytes')}B")
                            return
                    st["phase"] = "failed_fix"
                    st["error"] = f"fixer rc={rc}"
                    LOGGER.warning("task %s: fixer rc=%s -> failed_fix", sid, rc)
                    return
                head = worker.agent("git-head", {"coder_dir": self.coder_dir(task)})
                new_commit = head.get("commit")
                if not new_commit or new_commit == st.get("last_ready_commit"):
                    st["phase"] = "failed_fix"
                    st["error"] = "fixer made no new commit"
                    return
                st["fix_count"] = int(st.get("fix_count") or 0) + 1
                st["last_ready_commit"] = new_commit
                st["phase"] = "publish_pending"
                LOGGER.info("task %s: fixer committed %s (fix #%s)", sid, new_commit[:12], st["fix_count"])
            elif phase == "accept_pending":
                cur = st.get("current_review") or {}
                commit = str(cur.get("commit") or st.get("last_ready_commit") or "")
                res = self.remote_accept(task, commit, int(cur.get("round") or 0))
                st["phase"] = "accepted"
                st["accepted_commit"] = res.get("accepted_commit")
                st["accept_fails"] = 0
                LOGGER.info("task %s: ACCEPTED commit=%s", sid, (res.get("accepted_commit") or "")[:12])
        except Exception as exc:
            LOGGER.warning("task %s (%s) phase %s error: %s", sid, task.project, phase, exc)
            if not st.get("last_error"):
                st["last_error"] = str(exc)
            if phase == "publish_pending":
                st["phase"] = "failed_publish"
                st["error"] = str(exc)
            elif phase == "accept_pending":
                # accept 失败不能无限 tick 重试：计数到 max_accept_retries（默认 6）
                # 就落 failed_publish（fail-loud），不静默卡死。
                fails = int(st.get("accept_fails") or 0) + 1
                st["accept_fails"] = fails
                cap = int(self.cfg.get("max_accept_retries") or 6)
                if fails >= cap:
                    st["phase"] = "failed_publish"
                    st["error"] = f"accept failed {fails} times (>= cap {cap}); last: {exc}"
                    LOGGER.warning("task %s: %s", sid, st["error"])
        finally:
            # 任何分支（含中间 return 的失败分支）都必须落盘：
            # 若失败终态只留在内存，退出后磁盘仍是运行中，--show-status
            # 和重启恢复都会看到落后/错误的状态。
            self.save_state()


def reviewer_root_round(r: Runner, task: Task, round_no: int) -> str:
    return f"{r.reviewer_root(task).rstrip('/')}/round-{round_no}"


def load_config(path: Path, overrides: argparse.Namespace) -> Dict[str, Any]:
    cfg = read_json(path, {})
    cfg.setdefault("workers", ["adm1", "adm2", "adm3", "adm4"])
    cfg.setdefault("work_root", "~/ad_xjtan_v4pro")
    cfg.setdefault("remote_agent_dir", "~/codex_v4pro")
    cfg.setdefault("remote_python", "python3")
    cfg.setdefault("tasks_csv", str(DEFAULT_TASKS_CSV))
    cfg.setdefault("repo", {})
    cfg["repo"].setdefault("owner", "")  # 留空促使使用者显式填写，避免误用默认账号
    cfg["repo"].setdefault("suffix", "_dsv4pro_v1")
    cfg["repo"].setdefault("visibility", "private")
    cfg["repo"].setdefault("create_repo", True)
    # 不再有静默默认的 codex 命令：未显式指定 agent 时启动即失败（见 resolve_agent）
    cfg.setdefault("max_fix_rounds", 3)
    cfg.setdefault("timeout_minutes", 45)
    cfg.setdefault("policy_file", "")
    cfg.setdefault("poll_interval_seconds", 30)
    cfg.setdefault("max_interrupts", 4)
    # A/B2：agent failover 与假死探测旋钮
    cfg.setdefault("failover_cap", 3)          # 每轮最多换几个 agent，打满落失败终态
    cfg.setdefault("probe_fail_budget", 60)    # 探针连续不健康的 park 次数上限
    cfg.setdefault("zombie_after_secs", 1200)  # 进程活但这么久没写盘 → 判僵尸
    if overrides.workers:
        cfg["workers"] = overrides.workers
    if overrides.work_root:
        cfg["work_root"] = overrides.work_root
    if overrides.repo_suffix is not None:
        cfg["repo"]["suffix"] = overrides.repo_suffix
    if overrides.repo_owner:
        cfg["repo"]["owner"] = overrides.repo_owner
    if overrides.tasks_csv:
        cfg["tasks_csv"] = overrides.tasks_csv
    if overrides.timeout_minutes:
        cfg["timeout_minutes"] = overrides.timeout_minutes
    if overrides.max_fix_rounds is not None:
        cfg["max_fix_rounds"] = overrides.max_fix_rounds
    if overrides.codex_command:
        cfg["codex_command"] = overrides.codex_command
    if overrides.failover_cap is not None:
        cfg["failover_cap"] = overrides.failover_cap
    if overrides.probe_fail_budget is not None:
        cfg["probe_fail_budget"] = overrides.probe_fail_budget
    if overrides.zombie_after is not None:
        cfg["zombie_after_secs"] = overrides.zombie_after
    cfg["tasks_csv"] = str(Path(cfg["tasks_csv"]))
    if not Path(cfg["tasks_csv"]).is_absolute():
        cfg["tasks_csv"] = str(ROOT / cfg["tasks_csv"])
    return cfg


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--workers", nargs="*", help="hosts (adm1..adm4 or local)")
    p.add_argument("--work-root", help="big working directory on the worker hosts")
    p.add_argument("--repo-suffix", help="GitHub repo suffix, e.g. _dsv4pro_v1")
    p.add_argument("--repo-owner")
    p.add_argument("--tasks-csv")
    p.add_argument("--timeout-minutes", type=int)
    p.add_argument("--max-fix-rounds", type=int)
    p.add_argument("--codex-command", help="override the codex command (fake binaries allowed for testing)")
    p.add_argument("--zombie-after", type=int, metavar="SECONDS",
                   help="B2: worker alive but no disk writes for this long -> zombie -> failover")
    p.add_argument("--failover-cap", type=int, metavar="N",
                   help="A: max agent failovers per round before a terminal failed_*")
    p.add_argument("--probe-fail-budget", type=int, metavar="N",
                   help="A: max consecutive ticks with no healthy agent before terminal failed_*")
    p.add_argument("--dry-run", action="store_true", help="print the plan, touch nothing")
    p.add_argument("--check", action="store_true", help="sync agents + check host env, start no codex")
    p.add_argument("--once", action="store_true", help="one scheduling pass")
    p.add_argument("--loop", type=int, metavar="SECONDS", help="poll until terminal or timeout")
    p.add_argument("--show-status", action="store_true")
    p.add_argument("--retry-task", action="append", default=[], help="requeue a task (repeatable)")
    return p.parse_args(argv)


def show_status(runner: Runner) -> None:
    print(f"{'id':>3} {'project':<18} {'worker':<7} {'phase':<16} {'rounds':<6} {'commit'}")
    for t in runner.tasks:
        st = runner.state.get(t.task_id, {})
        commit = (st.get("accepted_commit") or st.get("last_ready_commit") or "")[:10]
        print(f"{t.task_id:>3} {t.project:<18} {t.worker:<7} {st.get('phase','new'):<16} {str(st.get('rounds',0)):<6} {commit}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config, args) if args.config.is_file() else load_config(Path("missing"), args)

    runner = Runner(cfg)
    runner.load_tasks()
    runner.load_state()

    # 单实例锁：避免两个 controller 同时改同一份 controller_state.json
    # （两个进程交错写入会互相覆盖状态）。只读的 --show-status 不加锁，
    # 这样可以在 loop 跑着的时候看进度；状态文件写入是原子的，不会读到半截。
    lock_fd = None
    if not args.show_status:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(STATE_PATH.parent / "controller.lock", "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("错误：已有一个 controller 在跑（state/controller.lock 被占用），"
                  "同时跑两个会互相覆盖状态。先停掉另一个再重试。", file=sys.stderr)
            return 2

    # 每个角色都必须显式指派 agent（无默认）。任何缺失/未知 preset 立即中止，
    # 绝不静默缩回某个实现。dry-run/check/loop 三种模式都先过这一关。
    for t in runner.tasks:
        for role in AGENT_ROLES:
            resolve_agent(cfg, t, role)

    for tid in args.retry_task:
        if tid not in runner.state:
            LOGGER.error("--retry-task %s: unknown task id", tid)
            return 2
        old = runner.state[tid]
        runner.state[tid] = {"phase": "new", "retry_history": runner.state[tid].get("retry_history", []) + [
            {"at": utcnow(), "from_phase": old.get("phase"), "error": old.get("error") or old.get("last_error")}]}
        LOGGER.info("task %s requeued from phase %s", tid, old.get("phase"))
    runner.save_state()

    if args.show_status:
        show_status(runner)
        return 0

    hosts_needed = {t.worker for t in runner.tasks}
    for name in sorted(hosts_needed):
        host = runner.host(name)
        if args.dry_run:
            print(f"[dry-run] host {name}: agent at {host.agent_path()}")
            continue
        host.sync_agent()

    if args.dry_run:
        for t in runner.tasks:
            print(f"[dry-run] task {t.task_id} {t.project}: worker={t.worker} "
                  f"coder={runner.coder_dir(t)} reviewer={runner.reviewer_root(t)} "
                  f"repo={cfg['repo']['owner']}/{runner.repo_name(t)} phase={runner.state.get(t.task_id, {}).get('phase', 'new')}")
        return 0

    if args.check:
        ok = True
        for name in sorted(hosts_needed):
            try:
                res = runner.host(name).agent("check")
            except Exception as exc:
                print(f"{name:<8} ERROR {exc}")
                ok = False
                continue
            gh = res.get("gh", {})
            print(f"{name:<8} python={'ok' if res.get('python3',{}).get('path') else 'MISSING'} "
                  f"codex={'ok' if res.get('codex',{}).get('path') else 'MISSING'} "
                  f"gh={gh.get('login') or 'MISSING'} tmux={'yes' if res.get('tmux',{}).get('path') else 'no'} "
                  f"timeout={'yes' if res.get('timeout',{}).get('path') else 'no'}")
            ok = ok and bool(res.get("ok"))
        for t in runner.tasks:
            parts = []
            for role in AGENT_ROLES:
                agents = resolve_agents(cfg, t, role)
                parts.append(f"{role}=[{'|'.join(a['name'] for a in agents)}]")
            print(f"agents  task {t.task_id} {t.project}: " + " ".join(parts))
        print("PASS" if ok else "CHECK FAILED")
        return 0 if ok else 1

    if args.once:
        for t in runner.tasks:
            runner.step(t)
        return 0

    if args.loop:
        deadline = time.monotonic() + args.loop
        while time.monotonic() < deadline:
            terminal = all(runner.state.get(t.task_id, {}).get("phase") in TERMINAL_PHASES for t in runner.tasks)
            if terminal:
                break
            for t in runner.tasks:
                runner.step(t)
            if all(runner.state.get(t.task_id, {}).get("phase") in TERMINAL_PHASES for t in runner.tasks):
                break
            time.sleep(min(cfg.get("poll_interval_seconds", 30), max(1, int(deadline - time.monotonic()))))
        show_status(runner)
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
