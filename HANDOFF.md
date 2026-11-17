# 两步选段条件检验：交接不变量说明

本说明交接 SELECTIVE.md 新增能力的不变量，供复核与维护对照。实现见
selection/event.py（事件生产）、inference/selective.py（条件集合与概率）、
delivery/selective.py（门面协调）、archive 与 delivery 的既有扩展点。

## 父链与身份

- 新父链：selective_report → selection → analysis → task → revision。
- selection 的 parent_id 是 analysis_id；selective_report 的 parent_id 是 selection_id。
- 关联键：selection 按 analysis_id 唯一；selective_report 按 (selection_id, left_leaf) 唯一。
  重复调用复用原成果 ID；更正、对象修改、关闭重开均不改变旧事件与报告。

## 事件语义（冻结即事实）

- 事件固定：固定输入值、请求参数、最终叶段、两步各自的有序胜出者及该步全部合法
  候选（按字典序）。第一步决定第二步候选资格；不固定任何候选对比的正负号。
- 检验只根据冻结事件求条件集合 S，不把当前数据上的点值分段重新当作事件。

## 条件集合 S 的精确性

- 沿直线 y(z)=u+ηz/q，每个候选增益是 z 的有理系数二次多项式；胜出条件逐候选
  给出 D(z)>0（字典序更早的竞争者，严格）或 D(z)≥0（更晚，非严格）。
- S 是这些约束的交集，按全部临界根切分并逐区间认证；孤立点、相切边界、开闭端
  全部如实保留；不固定增益符号、不丢分量、不取凸包。
- 端点表示：有理数为 Fraction；无理端点为 {"poly": (a,b,c), "root": j}，a,b,c
  互质且 a>0，判别式为正非平方，j=0 小根、1 大根。可约根必须回到 Fraction。
- support 为按下端排序、无重叠的最大连通分量；无穷端用 None 且不闭；孤立点是
  两端相等且均闭的分量。

## 概率与精度

- 误差模型 Z~N(0, v)，v=σ²q，σ² 为父任务固定已知方差。
- p = P(|Z|≥|z₀| 且 Z∈S) / P(Z∈S)。条件质量 < 1e-8 抛 ValueError 且不发布；
  ≥ 1e-8 时 p 的绝对误差 ≤ 1e-7。单点无正态质量但仍在 S 中表示。

## 读取、发布与核验

- read_result 只解码并核对固定父链与结构算术关系（z=ηᵀy、v=σ²q、事件重放一致），
  不重新选择、不求 S、不积分。
- 新成果沿用 fault_hook 的 before_insert / after_insert / before_commit 边界，
  kind 为 selection、selective_report；失败整体回滚，可重试，不留半成品。
- export_report 对 selective_report 产出 version=2 自足包（revision、task、
  analysis、selection、report 五对象，digests 全覆盖）；核验器仅用包内资料重算
  选择事件、S 与 p，不打开数据库。V1 包结构与行为不变。

## 核验入口

- python3.11 -B selective_examples.py --verify-all：全部原 unittest 回归 +
  两个固定样例的端到端联动（发布失败回滚、更正后重开）+ 独立核账。
- 独立核账不依赖生产求解器自证：手工推导的合成约束区间预言、独立候选枚举、
  有理探针（参考贪心重跑）、Simpson 独立积分；覆盖全叶竞争、无穷尾、恒等比较、
  相切根、零增益平局及零条件质量拒绝。
- python3.11 -B selective_examples.py --demo：真实冻结事件与条件报告，
  含断开集合、代数端点及更正后重开旧成果。
