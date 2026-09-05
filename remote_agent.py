#!/usr/bin/env python3
"""v4pro remote agent: the only execution-side component.

Runs on every worker host (adm1-adm4, or the local Mac for fast loop tests).
The Mac controller talks to it over short-lived SSH commands (or direct
subprocess calls when the host is ``local``).  All GitHub operations happen
here, on a machine that already has ``gh`` credentials; tokens never enter
controller state, prompts or logs.

Handles three roles, all detached from the SSH connection:

- ``coder``   writes the project in <work_root>/<project><suffix>/
- ``review``  verifies a fixed commit in
              <work_root>/<project><suffix>_reviewer/round-<N>/
- ``fix``     amends the code in the coder directory after a failed review

Protocol comments on the task Issue are machine-generated here too:

    <!-- V4PRO READY  v1 --> {json} <!-- END V4PRO READY  v1 -->
    <!-- V4PRO REVIEW v1 --> {json} <!-- END V4PRO REVIEW v1 -->
    <!-- V4PRO MERGE  v1 --> {json} <!-- END V4PRO MERGE  v1 -->

Stdlib only.  Keep this file small on purpose: it is the v4pro "simplest
runnable version" execution core, not a replacement for the full worker.py
policy stack in the parent repository.
"""

from __future__ import annotations

import json
import re
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

UTCNOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

STATE_VERSION = 1
VALID_ROLES = ("coder", "review", "fix")
VALID_REVIEW_STATUS = ("PASS", "FAIL", "BLOCKED")


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------

def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sh(cmd: list, cwd: Optional[str] = None, timeout: int = 300) -> str:
    """Run a command, return stdout, raise on non-zero."""
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:2])} rc={p.returncode}: {(p.stderr or p.stdout).strip()[-500:]}")
    return p.stdout.strip()


def sh_ok(cmd: list, cwd: Optional[str] = None, timeout: int = 300) -> bool:
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    return p.returncode == 0


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def iso_to_epoch(iso: str) -> Optional[float]:
    """'2026-09-03T23:29:05Z' -> epoch seconds (None if unparsable)."""
    import calendar
    try:
        return calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return None


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def emit(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def fail(message: str, extra: Optional[Dict[str, Any]] = None) -> int:
    emit({"ok": False, "error": message, **(extra or {})})
    return 2


def load_stdin_payload() -> Dict[str, Any]:
    try:
        data = json.loads(sys.stdin.read())
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": f"invalid payload: {exc}"}))
        raise SystemExit(2)
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "error": "payload must be a JSON object"}))
        raise SystemExit(2)
    return data


# ----------------------------------------------------------------------------
# task state (one JSON file per task inside the shared work root)
# ----------------------------------------------------------------------------

def state_file(payload: Dict[str, Any]) -> Path:
    return Path(os.path.expanduser(str(payload["task_dir"]))) / "state.json"


def load_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    return read_json(state_file(payload), {"schema": STATE_VERSION, "phase": "new"}) or {}


def save_state(payload: Dict[str, Any], state: Dict[str, Any]) -> None:
    write_json(state_file(payload), state)


def patch_state(payload: Dict[str, Any], **updates: Any) -> Dict[str, Any]:
    state = load_state(payload)
    state.update(updates)
    save_state(payload, state)
    return state


# ----------------------------------------------------------------------------
# environment check
# ----------------------------------------------------------------------------

def cmd_check(payload: Optional[Dict[str, Any]] = None) -> int:
    result: Dict[str, Any] = {"ok": True}
    for name in ("python3", "git"):
        result[name] = {"path": which(name)}
        if not result[name]["path"]:
            result["ok"] = False
    result["codex"] = {"path": which("codex")}
    if result["codex"]["path"]:
        v = subprocess.run(["codex", "--version"], text=True, capture_output=True)
        result["codex"]["version"] = (v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr).strip() else "?"
    else:
        result["ok"] = False
    result["gh"] = {"path": which("gh")}
    if result["gh"]["path"]:
        p = subprocess.run(["gh", "api", "user", "--jq", ".login"], text=True, capture_output=True)
        result["gh"]["login"] = p.stdout.strip() if p.returncode == 0 else None
        result["gh"]["ok"] = p.returncode == 0 and bool(p.stdout.strip())
        if not result["gh"]["ok"]:
            result["ok"] = False
    else:
        result["ok"] = False
    result["tmux"] = {"path": which("tmux")}
    result["timeout"] = {"path": which("timeout")}
    result["work_root_writable"] = None
    emit(result)
    return 0 if result["ok"] else 1


# ----------------------------------------------------------------------------
# role startup (coder / review / fix), detached from SSH
# ----------------------------------------------------------------------------

