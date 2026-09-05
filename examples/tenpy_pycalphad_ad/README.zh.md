# 示例批次：tenpy + pycalphad 真实 AD 上游缺口 issue

四个任务文件来自一次真实生产批次：
`tasks/task_tenpy_xj1.md`、`tasks/task_pycalphad_xj{1,2,_all}.md`。
issue 正文按原始格式逐字保留（Summary、范围、验收条件、复现命令），仅外部组织
路径与作者信息按共享口径做了脱敏。它们不是 mock。

| task_id | 项目 | issue 内容一句话 |
|---------|------|------------------|
| xj1 | tenpy_xj1 | MPS overlap / MPO expectation_value 状态级收缩的可微版本 |
| pyc_xj1 | pycalphad_xj1 | 固定 Model 性质的可组合二阶导数（HVP） |
| pyc_xj2 | pycalphad_xj2 | equilibrium / calculate 工作流的隐式导数（有约束最优点导数） |
| pyc_xj_all | pycalphad_xj_all | 上面两个缺口在一个仓库、一条提交链里一起修 |

真实批次用的种子 = issue 发生时刻的内部仓库 commit：
tenpy `76c77b78e4c367749ffc69ea87782d229a5534f6`，
pycalphad `85554b44ce0e0bb821f4e19a63b3c0c4be953386`。
作为公开示例，种子改填你自己的仓库（任意 git 远程，支持分支名或 40 位 SHA）。

配套 `tasks.csv` 直接可用：改 seed_url/seed_ref 两列后，
按 RUNBOOK_EN.md 建批次目录并启动 controller 即可。
