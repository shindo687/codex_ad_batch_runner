<!-- provenance: from-scratch task book (not a GitLab issue), authored 2026-09-05 -->
# 任务：为 Germinal / BindCraft 使用的 Rosetta 打分接口增加 AD

## 目标与边界

交付独立安装的 `rosetta_ad` 配套包，为 PyRosetta 在 binder / antibody 后处理中的
连续打分计算提供 ChainRules `jvp`、`vjp`、`grad`、`value_and_grad`。
先完成固定序列、固定原子拓扑的能量、固定构象界面能和 RMSD 求导。
不改造整个 Rosetta，不运行完整蛋白设计流水线，不实现 FastRelax 的端到端导数。

这是一个完整的单任务，可由 runner 分配给一台主机执行；本文件不是 adm1–adm4
部署清单，不自行给其他主机派活、创建额外批次或修改 runner。

## 来源与规范

任务正文自包含，不依赖发起机上的调研文件。以下固定版本用于恢复调用语义：

- Rosetta 上游：`https://github.com/RosettaCommons/rosetta.git`。
  源码调查点：`de92a3c0dea8a010d372a22025e3e50bd4e2f33f`；不等于已安装 PyRosetta 的构建版本。
- [BindCraft PyRosetta 工具](https://github.com/martinpacesa/BindCraft/blob/efb5bfeb8b4b1a5944256f979c34e0c8e6a82d9d/functions/pyrosetta_utils.py)：`efb5bfeb8b4b1a5944256f979c34e0c8e6a82d9d`。
- [Germinal PyRosetta 工具](https://github.com/SantiagoMille/germinal/blob/1e1c1a5b79884ae45abae030c9df90d9423a990a/germinal/filters/pyrosetta_utils.py)：`1e1c1a5b79884ae45abae030c9df90d9423a990a`；改编自 BindCraft。
- 权威接口规范：只读克隆 `https://github.com/shindo687/ad-specs` 到交付仓库之外，
  先读 `AD_AGENT_EXECUTION_WORKFLOW.md` 及 `ad-rules/` 的 README、接口与一致性文档；记录所用 commit。

本任务依据用户要求，对通用模板的“完整 API 范围”作明确限定：只清点下表四项
及下文列出的暂缓能力，不遍历整个 Rosetta。其余原生语义、统一接口、不得修改上游、
不得使用生产数值差分和必须真实测试等规则保持有效。先写 Spec 再实现；
本任务给出的范围不需要重复询问，重大语义变化才请求决定。

## 第一轮交付范围

下列函数名是建议的配套包入口，不是声称上游已有同名 API。可调整命名，但不能
悄悄改变输入、输出或活动参数。公开入口必须可通过统一 AD 接口调用。

| ID | 建议入口及原生基础 | 必须交付的活动输入 |
|---|---|---|
| E1 | `score_pose`：原生 `ScoreFunction(pose)` | 全原子笛卡尔坐标 `xyz`、指定打分项的权重 `weights` |
| E2 | `interface_dg_fixed`：关闭打包的 `InterfaceAnalyzerMover.get_interface_dG()` | 固定双链构象的 `xyz`、同一评分配置的 `weights` |
| G1 | `rmsd_fixed`：`RMSDMetric.calculate()`，固定映射且不叠合 | 待比较结构的 `xyz`；参考结构固定 |
| B1 | `binder_score`：`TotalEnergyMetric` + 固定 `ChainSelector` | 固定复合物结构的 `weights`；坐标导数列为本轮暂缓 |

四项均需原生正向、上述活动输入的 JVP/VJP 和公开示例。E1、E2 必须有真实坐标导数，
不能只实现权重导数就宣布任务完成。B1 不要求本轮解决残基选择后的坐标梯度，
但请求该方向时必须明确报未支持，不得把整个复合物梯度截取后冒充。

第一轮仅支持普通非对称双链蛋白、固定标准氨基酸序列及全原子映射即可。
坐标用 Å，能量用 Rosetta energy units（REU），实数双精度；说明权重与坐标梯度单位。
固定原子类型、氢原子、质子化状态、链/残基选择、拓扑和评分选项。
不对文件路径、序列字符串、补氢/结构修复、离散索引求导。

## 原生语义与实现路线

1. **先做最小环境与梯度探针。** 在分配到的主机上使用独立环境，核实 PyRosetta
   版本、Rosetta revision、Python、ChainRules、评分配置。优先用已有或预编译包，
   不编译整个 Rosetta，不下载设计模型权重。依赖/授权不足应报告确切错误，不伪造验证。
2. **复用原生导数。** 优先调查 `core.optimization.CartesianMinimizerMap`、
   `CartesianMultifunc.dfunc` 及相应初始化/清理顺序；
   [绑定文档](https://graylab.jhu.edu/PyRosetta.documentation/pyrosetta.rosetta.core.optimization.html)
   不是当前安装可调用的证明。原生梯度无法取得时写出最小复现并报告阻碍，
   不能改用有限差分、假梯度或重写力场凑齐验收。
3. **保留评分设置。** 两项目使用 `get_fa_scorefxn()`，初始化含
   `-corrections::beta_nov16 true`。复现并记录实际非零权重与选项；不得静默换成
   `ref2015`，也不得为跑通梯度删掉原评分中的项。首轮权重活动集固定为选定的
   已启用项，核实原生能量项可用于权重导数，不把未计算的缓存零值当真。
4. **E2 明确是 no-repack 版本。** 两项目原流程都启用了 `set_pack_separated(True)`；
   本入口显式关闭 `pack_input` 和 `pack_separated`，关闭无关随机统计，固定 A/B 分离方式。
   正向必须调用原生 InterfaceAnalyzer，梯度对应其实际能量差和分离变换；
   不以 `dG_cross` 或任意孤立链能量差替换原值。请求打包模式的 AD 时明确拒绝。
   此入口不宣称等价于原项目启用 repack 的完整 `score_interface`。
5. **B1 保留残基能量分配。** 原生 `TotalEnergyMetric` 使用选中残基的
   `PerResidueEnergyMetric` 汇总，并涉及氢键能量分解。不得换成孤立 binder 打分。
   权重导数也需与这个原生指标独立对照，而不是复用不匹配的总能量缓存。
6. **G1 固定映射。** 显式设置无叠合、匹配的重原子范围；原值取原生 RMSDMetric，
   可在配套包中写解析导数。零 RMSD 处显式报告不可微；不能偷偷加 epsilon 改变原值。
   如另提供平方 RMSD，需单独命名和测试。不得在扰动后重新挑原子或改变对应关系。
7. **保留精度与可复用状态。** 对舍入前的原生值注册规则，PDB 仅用于初始装载，
   不在梯度路径中反复写 PDB。使用内部 Pose 副本，保存 pullback 所需状态；
   调用方后续改坐标或权重不得破坏已返回的 pullback。检查坐标/自由度映射及约束设置。
8. **只做加法。** 不 monkey-patch 上游，不用 JAX/PyTorch 重写 Rosetta，不复制整套
   力场计算。有限差分仅存在于测试 oracle；不支持的输入明确报错。

原生行为参考：[InterfaceAnalyzer](https://docs.rosettacommons.org/docs/latest/application_documentation/analysis/interface-analyzer)、
[TotalEnergyMetric 源码](https://github.com/RosettaCommons/rosetta/blob/de92a3c0dea8a010d372a22025e3e50bd4e2f33f/source/src/core/simple_metrics/metrics/TotalEnergyMetric.cc)、
[RMSDMetric](https://docs.rosettacommons.org/docs/latest/scripting_documentation/RosettaScripts/SimpleMetrics/simple_metric_pages/RMSDMetric)。

## 本轮不做

- `FastRelax.apply()` 的输入输出求导、最优构象隐式微分、rotamer 打包/设计、序列梯度。
- 自动结构对齐的导数、扭转角接口、高阶导数、多链/对称/膜蛋白/非标准残基扩展。
- SASA、shape complementarity、packstat、SAP 的导数，以及接触数、氢键计数、
  buried-unsatisfied H-bond、LayerSelector、DSSP 和疏水斑块等离散筛选的梯度。
- Germinal 多次 relax 的随机路径、`argmin` 选结构、通过/失败判定及舍入的导数。
- 完整 AlphaFold / ProteinMPNN / AbMPNN 设计流程、额外主机或 GPU 计算。

以上只需在支持表列明，不必为了“覆盖”再包装全部正向 API。FastRelax 可以作为
不求导的预处理，或直接采用预先准备的结构；不能声称对松弛前坐标给出了完整梯度。

## 交付布局

- `rosetta_ad/`：独立可安装配套包，内含 `pyproject.toml`、实现代码、
  `SPEC.md`、`SUPPORT.md`、`requirements.md`。
- `tests/`、`examples/`、`evidence/`：真实测试、两个轻量兼容示例及可复核日志。
- 根目录 `README.md`、`.gitignore` 等常规文件。

与其他任务的整仓快照模板不同，本任务不把整个 Rosetta、数据库或 PyRosetta wheel
提交进产出仓库。依赖单独安装，参考源码放在交付仓库之外并保持只读；
`requirements.md` 记录来源、精确版本、安装命令、原生源码对应关系及 fixture 来源/校验和。
规范仓、虚拟环境、模型权重、缓存和凭据均不得入库。测试结构只收录有明确来源且
可按其条件使用的最小数据；不确定时提供获取方法，不擅自镜像完整上游。

## 最低验收标准

1. **先 Spec。** 实现前写清 E1/E2/G1/B1 的签名、活动输入、单位、原生对应关系、
   原子映射与误差标准；支持表逐项区分已验证、失败、未运行和明确暂缓。
2. **真实原生值。** 四项均与同配置原生 API 对照，不用硬编码、模拟对象或替代力场。
   建议初始标准：原值 `atol=1e-8, rtol=1e-8`；若版本有实证偏差，先记录原因再定标准。
3. **真实导数。** 对各必需活动输入做多步长中心差分方向检查，并检查 JVP/VJP 对偶、
   零方向、活动输入裁剪、pullback 重复使用及状态隔离。建议导数初始标准
   `atol=1e-4, rtol=1e-3`，接近零的导数使用绝对误差；报告步长扫描和最坏误差。
   原生梯度调用自身不算独立 oracle，不得只测零导数或极小点。
4. **错误边界。** 覆盖缺失链、形状/原子映射错误、非法权重项、G1 零 RMSD、
   B1 坐标导数和 E2 打包模式请求。不得把缺 PyRosetta 导致的全 skip 记为通过。
5. **两个轻量用法。** 提供 BindCraft 风格的界面评分示例、Germinal 风格的
   binder 能量/RMSD 示例；可共用一个有来源的双链蛋白 fixture，但必须记录
   来源、链/原子映射及与各项目调用点的对应。不要求运行整个原项目。
   至少展示一次通过公开梯度接口、配合小步长/回溯，使一个明确选定的连续目标下降；
   比较同配置原生值，记录前后分数、梯度范数和耗时，不将其解释为真实结合能力提升。
6. **安装与报告。** 全新环境单独安装同版 PyRosetta、ChainRules 及构建出的配套包，
   在源码目录之外运行公开接口 smoke test。保存确切命令、环境、测试总数/通过/失败/
   跳过数、退出码和误差；E1/E2/G1/B1 的必需部分全部验证后才可 PASS。
   只有文档、权重导数或模拟测试不能 PASS。不能完成时交付真实部分结果和阻碍证据。

后续 commit/push 与评审按 runner 已分配的目标仓库和工作单执行；不得扩大发布范围。