def agent_command_line(agent_cmd: str, agent_style: str, prompt_file: Path) -> str:
    """把 agent 命令 + 提示词传递方式拼成一行 shell（不含 timeout 包装）。

    - stdin:    提示词从 stdin 管道进去（codex 风格），命令末尾必须是单独 "-"
    - atfile:   提示词以 @文件 参数传入（pi 风格），stdin 喂 /dev/null
    - argvfile: 提示词作为单个 argv 传入，stdin 喂 /dev/null

    命令首词用双引号包裹：config 里 preset cmd 会用 $HOME/... 形式，
    单引号会冻结 $HOME 导致 command not found（h200 实战坑）。
    其余参数仍用 shlex.quote 严格包裹。

    支持 env 前缀（如 "FAKE_PI_MODE=ok python3 script.py"）：前缀里
    赋值形态的 token 保留为环境赋值词（严格 quote），可执行词从第一个
    非赋值 token 开始；不这么做的话首词会变成 "FAKE_PI_MODE=ok"，
    execvp 找不到可执行文件 → rc=127（负面场景装配坑）。
    """
    parts = shlex.split(agent_cmd)
    if not parts:
        parts = ["echo"]
    envs: List[str] = []
    while parts and "=" in parts[0] and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[0]):
        envs.append(parts.pop(0))
    if not parts:
        parts = ["echo"]
    q = lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    parts_q = [shlex.quote(e) for e in envs] + [q(parts[0])] + [shlex.quote(c) for c in parts[1:]]
    if agent_style == "stdin":
        if parts[-1] != "-":
            parts_q.append("-")
        return " ".join(parts_q) + f" < {shlex.quote(str(prompt_file))}"
    if agent_style == "atfile":
        return " ".join(parts_q) + f" {shlex.quote('@' + str(prompt_file))} < /dev/null"
    if agent_style == "argvfile":
        return " ".join(parts_q) + f" \"$(cat {shlex.quote(str(prompt_file))})\" < /dev/null"
    raise RuntimeError(f"agent_command_line: 未知 agent style {agent_style!r}")


def runner_script(payload: Dict[str, Any], role: str, round_no: int, workdir: Path) -> str:
    """Shell script the detached session executes.

    codex stdout+stderr go to task logs/<role>_r<round>.log; the prompt stays
    in the task dir as <role>_r<round>_prompt.md (task text only, never
    credentials).  A final mark-done writes the exit code back to state.json.
    """
    logs_dir = Path(os.path.expanduser(str(payload["task_dir"]))) / "logs"
    prompt_file = logs_dir / f"{role}_r{round_no}_prompt.md"
    log_file = logs_dir / f"{role}_r{round_no}.log"
    rc_file = logs_dir / f"{role}_r{round_no}.rc"
    # generated earlier by the agent; several lines must match exactly
    assert prompt_file.exists(), prompt_file

    agent_cmd = str(payload.get("agent_cmd") or payload.get("codex_command") or "").strip()
    agent_style = str(payload.get("agent_style") or "stdin")
    agent_name = str(payload.get("agent_name") or "codex")
    if not agent_cmd:
        raise RuntimeError("runner_script: payload 缺 agent_cmd（agent 指派未解析）")
    line = agent_command_line(agent_cmd, agent_style, prompt_file)
    timeout_cmd = which("timeout")
    if timeout_cmd and payload.get("timeout_seconds"):
        line = f"{shlex.quote(timeout_cmd)} -s TERM -k 30 {int(payload['timeout_seconds'])} {line}"

    agent = shlex.quote(str(Path(__file__).resolve()))
    python = shlex.quote(sys.executable or "python3")
    task_dir = shlex.quote(str(Path(os.path.expanduser(str(payload["task_dir"])))))
    ts = now()
    return f"""#!/bin/sh
# v4pro generated runner: role={role} round={round_no}
cd {shlex.quote(str(workdir))} || exit 125
{line} >> {shlex.quote(str(log_file))} 2>&1
rc=$?
echo "$rc" > {shlex.quote(str(rc_file))}
if [ "$rc" -eq 0 ]; then st=success; else st=failed; fi
{python} {agent} mark-done --task-dir {task_dir} --role {role} --state "$st" --rc "$rc" --note "{agent_name} exited rc=$rc at {ts}" >> {shlex.quote(str(log_file))} 2>&1
"""


