# agents：按角色指派干活 agent（强制显式，无默认）

v4pro 的三个角色各自必须被**显式**指派一个 agent，不存在静默默认。缺失即启动失败：

- `coder`：全新仓库从零写码
- `fix`：在 coder 工作区按审查请求修改
- `review`：独立工作区审 commit、跑测试、出判决

## 配置位置（三层，越往下优先级越高）

1. `config.json` -> `agents.roles`：本批的默认指派（角色 -> preset 名，**有序列表**）
2. `tasks.csv` 每行的 `coder_agent` / `fix_agent` / `review_agent` 列（可选）：只覆盖那一行
3. 命令行 `--codex-command X`：全局覆盖**全部角色**（测试桩专用；用来跑 test_fake_codex_bad.py，
   此时列表只剩一位、跳过探针）

`agents.presets` 定义可用的 agent：

```json
"agents": {
  "presets": {
    "codex":   { "cmd": "codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check",
                 "style": "stdin", "probe": { "expect": "OK", "timeout_seconds": 45 } },
    "pi":      { "cmd": "pi -p --no-session", "style": "atfile",
                 "probe": { "expect": "OK", "timeout_seconds": 45 } },
    "pi-kimi": { "cmd": "pi-kimi -p --no-session", "style": "atfile",
                 "probe": { "expect": "OK", "timeout_seconds": 45 } }
  },
  "roles": { "coder": ["codex"], "fix": ["codex"], "review": ["pi-kimi", "codex"] }
}
```

角色值支持：有序列表 `["pi-kimi", "codex"]`、单个字符串 `"pi-kimi"`、逗号串
`"pi-kimi, codex"`（csv 里逗号列表要打引号）。列表顺序 = 失效轮换顺序。

## style：提示词怎么递进 agent

| style     | runner 生成形式                          | 适用           |
|-----------|------------------------------------------|----------------|
| `stdin`   | `{cmd} - < prompt.md`                    | codex          |
| `atfile`  | `{cmd} '@prompt.md' < /dev/null`         | pi / pi-kimi   |
| `argvfile`| `{cmd} "$(cat prompt.md)" < /dev/null`   | 提示词短小通用  |

路径全部 shlex 引号包裹；atfile/argvfile 的 stdin 是 /dev/null，避免 agent 误等标准输入。

## fail-loud 语义

- 角色没有指派（roles 缺、csv 缺、preset 名字错）=> `SystemExit`，启动即中止
- agent 进程退出码 != 0 => 阶段落失败终态（review->failed_review，fix->failed_fix，coder->failed），不静默重试
- 已实测：`pi -p` 与 `pi-kimi -p` 在无 TTY 环境下正常（rc=0）；API 报错时 pi rc=1（errord在 stderr/stdout）。注意 `--provider <不存在的名字>` 会被 pi 静默回退到默认 provider 并 rc=0，preset 拼写要靠 --check 的 agents 行人工核对
- --check 会打印每个任务的最终指派（如 `review=[pi-kimi|codex]`）；每次阶段开工日志也带 `agent=<name>`，落账可审计

## A：agent 失效转指（failover，显式、可数、封顶）

- **派工前探针**：每个候选 agent 开工前跑 1-token 级迷你提示词
  （`Reply with exactly the word: OK`，subprocess timeout=45 兜底）。rc=0 且输出含
  `expect` 才算康；不康的跳过试下一位。preset 里 `"probe": {"enabled": false}` 的
  测试桩永不浪费 token；--codex-command 覆盖同样跳过。全都不康：本 tick 不派工
  只 park 计数（顺带实现全局 API 停摆急停），`probe_fail_budget`（默认 60）打满落终态。
- **工后分类**（worker 侧 `outcome` 命令取 rc/时长/日志字节/日志尾，controller 侧
  `infralike()` 双轨判）：
  1. <120 秒且日志 <1KB（没来得及产出真内容）；
  2. 日志尾含断通路短语（Connection error / 404 / 429 / upstream …，中途断线也中）。
  时长取数缺失时标记字仍算 infra；两轨都缺判为真死。
- **infra 死亡** -> 列表下一位 agent 重开**同一轮**（review 不虚增轮次、prep-review 跳过），
  task 级 failover 预算 `failover_cap`（默认 3）/轮，打满落 `failed_*`（绝不静默无限还人）。
  真干砸 / rc=124 超时行为不变：照旧 fail-loud。
- 新旋钮：`failover_cap`、`probe_fail_budget`（CLI：--failover-cap/--probe-fail-budget）

## B2：工人假死探测（实例级，非进程级）

- worker `status` 增加 liveness：进程存活 + 最新写龄（工作区+task_dir 最新 mtime
  距今秒数，统筹 .git、4000 文件上限）。判死不用 stdout 字节（pi 块缓冲会假报），
  工作区里 pi 每走一次工具都写盘，是可靠信号。
- controller 每 tick：进程活但写龄 > `zombie_after_secs`（默认 1200 = 20 分钟，
  阶段启动宽限 30s）→ 杀会话 → 走 A 的 failover 引擎。CLI：--zombie-after 秒数。

## 测试

- 单元：`python3 -m unittest discover -s tests`（tests/test_agents.py：三种 style 生成器 +
  解析/校验 + roles 列表 + infralike 判别，33 项）
- 负面端到端零 API：`bash run_negative_tests.sh`（场景 5 = csv 指派 atfile 假 pi 炸掉 ->
  failed_review；场景 6/7/8 = 僵尸/infra 标记字 failover 成功判决 + cap 打满 fail-loud）
- 真机冒烟（几条 token 成本）：
  `printf 'Reply with exactly the word: OK' > p.md && pi -p --no-session @p.md < /dev/null; echo rc=$?`
## R1：coder infra failover 清理工作区（评审修复，2026-09-04）

- 坑：coder 的启动前提是空工作区（自己从 GitHub clone）。infra 死了的半成品
  不清掉，coder_pending 会永远卡 "workdir not empty"——failover 计数没机会增。
- 修：failover / 会话死恢复里 coder 分支一律委托 worker 执行新命令
  `clean-dir`（远程 worker 上 controller 本机的 rmtree 摸不到目录——同源 bug 一并修）。
- `clean-dir` 只清 work_root 之内；越界拒绝。场景 9（tasks/neg9）零 API 验证：
  假 coder 留半成品断线 → clean-dir → failover → 终态 accepted。

## P1：accept 重试上限（评审修复，2026-09-04）

- 坑：accept 失败（dirty/HEAD 不齐/push 拒）会每 tick 重试到永远，不响不亮。
- 修：`max_accept_retries`（默认 6）打满落 `failed_publish`（fail-loud），成功后归零。

## agent 命令 env 前缀（负面场景装配坑，2026-09-04）

- `VAR=val cmd ...` 形式的 preset cmd 现在支持：赋值前缀保留为环境赋值词，
  不参与首词双引号包裹（否则 execvp 找名为 "VAR=val" 的可执行 → rc=127，
  秒死进 infra 轨会误烧 failover 预算）。三种 style 均适用。
