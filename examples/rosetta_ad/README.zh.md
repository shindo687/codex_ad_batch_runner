# 示例任务：Rosetta 打分接口 AD（from-scratch 任务书）

`tasks/task_rosetta_ad_v4pro.md` 是一次真实试跑使用的 from-scratch 任务书
（不是从 GitLab issue 抄录，而是人工撰写的任务规格），与 issue 式任务形成对照：
目标与边界、范围（固定序列/拓扑能量、构象界面能、RMSD）、验收清单、交付形式
全部写在任务书里，coder 收到这份全文。

与 issue 式任务不同，from-scratch 任务可以不需要种子仓库：若用空仓库起步，
把 `seed_url/seed_ref` 两列留空或删除即可；runner 会把任务书作为 GitHub issue #1
正文发给 coder。

试跑原版在四台远程主机上跑了四份独立实现（同一份任务书），本示例只放单机一行。