def cmd_start(payload: Dict[str, Any]) -> int:
    if "task_dir" in payload:
        payload["task_dir"] = os.path.expanduser(str(payload["task_dir"]))
    td = Path(payload["task_dir"])
    role = str(payload.get("role") or "coder")
    if role not in VALID_ROLES:
        return fail(f"unknown role {role!r}")
    round_no = int(payload.get(f"{'review' if role == 'review' else 'fix'}_round" if role != "coder" else "round") or 0)
    work_root = Path(os.path.expanduser(str(payload["work_root"])))
    work_root.mkdir(parents=True, exist_ok=True)
    logs_dir = td / "logs"
    artifacts_dir = td / "artifacts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(payload)
    if str(state.get("phase") or "").startswith(role + "_running"):
        return emit({"ok": False, "error": f"{role} already running (phase={state['phase']})"})

    # ---- role-specific preparation ----
    workdir: Path
    if role == "coder":
        # GitHub 是代码的唯一来源：coder 的工作目录必须保持 EMPTY，
        # 由 coder 自己在会话里执行 `git clone {repo_url} .` 拉取。
        workdir = Path(os.path.expanduser(str(payload["coder_dir"])))
        workdir.mkdir(parents=True, exist_ok=True)
        if any(workdir.iterdir()):
            return fail("coder workdir not empty; it must clone the repository from GitHub into a clean dir")
    elif role == "review":
        commit = str(payload.get("commit") or "").strip()
        if not commit:
            return fail("review role requires reviewed commit")
        reviewer_root = Path(os.path.expanduser(str(payload["reviewer_root"])))
        workdir = reviewer_root / f"round-{round_no}"
        if workdir.exists():
            shutil.rmtree(workdir)
        reviewer_root.mkdir(parents=True, exist_ok=True)
        repo_url = gh_repo_url(payload)
        # 被审 commit 必须在 GitHub 上（coder 的 push 是事实前提）：先核对
        # 远端 main，再从 GitHub 克隆 —— reviewer 看到的与外部审计者一致。
        ls = subprocess.run(["git", "ls-remote", repo_url, "main"],
                            text=True, capture_output=True)
        remote_sha = (ls.stdout or "").split()[0] if ls.returncode == 0 and ls.stdout.strip() else ""
        if remote_sha != commit:
            shutil.rmtree(workdir, ignore_errors=True)
            return fail(f"reviewed commit {commit[:12]} not on origin/main (remote={remote_sha[:12] or '-'})")
        sh(["git", "clone", "--quiet", repo_url, str(workdir)])
        try:
            sh(["git", "-C", str(workdir), "checkout", "--quiet", commit])
        except RuntimeError:
            shutil.rmtree(workdir, ignore_errors=True)
            return fail(f"cannot checkout reviewed commit {commit[:12]} from GitHub clone")
        state["reviewer_dir"] = str(workdir)
    else:  # fix
        workdir = Path(os.path.expanduser(str(payload["coder_dir"])))
        if not workdir.is_dir() or not (workdir / ".git").exists():
            return fail("fix role requires an existing coder repository")
        fix_path = artifacts_dir / "fix_request.json"
        write_json(fix_path, {"round": round_no, "fix_requests": payload.get("fix_requests") or [], "at": now()})

    # ---- prompt file ----
    prompt_file = logs_dir / f"{role}_r{round_no}_prompt.md"
    prompt_file.write_text(str(payload.get("prompt") or ""), encoding="utf-8")
    prompt_file.chmod(0o600)

    # ---- detach ----
    runner = logs_dir / f"{role}_r{round_no}_runner.sh"
    runner.write_text(runner_script(payload, role, round_no, workdir), encoding="utf-8")
    runner.chmod(0o700)
    session = f"v4pro-t{payload.get('task_id')}-{role}-r{round_no}-{os.getpid()}"
    backend = "tmux"
    pid = None
    if which("tmux"):
        p = subprocess.run(["tmux", "new-session", "-d", "-s", session, "sh", str(runner)],
                           text=True, capture_output=True)
        if p.returncode != 0:
            backend = "nohup"
    else:
        backend = "nohup"
    if backend == "nohup":
        p = subprocess.Popen(
            ["setsid", "sh", str(runner)] if which("setsid") else ["nohup", "sh", str(runner)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        pid = p.pid

    patch_state(payload,
                phase=f"{role}_running",
                role=role,
                backends={**state.get("backends", {}), role: backend},
                session=session,
                pid=pid,
                started_at=now(),
                workdir=str(workdir),
                **({"reviewer_dir": str(workdir)} if role == "review" else {}),
                prompt_file=str(prompt_file),
                log_file=str(logs_dir / f"{role}_r{round_no}.log"))
    emit({"ok": True, "phase": f"{role}_running", "session": session, "backend": backend} | ({"pid": pid} if pid else {}))
    return 0


def cmd_mark_running(payload: Dict[str, Any]) -> int:
    patch_state(payload, phase=f"{payload.get('role')}_running", pid=os.getpid(),
                last_alive_at=now(), error=None)
    emit({"ok": True})
    return 0


def cmd_mark_done(payload: Dict[str, Any]) -> int:
    role = payload.get("role")
    rc = int(payload.get("rc") or -1)
    state_val = str(payload.get("state") or ("success" if rc == 0 else "failed"))
    state = load_state(payload)
    state["phase"] = f"{role}_done"
    state[f"{role}_returncode"] = rc
    state[f"{role}_status"] = state_val
    state["finished_at"] = now()
    if payload.get("note"):
        state[f"{role}_note"] = payload["note"]
    save_state(payload, state)
    emit({"ok": True, "phase": state["phase"]})
    return 0


def cmd_status(payload: Dict[str, Any]) -> int:
    state = load_state(payload)
    if str(state.get("phase") or "").endswith("_running"):
        state["liveness"] = liveness_snapshot(state)
    emit(state)
    return 0


def session_alive(state: Dict[str, Any]) -> bool:
    """当前角色的脱产会话是否还活着（tmux 会话或 nohup pid）。"""
    backend = str(state.get("backends", {}).get(str(state.get("role") or "coder")) or "tmux")
    session = str(state.get("session") or "")
    alive = False
    if backend == "tmux" and session and which("tmux"):
        p = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True)
        alive = p.returncode == 0
    pid = state.get("pid")
    if not alive and isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError, OSError):
            alive = False
    return alive


def liveness_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """假死探测数据：进程活着 + 磁盘写龄（工作区/日志最新 mtime 距今秒数）。

    只凭 stdout 日志大小不可靠（pi 的 print 输出是块缓冲，可能在几十
    分钟里 0 字节但实际在写文件），所以以工作区文件 mtime 为主。
    """
    alive = session_alive(state)
    newest: Optional[float] = None

    def touch(path: Optional[str]) -> None:
        nonlocal newest
        if not path:
            return
        p = Path(path)
        try:
            m = p.stat().st_mtime
            if newest is None or m > newest:
                newest = m
        except OSError:
            pass

    touch(state.get("log_file"))
    # 工作区 + 任务目录都扫：reviewer 的裁决文件写在 task_dir/artifacts 而非
    # 克隆目录，只扫 workdir 会把“读长代码但最后才写裁决”的正常 reviewer 误判僵尸。
    for root in (state.get("workdir"), state.get("task_dir")):
        if not root or not Path(str(root)).is_dir():
            continue
        budget = 4000  # 文件数上限：大仓库只扫前 4000 个，都不算最新也无碍
        for dirpath, dirnames, filenames in os.walk(str(root)):
            if ".git" in dirnames:
                dirnames.remove(".git")
            for name in filenames:
                touch(os.path.join(dirpath, name))
                budget -= 1
            if budget <= 0:
                break
    newest_age: Optional[int] = None
    if newest is not None:
        newest_age = max(0, int(time.time() - newest))
    return {"proc_alive": alive, "newest_age_secs": newest_age, "at": now()}


