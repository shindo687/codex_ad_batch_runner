# 示例批次：quspin 的 3 个 AD 上游缺口 issue（真实任务）

这三个任务文件来自一次真实生产批次（`tasks/task_quspin_xj{1,2,3}.md`）：
issue 正文按原始格式逐字保留（Summary、范围、验收条件），仅外部链接与作者信息
按共享口径做了脱敏。它们不是 mock，body 内的测试与验收要求就是 coder 收到的原文。

| task_id | 项目 | issue 内容一句话 |
|---------|------|------------------|
| xj1 | quspin_xj1 | 让动态驱动参数穿过固定网格轨迹可求导 |
| xj2 | quspin_xj2 | 补 Floquet 本征系统（准能量/本征矢）微分规则 |
| xj3 | quspin_xj3 | 已有 7 条平滑规则的二阶组合（HVP） |

真实批次用的种子 = issue 发生时刻的内部仓库 commit
（SHA `3fd649035b1d46d7657be011b3266a8520ef8103`）。作为公开示例，
种子改填你自己的仓库（任意 git 远程，支持分支名或 40 位 SHA）。

配套 `tasks.csv` 直接可用：改 seed_url/seed_ref 两列后，
按 RUNBOOK_EN.md 建批次目录并启动 controller 即可。
