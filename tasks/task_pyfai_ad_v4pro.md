<!-- provenance: from-scratch task book (not a GitLab issue), authored 2026-09-03 -->
# 任务：为 pyFAI 增加自动微分（AD）能力

## 目标软件

上游仓库：`https://github.com/silx-kit/pyFAI`（同步辐射粉末/面探测器衍射数据处理库）。
本项目要交付的是：一个与上游分开安装的 sidecar 包，为 pyFAI 中适合求导的
公共 API 提供统一 AD 接口（JVP / VJP / 梯度），并给出可复查的验收证据。

## 权威规范（私有仓 `https://github.com/shindo687/ad-specs`，必须遵守，冲突时以它们为准）

先把规范仓 shallow 克隆到**本仓库之外**的临时位置研读（如 `../ad-specs`），
里面有两份权威文档：

- `AD_AGENT_EXECUTION_WORKFLOW.md` —— 执行流程与 9 条强制规则（先通读）
- `ad-rules/` —— AD 接口与规则规范（按它定义接口、命名与验收方式，先读其中 README/文档）

规范仓只读研读；不要把规范仓的内容提交进本仓库。

## 目录硬规则（reviewer 会逐条核对，违反即 FAIL）

1. 本仓库根目录下只允许两个内容树：
   - `upstream/` —— 上游 pyFAI 的只读快照。导入方式：shallow 克隆
     `git clone --depth 1 https://github.com/silx-kit/pyFAI`，**删除克隆目录里的
     `.git`**，把其中全部文件放入 `upstream/`；在 `pyfai_ad/requirements.md`
     里记录源 commit 号、克隆时间与删除 .git 的事实。
   - `pyfai_ad/` —— 你的 sidecar 包；新代码只能写在这里和 `tests/`。
   - 另有 `tests/`、`README.md`、`.gitignore` 等常规交付文件。
2. `upstream/` 的全部文件只允许在**单独一个“导入快照”commit** 里添加；
   其余任何 commit 都不得改动 `upstream/` 下任何一行。
3. 原始软件与新代码必须分处两个目录，绝不把新代码或修改写进 `upstream/`。

## 实现要求（摘要；细节以权威规范为准）

- 只做加法：原函数是数值结果的唯一来源，AD 层只调用原函数并补充导数规则，
  不复制、不重写整套原计算。
- 统一接口：默认用 ChainRules 注册/暴露 `jvp`、`vjp`、`grad`、`value_and_grad`。
- 不得为 AD 用 JAX / PyTorch 重写上游底层实现。
- 先公共 API 后工作流：遍历目标 API、确定 AD 范围，先写实现规格说明
  （`pyfai_ad/spec.md`），再实现；不能拿少量示例工作流冒充完整范围。
- 有限差分 / 复步长只允许作为测试基准（oracle）；正式规则缺失时必须明确
  报错或声明未支持，不得悄悄地用数值差分冒充已实现的 AD。
- 所有“完成”声明都要附：文件位置、环境、命令、测试数量、通过/失败数、
  误差阈值、仍未覆盖的接口清单。

## 最低验收标准（reviewer 将逐条核对，每一条都要有证据）

1. `upstream/` 与“导入快照”commit 中的内容逐字节一致：`git diff
   导入快照提交的 upstream -- HEAD 的 upstream` 为空。
2. `tests/` 全部测试真实运行过：日志里有确切命令、数量与通过数，退出码 0；
   “测试没跑”直接判 FAIL。
3. 每个对外注册的 AD 接口都有至少一个 oracle 对照测试（有限差分/复步长/解析结果）。
4. 全新 venv 里 `pip install -e pyfai_ad` 之后，公开接口可导入、一个真实工作流
   示例可运行，且不依赖源码目录内部路径。
5. 仓库干净：无 `__pycache__`、`*.pyc`、凭据、缓存文件入库；`git status` 干净。

## 注意

- 这是真实科学研究任务，规模远大于玩具示例：先读上游的公开 API 与文档再定范围，
  时间是几分钟到几小时级别都不要跳步。
- 遇到“必须修改上游源码 / 改变原公共 API / 改变数据结构”的情况：停下来，
  把问题写进 evidence 并判 BLOCKED，不要自行决定改上游。