def cmd_alive(payload: Dict[str, Any]) -> int:
    """Is the current role's detached session still alive? Controller polls
    this to detect sessions killed by external process reaping; a dead session
    with phase still *_running lets the controller restart the same phase."""
    state = load_state(payload)
    phase = str(state.get("phase") or "")
    if not phase.endswith("_running"):
        return emit({"ok": True, "alive": False, "phase": phase, "reason": "not-running"})
    return emit({"ok": True, "alive": session_alive(state), "phase": phase,
                 "backend": state.get("backends", {}).get(str(state.get("role") or "coder")),
                 "session": state.get("session")})


def cmd_reset_phase(payload: Dict[str, Any]) -> int:
    """Clear the *_running marker of a dead session so the next cmd_start can
    relaunch the role. Only ever called after cmd_alive reported dead."""
    patch_state(payload, phase=str(payload.get("phase") or "stopped"),
                pid=None, session=None, error=None)
    emit({"ok": True, "phase": payload.get("phase")})
    return 0


def cmd_stop(payload: Dict[str, Any]) -> int:
    state = load_state(payload)
    backend = str(state.get("backends", {}).get(str(state.get("role") or "coder")) or "tmux")
    if backend == "tmux":
        session = str(state.get("session") or "")
        if session:
            subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)
    else:
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0:
            subprocess.run(["pkill", "-TERM", "-g", str(pid)], capture_output=True)
    patch_state(payload, phase="stopped", stopped_at=now())
    emit({"ok": True, "phase": "stopped"})
    return 0


def cmd_probe(payload: Dict[str, Any]) -> int:
    """派工前的连通性探针：用 1-token 级别的迷你提示词验 agent 通路。

    真 agent（codex/pi/pi-kimi）派活前先跑这个：rc=0 且输出含 expect 才
    算健康；不健康的候选会被 controller 跳过/换下一个（failover 机制）。
    测试桩在 preset 里声明 probe.enabled=false，永远不会浪费一次真 API。
    """
    agent_cmd = str(payload.get("agent_cmd") or "").strip()
    agent_style = str(payload.get("agent_style") or "stdin")
    expect = str(payload.get("expect") or "OK")
    if not agent_cmd:
        return fail("probe requires agent_cmd")
    logs_dir = Path(os.path.expanduser(str(payload.get("task_dir") or "."))) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    probe_file = logs_dir / f"probe_{os.getpid()}_{int(time.time())}.md"
    probe_file.write_text("Reply with exactly the word: OK", encoding="utf-8")
    line = agent_command_line(agent_cmd, agent_style, probe_file)
    timeout_s = int(payload.get("probe_timeout_seconds") or 60)
    t0 = time.time()
    try:
        p = subprocess.run(["sh", "-c", line], text=True, capture_output=True,
                           timeout=timeout_s, cwd=str(logs_dir))
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        rc, found = p.returncode, expect.lower() in out.lower()
    except subprocess.TimeoutExpired:
        rc, out, found = 124, "", False
    healthy = rc == 0 and found
    emit({"ok": True, "healthy": healthy, "rc": rc, "expect": expect,
          "duration_seconds": round(time.time() - t0, 1),
          "output_tail": (out or "")[-300:]})
    return 0


