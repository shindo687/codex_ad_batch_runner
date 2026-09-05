# v4pro - simplest runnable batch loop

A from-scratch, deliberately minimal version of the codex AD batch runner.
Two stdlib-only Python files:

- `controller.py` - runs on the Mac; schedules tasks and drives the loop.
- `remote_agent.py` - runs on every worker host (adm1-adm4, or `local`);
  starts detached codex processes, does all git/GitHub operations with the
  host's own `gh` credentials.

The task text decides what the work is (a tiny package, an AD workload,
anything); the controller only orchestrates directories, git/GitHub and the
review evidence.  No package or domain names are hard-coded anywhere.

## The loop

Per task, one host, serialized:

```text
prepare: create private GitHub repo + work-order Issue (body = full task text)
coder reads the Issue body (fetched from GitHub) and git-clones the repo itself
  -> writes code in <work_root>/<project><suffix>/ -> commits -> git push
  -> Issue comment V4PRO READY(commit)
reviewer runs in <work_root>/<project><suffix>_reviewer/round-<N>/
  (a fresh clone FROM GITHUB, checked out at the reviewed commit)
  -> writes review_report.md + review_result.json
  -> Issue comment V4PRO REVIEW(PASS|FAIL|BLOCKED)
FAIL and rounds left:
  -> fixer syncs coder dir with origin/main, fixes, commits, pushes, back to READY
PASS:
  -> merge gate (HEAD == reviewed commit, clean tree, origin/main == HEAD)
  -> push -> V4PRO MERGE
```

- GitHub 是任务的唯一事实来源：`prepare` 阶段先建私有仓库并发布工作单 Issue
  （正文 = 完整任务文本）；controller 随后从 GitHub 把 issue 正文读回交给
  coder，coder 自己 `git clone` 仓库开工；reviewer 每一轮都从 GitHub 克隆。
- Reviewer and coder always work in different subdirectories of the same big
  work root: the reviewer dir is the coder dir name plus `_reviewer`.
- The GitHub repo name is `<project><suffix>`; `suffix` is configurable
  (default `_dsv4pro_v1`). Reusing the suffix of an existing repo is refused
  at prepare (fail-loud: one batch, one suffix).
- `work_root` is the big directory on the worker host (default
  `~/ad_xjtan_v4pro`); every worker gets the same layout.
- All state, logs and artifacts live under the remote work root:
  `tasks/task-<id>/` holds `state.json`, `logs/`, `artifacts/`.

Issue comment protocol (machine events, JSON in comment bodies):

```text
<!-- V4PRO READY  v1 --> {from: worker, commit, previous_commit, round} <!-- END V4PRO READY  v1 -->
<!-- V4PRO REVIEW v1 --> {from: reviewer, commit, status, round, fix_requests[], ...} <!-- END V4PRO REVIEW v1 -->
<!-- V4PRO MERGE  v1 --> {from: reviewer, commit, review_round} <!-- END V4PRO MERGE  v1 -->
```

每条评论正文第一行是人类可读的角色标题（如 `[reviewer 判决] 第 1 轮 · FAIL · 1 条修复要求`），
GitHub 时间线不用展开就能看出这条属于谁；JSON 里的 `from` 字段给机器解析用。
整个 loop 只有两个角色：`worker`（coder/fixer，交活）和 `reviewer`（判决；PASS 的
合并门也归 reviewer，是判决的机器执行）。
Issue 正文（工作单）在开工前由 controller 代发（机器建的文档、不表态），带机器标记和完整任务文本：

```text
<!-- V4PRO TASK   v1 --> {from: controller, task_id, project, repo, clone_url, ...} <!-- END V4PRO TASK v1 -->
```

干活的首次发言是 worker 的交付/修复（`V4PRO READY`）。所有内容都使用同一个 gh 账号发布
（机器代发），发言角色以 `from` 字段（worker|reviewer）为准，不要凭发布者账号判断；
工作单本身是文档，不由任何角色署名。

## Requirements

