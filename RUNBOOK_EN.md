# Runner onboarding (collaborators)

This repo lets you run "coder / reviewer / fixer" loops for one issue per Git
repo. One instance of the runner = one **batch**: a `tasks.csv` of issues, a
`config.json`, and a state dir. Each task gets its own fresh GitHub repo and
issue; the loop is: agent (coder/fix) works → reviewer verdicts PASS/FAIL →
fix rounds until accept, hard stop.

## Architecture in one picture

```
tasks.csv ──► controller.py ──► remote_agent.py ──► GitHub (repo + issue per task)
                 │  (state/controller.log)
                 ▼
        per-task dirs: tasks/task-N/{logs,artifacts,state.json}
        work dirs:     <work_root>/<project><suffix>          (coder/fix hand)
                       <work_root>/<project><suffix>_reviewer (review hand)
```

## Prerequisites

1. `codex` CLI installed and logged in on your machine. Verify your account
   can actually use the model you want: run a tiny
   `codex exec -m <model> "reply exactly OK"` first.
   Model availability is account/plan dependent.
2. `gh` CLI logged in (needs permission to create private repos).
3. Seedable access to the starter repository: prepare clones it with your git
   credentials. Seeds may be a branch name or a full 40-char commit SHA
   (SHA = "start from the state at issue creation time").

## Start a batch

```
mkdir mybatch && cd mybatch
cp <this-repo>/controller.py <this-repo>/remote_agent.py .
cp <this-repo>/template/config.template.json config.json
cp <this-repo>/template/tasks.template.csv  tasks.csv
mkdir tasks && cp <this-repo>/template/tasks_src/task.template.md tasks/task_myissue1.md
# 编辑三个 PLACEHOLDER 与 owner/suffix；suffix 必须唯一(与你的其他批次不撞),
# 已有同 suffix 的仓库会让 prepare 报错拒绝复用。
python3 controller.py --config config.json --tasks-csv tasks.csv --loop 43200
```

Watch: `tail -f state/controller.log`；live agent output:
`tasks/task-1/logs/coder_r0.log` (prompt kept at `*_r0_prompt.md`).
GitHub side: each task repo + issue #1 carries the run record.

## Key rule (failure modes we hit)

- Task md = the issue text verbatim; '未准备好' 状态不允许空任务。
- Same suffix must never be reused across batches (prepare refuses).
- Seeds push to the fresh repo as `refs/heads/main`; SHAs also allowed.
- Agents MUST `git push origin main` before finishing; controller verifies.
- `zombie_after_secs` (20 min no disk writes) kills and fails over; 3 fails
  per role; probes gate dispatch (probe_budget 60).

## Running agents

```
codex exec -m <model> ...        (SUT agent, model pinned per batch config)
```
Reasoning effort has no CLI flag; it comes from `codex`'s global config
(`model_reasoning_effort`). Pin `-m` in the batch's `agents.presets.*.cmd`
so restarts/failovers stay on the same model.