def cmd_outcome(payload: Dict[str, Any]) -> int:
    """工人侧“死因取证”：rc/时长/日志字节数/日志尾，供 controller 分类
    infra（基础设施死亡，可换 agent 重开）vs real（真干砸，保持 fail-loud）。"""
    state = load_state(payload)
    role = str(payload.get("role") or "coder")
    rc = state.get(f"{role}_returncode")
    started = iso_to_epoch(str(state.get("started_at") or ""))
    finished = iso_to_epoch(str(state.get("finished_at") or ""))
    duration = None
    if started is not None and finished is not None:
        duration = max(0, int(finished - started))
    log_file = Path(str(state.get("log_file") or ""))
    if not log_file.is_file():
        # 状态文件是旧版本写的：回退到 logs/{role}_r*.log 里与 rc 文件对应最近的一个
        logs_dir = Path(os.path.expanduser(str(payload.get("task_dir") or "."))) / "logs"
        candidates = sorted(logs_dir.glob(f"{role}_r*.rc"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            log_file = candidates[0].with_suffix(".log")
    log_bytes, tail = 0, ""
    if log_file.is_file():
        try:
            data = log_file.read_bytes()
            log_bytes = len(data)
            tail = data[-8192:].decode(errors="replace")
        except OSError:
            pass
    emit({"ok": True, "role": role, "rc": rc,
          "duration_seconds": duration, "log_bytes": log_bytes, "log_tail": tail})
    return 0


# ----------------------------------------------------------------------------
# GitHub steps (gh credentials live on this host only)
# ----------------------------------------------------------------------------

def gh_repo_name(payload: Dict[str, Any]) -> str:
    return str(payload.get("repo_name") or f"{payload.get('project')}{payload.get('gh', {}).get('suffix', '')}")


def gh_full_name(payload: Dict[str, Any]) -> str:
    owner = str(payload.get("gh", {}).get("owner") or "").strip()
    return f"{owner}/{gh_repo_name(payload)}"


def gh_repo_url(payload: Dict[str, Any]) -> str:
    return f"https://github.com/{gh_full_name(payload)}.git"


def gh_repo_empty(full: str) -> bool:
    """Whether the GitHub repository exists and has no commits yet."""
    p = subprocess.run(["gh", "repo", "view", full, "--json", "isEmpty",
                        "--jq", ".isEmpty"], text=True, capture_output=True)
    return p.returncode == 0 and "true" in (p.stdout or "").lower()


def push_seed(dest_full: str, seed: Dict[str, Any]) -> tuple[int, str]:
    """Import the seed repository (upstream AD package) into an empty GitHub repo.

    The batch task repos must carry the authored AD-package history so the
    coder works on top of the reviewed package, not from scratch.  Only
    branches and tags are mirrored; the seed's default branch is mapped to
    ``main`` of the destination.
    """
    url = str(seed.get("url") or "").strip()
    if not url:
        return 0, ""
    ref = str(seed.get("ref") or "").strip() or "HEAD"
    tmp = tempfile.mkdtemp(prefix="v4pro-seed-")
    bare = os.path.join(tmp, "seed.git")
    try:
        p = subprocess.run(["git", "clone", "--quiet", "--mirror", "--", url, bare],
                           text=True, capture_output=True)
        if p.returncode != 0:
            return 1, f"seed clone failed: {(p.stderr or p.stdout).strip()[-400:]}"
        if ref == "HEAD":
            p2 = subprocess.run(["git", "-C", bare, "symbolic-ref",
                                 "refs/remotes/origin/HEAD"], text=True, capture_output=True)
            resolved = (p2.stdout or "").strip().rsplit("/", 1)[-1]
            ref = resolved or "main"
        dest = f"https://github.com/{dest_full}.git"
        # 种子 ref 支持两种形态：分支名（refs/heads/<ref>）与 commit SHA（裸对象引用）。
        # 用户要求按 issue 发生时的时间点种子，SHA 形态覆盖该场景。
        is_sha = bool(re.fullmatch(r"[0-9a-f]{12,40}", ref))
        if is_sha:
            pv = subprocess.run(["git", "-C", bare, "rev-parse", "--quiet", "--verify",
                                 f"{ref}^{{commit}}"], text=True, capture_output=True)
            if pv.returncode != 0:
                return 1, f"seed ref {ref} does not resolve to a commit in the seed repo"
            specs = [f"+{ref}:refs/heads/main", "+refs/tags/*:refs/tags/*"]
        else:
            specs = [f"+refs/heads/{ref}:refs/heads/main", "+refs/tags/*:refs/tags/*"]
        p3 = subprocess.run(["git", "-C", bare, "push", "--quiet", "--", dest] + specs,
                            text=True, capture_output=True)
        if p3.returncode != 0:
            return 1, f"seed push failed: {(p3.stderr or p3.stdout).strip()[-400:]}"
        return 0, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_prepare(payload: Dict[str, Any]) -> int:
    """Create the private GitHub repository and the work-order Issue.

    The Issue body carries the complete task text: GitHub becomes the single
    source of the task (controller reads it back from the Issue and hands that
    text to the coder, which clones the repo itself).  When ``seed.url`` is
    given, the seed repository's history is imported into the fresh repo first;
    this makes the same prepare retryable (an empty repo from a failed attempt
    is completed instead of rejected).
    """
    state = load_state(payload)
    full = gh_full_name(payload)
    existing = state.get("issue") or {}
    if existing.get("number"):
        if not sh_ok(["gh", "repo", "view", full]):
            return fail(f"repository {full} missing despite recorded Issue")
        emit({"ok": True, "issue": existing, "repo": full, "reused": True})
        return 0

    existed = sh_ok(["gh", "repo", "view", full])
    if existed and not gh_repo_empty(full):
        return fail(f"repository {full} already exists; a batch suffix must never be reused")
    if not existed:
        if not payload.get("gh", {}).get("create_repo", False):
            return fail(f"repository {full} does not exist and create_repo is disabled")
        visibility = str(payload.get("gh", {}).get("visibility") or "private")
        created = subprocess.run(["gh", "repo", "create", full, f"--{visibility}", "--description",
                                  f"v4pro batch task {payload.get('task_id')} ({payload.get('project')})"],
                                 text=True, capture_output=True)
        if created.returncode != 0:
            return fail(f"repo create failed: {(created.stderr or created.stdout).strip()[-400:]}")
    elif gh_repo_empty(full) and payload.get("seed", {}).get("url"):
        pass  # retry of a previous failed prepare attempt: seed it below
    rc, message = push_seed(full, payload.get("seed") or {})
    if rc != 0:
        return fail(f"seed push failed for {full}: {message}")

    task_text = str(payload.get("task_text") or "").strip()
    if not task_text:
        return fail("prepare requires task_text (the issue body is the task source)")
    task_meta = {
        "kind": "V4PRO TASK", "version": 1, "at": now(),
        # 工作单是文档、由 controller 代发而不表态；干活与判决的发言
        # 一律以各条评论的 from 字段（worker|reviewer）为准。
        "from": "controller",
        "task_id": str(payload.get("task_id")),
        "project": str(payload.get("project")),
        "repo": full,
        "clone_url": gh_repo_url(payload),
        "task_dir": str(payload.get("task_dir")),
        "coder_dir": str(payload.get("coder_dir")),
        "reviewer_root": str(payload.get("reviewer_root")),
        "loop": "worker 读工作单并 clone -> 交活 -> reviewer 判决 (PASS|FAIL) -> worker 修复 -> ... -> reviewer 合并",
    }
    title = str(payload.get("issue_title") or f"[v4pro] {payload.get('project')} task-{payload.get('task_id')}")
    body_lines = [
        f"**[v4pro 工作单] task-{payload.get('task_id')} {payload.get('project')} · "
        f"任务要求 = 本 issue 正文（coder 从 GitHub 读本单并克隆 {full} 开工）**",
        "",
        "<!-- V4PRO TASK v1 -->",
        "```json",
        json.dumps(task_meta, ensure_ascii=False, indent=2),
        "```",
        "<!-- END V4PRO TASK v1 -->",
        "",
        "## 任务要求（coder 收到的正文，以 GitHub 上这份为准）",
        "",
        task_text,
    ]
    p = subprocess.run(["gh", "issue", "create", "--repo", full, "--title", title,
                        "--body", "\n".join(body_lines)], text=True, capture_output=True)
    if p.returncode != 0:
        return fail(f"issue create failed: {(p.stderr or p.stdout).strip()[-400:]}")
    try:
        number = int(p.stdout.strip().rstrip("/").split("/")[-1])
    except ValueError:
        return fail(f"cannot parse issue number from {p.stdout.strip()[-200:]}")
    issue = {"owner": str(payload["gh"]["owner"]), "repo": gh_repo_name(payload),
             "number": number, "url": p.stdout.strip()}
    patch_state(payload, issue=issue, repo=full, prepared_at=now(), phase="prepared")
    emit({"ok": True, "issue": issue, "repo": full})
    return 0


def cmd_issue_body(payload: Dict[str, Any]) -> int:
    """Read the Issue body back from GitHub (round trip) for the coder prompt."""
    state = load_state(payload)
    issue = state.get("issue") or {}
    if not issue.get("number"):
        return fail("no Issue recorded; run prepare first")
    # controller 传进来的 payload 可能没有 gh 字段：以 prepare 时记录的
    # issue.owner/issue.repo 为准，不现拼 gh_full_name(payload)。
    full = f"{issue.get('owner')}/{issue.get('repo')}"
    p = subprocess.run(["gh", "issue", "view", str(issue["number"]), "--repo", full,
                        "--json", "body", "--jq", ".body"], text=True, capture_output=True)
    if p.returncode != 0:
        return fail(f"issue body fetch failed: {(p.stderr or p.stdout).strip()[-400:]}")
    body = (p.stdout or "").strip()
    if not body:
        return fail(f"issue #{issue['number']} body is empty")
    emit({"ok": True, "body": body, "number": issue["number"]})
    return 0


def cmd_publish(payload: Dict[str, Any]) -> int:
    """Push coder main (idempotent), verify origin/main == HEAD, post READY."""
    state = load_state(payload)
    full = gh_full_name(payload)
    coder_dir = Path(os.path.expanduser(str(payload["coder_dir"])))

    # 仓库与工作单 Issue 由 prepare 阶段先行创建（coder clone 的工作前提）。
    if not sh_ok(["gh", "repo", "view", full]):
        return fail(f"repository {full} missing; the prepare step must run before coder/publish")
    origin = subprocess.run(["git", "-C", str(coder_dir), "remote", "get-url", "origin"],
                            text=True, capture_output=True)
    want = f"https://github.com/{full}.git"
    if origin.returncode != 0:
        sh(["git", "-C", str(coder_dir), "remote", "add", "origin", want])
    elif origin.stdout.strip() != want:
        sh(["git", "-C", str(coder_dir), "remote", "set-url", "origin", want])

    # 合并门前置检查：coder 工作区必须干净。未提交/未跟踪的文件不会被
    # push，但如果悄悄放行，这些文件会永远消失 —— 必须 fail-loud 让人看。
    status = subprocess.run(["git", "-C", str(coder_dir), "status", "--porcelain"],
                            text=True, capture_output=True)
    if status.returncode != 0:
        return fail(f"worktree status failed: {(status.stderr or status.stdout or '').strip()[-200:]}")
    if (status.stdout or "").strip():
        return fail(f"coder worktree is dirty; refusing publish:\n{(status.stdout or '').strip()[:400]}")

    commit = sh(["git", "-C", str(coder_dir), "rev-parse", "HEAD"])
    push = subprocess.run(["git", "-C", str(coder_dir), "push", "-u", "origin", "main"],
                          text=True, capture_output=True)
    if push.returncode != 0:
        return fail(f"push failed: {(push.stderr or push.stdout).strip()[-400:]}")
    # 合并门的最外层：GitHub 上的 main 必须就是被审的 HEAD。
    ls = subprocess.run(["git", "ls-remote", gh_repo_url(payload), "main"],
                        text=True, capture_output=True)
    remote_sha = (ls.stdout or "").split()[0] if ls.stdout.strip() else ""
    if remote_sha != commit:
        return fail(f"origin/main {remote_sha[:12]} != coder HEAD {commit[:12]}; GitHub is not up to date")

    issue = state.get("issue") or {}
    if not issue.get("number"):
        return fail("no Issue recorded; run prepare first")

    ready = {
        "kind": "V4PRO READY", "version": 1, "at": now(),
        "from": "worker",
        "task_id": str(payload.get("task_id")),
        "commit": commit,
        "previous_commit": str(payload.get("previous_commit") or ""),
        "round": int(payload.get("round") or 0),
    }
    if int(ready["round"]) > 0:
        first_line = f"[worker 修复] 第 {ready['round']} 轮修复 commit {commit[:12]} 已推送，等待复审"
    else:
        first_line = f"[worker 交付] commit {commit[:12]} 已推送，等待评审"
    body_text = (f"**{first_line}**\n\n<!-- V4PRO READY v1 -->\n```json\n"
                 f"{json.dumps(ready, ensure_ascii=False, indent=2)}\n```\n<!-- END V4PRO READY v1 -->\n")
    p = subprocess.run(["gh", "issue", "comment", str(issue["number"]), "--repo", f"{issue['owner']}/{issue['repo']}",
                        "--body-file", "-"], input=body_text, text=True, capture_output=True)
    if p.returncode != 0:
        return fail(f"READY comment failed: {(p.stderr or p.stdout).strip()[-400:]}")

    patch_state(payload, issue=issue, repo=full, last_ready_commit=commit,
                pushed_at=now(), phase="ready_posted")
    emit({"ok": True, "issue": issue, "commit": commit, "repo": full})
    return 0


def cmd_finalize_review(payload: Dict[str, Any]) -> int:
    """Post the machine REVIEW comment from the reviewer's result file."""
    state = load_state(payload)
    issue = state.get("issue") or {}
    if not issue.get("number"):
        return fail("no Issue recorded; run publish first")
    td = Path(payload["task_dir"])
    result_path = td / "artifacts" / "review_result.json"
    result = read_json(result_path, None)
    status = "BLOCKED"
    fix_requests: list = []
    summary = "reviewer did not produce a valid review_result.json"
    if isinstance(result, dict):
        status = str(result.get("status") or "BLOCKED").upper()
        if status not in VALID_REVIEW_STATUS:
            status = "BLOCKED"
        fix_requests = result.get("fix_requests") or []
        summary = str(result.get("summary") or "")
    comment = {
        "kind": "V4PRO REVIEW", "version": 1, "at": now(),
        "from": "reviewer",
        "task_id": str(payload.get("task_id")),
        "commit": str(payload.get("commit") or state.get("last_ready_commit") or ""),
        "status": status,
        "round": int(payload.get("round") or 0),
        "summary": summary[:2000],
        "fix_requests": fix_requests[:50],
        "artifacts": {
            "result": str(result_path),
            "report": str(td / "artifacts" / "review_report.md"),
        },
    }
    detail = f" · {len(fix_requests)} 条修复要求" if status == "FAIL" else ""
    first_line = f"[reviewer 判决] 第 {comment['round']} 轮 · {status}{detail}"
    body_text = (f"**{first_line}**\n\n<!-- V4PRO REVIEW v1 -->\n```json\n"
                 f"{json.dumps(comment, ensure_ascii=False, indent=2)}\n```\n<!-- END V4PRO REVIEW v1 -->\n")
    p = subprocess.run(
        ["gh", "issue", "comment", str(issue["number"]), "--repo", f"{issue['owner']}/{issue['repo']}",
         "--body-file", "-"], input=body_text, text=True, capture_output=True)
    if p.returncode != 0:
        return fail(f"REVIEW comment failed: {(p.stderr or p.stdout).strip()[-400:]}")
    patch_state(payload, last_review={"commit": comment["commit"], "status": status,
                                      "round": comment["round"], "at": now()}, phase="review_posted")
    emit({"ok": True, "status": status, "round": comment["round"]})
    return 0


def cmd_accept(payload: Dict[str, Any]) -> int:
    """Merge gate for the single-branch model: HEAD==reviewed commit, clean
    tree, then push main and post the MERGE comment."""
    coder_dir = Path(os.path.expanduser(str(payload["coder_dir"])))
    commit = str(payload.get("commit") or "").strip()
    if not commit:
        return fail("accept requires the reviewed commit")
    head = sh(["git", "-C", str(coder_dir), "rev-parse", "HEAD"])
    if head != commit:
        return fail(f"coder HEAD {head[:12]} != reviewed commit {commit[:12]}")
    dirty = sh(["git", "-C", str(coder_dir), "status", "--porcelain"])
    if dirty.strip():
        return fail("coder tree is dirty; cannot accept")
    push = subprocess.run(["git", "-C", str(coder_dir), "push", "origin", "main"],
                          text=True, capture_output=True)
    if push.returncode != 0:
        return fail(f"accept push failed: {(push.stderr or push.stdout).strip()[-400:]}")

    state = load_state(payload)
    issue = state.get("issue") or {}
    if issue.get("number"):
        comment = {"kind": "V4PRO MERGE", "version": 1, "at": now(),
                   "from": "reviewer",
                   "task_id": str(payload.get("task_id")), "commit": commit,
                   "review_round": int(payload.get("round") or 0)}
        first_line = (f"[reviewer 合并] 第 {comment['review_round']} 轮 PASS 已生效 · "
                      f"{commit[:12]} 核验通过，main 已推送")
        body_text = (f"**{first_line}**\n\n<!-- V4PRO MERGE v1 -->\n```json\n"
                     f"{json.dumps(comment, ensure_ascii=False, indent=2)}\n```\n<!-- END V4PRO MERGE v1 -->\n")
        p = subprocess.run(
            ["gh", "issue", "comment", str(issue["number"]), "--repo", f"{issue['owner']}/{issue['repo']}",
             "--body-file", "-"], input=body_text, text=True, capture_output=True)
        if p.returncode != 0:
            return fail(f"MERGE comment failed: {(p.stderr or p.stdout).strip()[-400:]}")
    patch_state(payload, phase="accepted", accepted_commit=commit, accepted_at=now(),
                coder_status="success", final_status="accepted")
    emit({"ok": True, "accepted_commit": commit})
    return 0


def cmd_prep_review(payload: Dict[str, Any]) -> int:
    """Start of a new review round: archive the previous round's verdict files.

    So the next verdict cannot be confused with a stale one.
    """
    artifacts = Path(payload["task_dir"]) / "artifacts"
    round_no = int(payload.get("round") or 0)
    if round_no <= 1:
        emit({"ok": True, "archived": 0})
        return 0
    prev = artifacts / f"round-{round_no - 1}"
    prev.mkdir(parents=True, exist_ok=True)
    moved = 0
    for name in ("review_report.md", "review_result.json", "review_test.log", "fix_request.json"):
        src = artifacts / name
        if src.exists():
            src.rename(prev / name)
            moved += 1
    emit({"ok": True, "archived": moved, "to": str(prev)})
    return 0


def cmd_git_head(payload: Dict[str, Any]) -> int:
    coder_dir = Path(os.path.expanduser(str(payload["coder_dir"])))
    if not (coder_dir / ".git").exists():
        return fail("coder dir has no git repository", {"commit": None})
    emit({"ok": True, "commit": sh(["git", "-C", str(coder_dir), "rev-parse", "HEAD"])})
    return 0


def cmd_clean_dir(payload: Dict[str, Any]) -> int:
    """清空并重建一个 work_root 下的目录（由 controller 委托 worker 侧执行）。

    用途：coder 基础设施失败后清理半成品工作区（coder 的启动前提是空目录、
    自己从 GitHub clone）。必须在 worker 上跑：远程 worker 场景里 controller
    本机的 rmtree 摸不到对方的文件系统。只允许清理 work_root 之内，防误删。
    """
    target = str(payload.get("dir") or "").strip()
    if not target:
        return fail("clean-dir requires dir")
    tgt = Path(os.path.expanduser(target))
    work_root = Path(os.path.expanduser(str(payload.get("work_root") or "")))
    if not tgt.is_relative_to(work_root):
        return fail(f"clean-dir target {target} outside work_root {work_root}")
    if tgt.exists():
        shutil.rmtree(tgt, ignore_errors=True)
    tgt.mkdir(parents=True, exist_ok=True)
    emit({"ok": True, "cleaned": target})
    return 0


def cmd_read_result(payload: Dict[str, Any]) -> int:
    path = Path(payload["path"])
    if not path.is_file():
        return fail(f"missing {path}", {"result": None})
    emit({"ok": True, "result": read_json(path, None)})


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

COMMANDS = {
    "check": cmd_check,
    "start": cmd_start,
    "mark-running": cmd_mark_running,
    "mark-done": cmd_mark_done,
    "status": cmd_status,
    "probe": cmd_probe,
    "outcome": cmd_outcome,
    "alive": cmd_alive,
    "reset-phase": cmd_reset_phase,
    "stop": cmd_stop,
    "prepare": cmd_prepare,
    "issue-body": cmd_issue_body,
    "publish": cmd_publish,
    "finalize-review": cmd_finalize_review,
    "accept": cmd_accept,
    "git-head": cmd_git_head,
    "clean-dir": cmd_clean_dir,
    "prep-review": cmd_prep_review,
    "read-result": cmd_read_result,
}


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(json.dumps({"ok": False, "error": f"usage: {Path(sys.argv[0]).name} {'|'.join(sorted(COMMANDS))} [--payload-stdin] [--key value ...]"}))
        return 2
    name = args[0]
    fn = COMMANDS.get(name)
    if fn is None:
        print(json.dumps({"ok": False, "error": f"unknown command {name!r}"}))
        return 2
    payload: Dict[str, Any] = {"role": "coder"}
    if "--payload-stdin" in args:
        payload = load_stdin_payload()
    # allow subprocess-style: --task-dir /x --role review --rc 0 --state ok
    i = 1
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if key == "payload_stdin":
                i += 1
                continue
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                payload[key] = args[i + 1]
                i += 2
            else:
                payload[key] = True
                i += 1
        else:
            i += 1
    return _run(name, fn, payload)


def _run(name: str, fn, payload: Dict[str, Any]) -> int:
    if name in ("status", "alive", "reset-phase", "stop", "mark-running", "mark-done", "start", "prepare", "issue-body", "publish", "finalize-review", "accept", "git-head", "prep-review", "read-result", "probe", "outcome"):
        if "task_dir" in payload:
            payload["task_dir"] = os.path.expanduser(str(payload["task_dir"]))
    try:
        return fn(payload)
    except Exception as exc:  # never leave the controller without a JSON answer
        return fail(f"{name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