- Mac: python3, ssh aliases or a local host; `gh` + `codex` on every worker
  host (the Mac itself counts as host `local`).
- Worker hosts need `tmux` (detached session) or fall back to
  `nohup`+`setsid`; `timeout` is used when available.

## Fast local loop test (recommended first run)

Two flavors:

### A. Free plumbing test (fake codex, real git/GitHub)

`test_fake_codex.py` is a deterministic stand-in for codex: the coder writes a
numkit package missing a module docstring, the reviewer really runs the tests
and FAILs it, the fixer adds the docstring, the next review PASSes.  Same
code path as the real loop (same runner scripts, same repo/issue operations),
zero codex cost:

```bash
python3 controller.py --config config.json --tasks-csv tasks.local.csv \
    --workers local --work-root $HOME/ad_xjtan_v4pro_test \
    --repo-suffix _dsv4pro_v1t4 \
    --codex-command 'python3 $HOME/ad_xjtan/codex_ad_batch_runner_v4pro/test_fake_codex.py' \
    --loop 600
python3 controller.py --show-status
```

Verified 2026-09-03 on this Mac (旧流程): coder rc=0 -> publish -> READY comment ->
review r1=FAIL (1 fix request) -> fixer commit -> READY -> review r2=PASS ->
merge gate holds (HEAD == reviewed commit) -> push -> MERGE comment.
Issue comments, repo tree, state.json, logs and artifacts all cross-checked.

### B. Real codex run

Same as A but without `--codex-command` (uses the real `codex` binary on the
worker host). The task `tasks/task_numkit_simple.md` is intentionally tiny:

```bash
python3 controller.py --config config.json --tasks-csv tasks.local.csv \
    --workers local --work-root $HOME/ad_xjtan_v4pro_test \
    --repo-suffix _dsv4pro_v1real --dry-run          # plan only

python3 controller.py --config config.json --tasks-csv tasks.local.csv \
    --workers local --work-root $HOME/ad_xjtan_v4pro_test --check

python3 controller.py --config config.json --tasks-csv tasks.local.csv \
    --workers local --work-root $HOME/ad_xjtan_v4pro_test \
    --loop 2400                                   # run to completion (polls)
python3 controller.py --show-status
```

This creates `github.com/<你的GitHub账号>/numkit_dsv4pro_v1real` (private). The
`_reviewer` subdirectory layout is identical to the remote hosts', so the
loop is exercised end-to-end without touching adm1-adm4.

**One suffix per batch.** If the repo already exists (a previous batch used
the same suffix), the publish push is rejected on purpose: never reuse a
suffix, pick the next one (`_dsv4pro_v2`, ...).

## Remote run (adm1-adm4)

```bash
python3 controller.py --check        # syncs remote_agent.py + verifies env
python3 controller.py --dry-run
python3 controller.py --once         # one scheduling pass
python3 controller.py --loop 7200    # keep polling until terminal
python3 controller.py --retry-task 1 --once
```

Change `work_root` or `repo_suffix` in `config.json` (or via CLI flags) when
you want a different batch directory / a new repo generation (for example
`_dsv4pro_v2`). See `python3 controller.py --help` for all flags
(`--codex-command` is the escape hatch for fake/test binaries).

## Deliberately missing (vs the parent repository)

This is the *simplest runnable* line, not a policy-complete system:

- no AD/API acceptance contract, no `AD_BATCH_POLICY.md` enforcement
  (optional: set `policy_file` in config to one and it is synced+referenced);
- no resource monitor, heartbeats, Feishu updates or secret redaction;
- single-branch model: coder commits directly on `main`, review is on a
  local clone, fix commits continue `main` (no branch per attempt);
- one slot per host, no per-host concurrency, no launch-intent replay;
- timeouts are enforced only when the host has `timeout` (Linux hosts do,
  macOS does not);
- no upstream/original read-only guard (real AD runs should keep their
  upstream checkout on a path outside the work root and treat it read-only
  by discipline).

Add these back (from the parent repo) only if a task set needs them.