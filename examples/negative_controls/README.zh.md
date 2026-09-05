# 负向对照批次：验证 runner 的失败路径（僵尸、断通、污染、评审拒收）

四个子目录是 v4pro 开发期做 `--check` 用的负向对照（negative controls），
全部围绕 `tasks/task_numkit_simple.md` + 假 agent 剧本，用来验证：

| 目录 | 对照什么 |
|------|----------|
| neg6 | reviewer 僵尸（有会话无落盘）→ 按 `zombie_after_secs` 超时击杀并换人 |
| neg7 | reviewer 断通（`FAKE_PI_MODE=infra`）+ 正常剧本的 failover 下线 |
| neg8 | 只有断通 reviewer（无正常替补）→ 落终态而不是静默循环 |
| neg9 | coder 污染（`FAKE_CODEX_MODE=infra_pollute`）→ 判定 infra 而非真失败 |

假 agent 就是仓库根目录的 `test_fake_codex.py` / `test_fake_pi.py`，通过
`FAKE_CODEX_MODE` / `FAKE_PI_MODE` 环境变量换剧本；config.json 里的 preset
命令已改成相对路径，把两个脚本拷进你的批次目录即可直接跑。

使用注意（与真实批次相同的约定）：

- `config.json` 的 `tasks_csv` 指向 `tasks/negN/tasks.csv`：把 negN 目录放到
  你批次目录的 `tasks/` 下，或改 `tasks_csv` 路径；
- repo suffix 每个目录不同（`_dsv4pro_v3n6` 等），跑一封批次要换新 suffix；
- 这些配置用 `work_root: ~/ad_xjtan_v4pro_negtest`、`remote_agent_dir:
  ~/codex_v4pro_dev_neg`，验证完毕请清理这两个目录与建出来的私有仓库。