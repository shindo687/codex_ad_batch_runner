# 示例批次：kwant 的 4 个 AD 上游缺口 issue + 四合一任务（真实任务）

五个任务文件来自一次真实生产批次（`tasks/task_kwant_xj{2,3,4,5,_all}.md`）：
issue 正文按原始格式逐字保留（Summary、范围、验收条件、复现命令），仅外部组织
路径与作者信息按共享口径做了脱敏。它们不是 mock，body 内的测试与验收要求就是
coder 收到的原文。

| task_id | 项目 | issue 内容一句话 |
|---------|------|------------------|
| xj2 | kwant_xj2 | 散射与格林函数求解器（smatrix/greens_function/ldos/wave_function/modes/selfenergy）缺 AD |
| xj3 | kwant_xj3 | Bands 本征矢导数被拒，挡住 Berry/QGT/BdG 敏感度 |
| xj4 | kwant_xj4 | 复数态 Density/Current 的 JVP/VJP |
| xj5 | kwant_xj5 | KPM 定矩谱密度对哈密顿量的求导 |
| xj_all | kwant_xj_all | 上面四个缺口在一个仓库、一条提交链里一起修（SECTION n OF 4 格式示例） |

真实批次用的种子 = issue 发生时刻的内部仓库 commit
（SHA `fd4470d049d01bc0486eaa96f7b76a570ea6915f`）。作为公开示例，
种子改填你自己的仓库（任意 git 远程，支持分支名或 40 位 SHA）。

配套 `tasks.csv` 直接可用：改 seed_url/seed_ref 两列后，
按 RUNBOOK_EN.md 建批次目录并启动 controller 即可。
