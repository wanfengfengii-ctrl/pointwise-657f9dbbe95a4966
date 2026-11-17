# 两步选段后的条件检验

这是在 README.md 所述完整 V1 上增加的能力。V1 的普通概率仍保留“未校正选段”的含义；本题新增报告才是在实际两步选择事件及干扰分量条件下的显著性结果。采样单位、精确有理输入、修订、错误类型和旧编码均沿用 V1，不修改原测试。

## 业务与入口

新增 WaterQualityApp.freeze_selection(analysis_id) -> selection_id，以及 WaterQualityApp.selective_test(selection_id, left_leaf) -> report_id，均返回持久成果 ID。前者接纳已发布的 analysis，限 8 至 40 行、min_leaf=2、splits=2；其他分析参数仍可通过原接口使用，但调用新增冻结入口时抛 ValueError 且不发布。left_leaf 是最终三叶中相邻两叶的左编号，只接受非布尔整数 0 或 1。

同一 analysis 重复冻结复用同一 selection_id；同一 selection_id、left_leaf 重复检验复用同一 report_id。未知成果或传入错误 kind 抛 archive.schema.UnknownResult，非法参数抛 ValueError，固定父链或编码损坏抛 CorruptArtifact。所有失败均不留下半成品。新成果沿用 fault_hook(stage, kind) 的 before_insert、after_insert、before_commit 边界，kind 分别为 selection、selective_report；失败回滚后可重试。

## 选择事件与计算语义

选择职责生产固定事件，检验职责消费事件。每步候选是当时全部当前叶内满足 min_leaf 的全部 (l,c,r)，不能仅考虑最终相邻叶或只保留胜出候选。增益、零增益执行及 (l,c,r) 字典序平局沿用 README.md。事件固定两步的有序胜出身份，不额外固定各候选线性对比的正负号。冻结事件须可独立解释两步胜出比较；检验根据冻结事件求条件集合，不能把再次运行当前数据上的点值分段当作事件。

令 y 为父分析固定数据，η 为最终指定左叶均值减右叶均值的逐行系数，q=ηᵀη，z₀=ηᵀy，u=y−ηz₀/q。对所有实数 z 定义 y(z)=u+ηz/q。S 恰为相同选择器对 y(z) 产生同一有序胜出序列的全部 z。第一步决定第二步的候选资格，平局时按原字典序决定端点属于哪个事件。不得额外固定增益符号、丢掉分量或取凸包；保留孤立点、相切边界和所有开闭端。允许全量重算、求临界根后逐区间认证及其他满足同一语义的设计，不增加性能要求。

误差模型为独立同方差正态噪声，σ² 是父任务固定的已知方差。返回 z₀、v=σ²q 及 p=P(|Z|≥|z₀|且Z∈S)/P(Z∈S)，其中 Z~N(0,v)。只对条件质量至少 1e-8 的请求要求数值支持，p 的绝对误差不得超过 1e-7；质量不足的请求允许抛 ValueError 且不发布。端点及集合归属须精确，不能用数值容差、网格或浮点根决定它们。单点没有正态质量，但必须在 S 中如实表示。

## 可观察成果

read_result 沿用 V1 的 artifact_id、kind、parent_id、data 外层。事件 kind 为 selection，parent_id 为 analysis_id，其 data 为：
- analysis_id、revision_id：固定父身份。
- request：V1 的 noise_variance、min_leaf、splits 字典；values 为按原行序的 Fraction 元组。
- leaves：最终有序半开叶段 (l,r) 的元组。
- stages：长度二的元组，每项含 winner=(l,c,r) 和 candidates，后者是该步全部合法候选三元组按字典序组成的元组。候选自身也包含胜出者。允许增加解释性字段，但这些公开字段必须存在。

条件报告 kind 为 selective_report，parent_id 为 selection_id，其 data 至少含 selection_id、left_leaf、z、variance、support、p。z 和 variance 为 Fraction；p 为有限 float。support 为按下端排序、无重叠的最大连通分量元组，每项为 lo、hi、lo_closed、hi_closed 字典。lo=None 表示负无穷，hi=None 表示正无穷，相应 closed 必须为 False。有限端为 Fraction 或 {"poly": (a,b,c), "root": j}：后者指 az²+bz+c=0 的第 j 个实根，j=0 为小根、1 为大根；a,b,c 是互质整数，a>0，判别式为正且非平方。可约根必须用 Fraction。孤立点为相等有限端且两端闭。端点表示须支持精确比较，不要求额外公开比较函数。

事件固定输入、噪声、阶段资格与胜出顺序，报告固定事件、叶编号和全部结果。更正源数据、修改输入或返回对象、关闭重开均不改变旧事件及报告。read_result 仅解码与核对固定父链及结构算术关系，不重新选择、求 S 或积分；已存在的重复调用也直接复用成果。

## 自足交付

扩展 export_report(report_id) 与 delivery.verification.verify_export_package，使其同时接纳新报告，旧包结构和行为保持兼容。新包 version=2，顶层为 version、manifest、revision、task、analysis、selection、report。manifest 含 revision_id、task_id、analysis_id、selection_id、report_id、digests；digests 精确覆盖后五个对象的名字，摘要仍按 V1 canonical_json 与 artifact_digest。五个对象使用既有版本化对象编码的扩展；selection 和 report 为对应新 kind 的成果信封。

新包的父链为 report→selection→analysis→task→revision。核验器只使用包内输入重算选择事件、S和p，核对精确部分及公开概率精度，不打开原数据库或借用当前修订。缺失、损坏、错配或计算结果不符返回 valid=False；export_report 对不可核验的包抛 CorruptArtifact。读取不重算的限制不适用于自足包核验。不要求新的网络服务或命令子命令。

## 固定样例和运行

selective_examples.py 是非答案夹具：只提供有限输入、手算预期和调用检查，不提供事件编译、代数求交或条件检验实现。
- disconnected：y=[-3,-3,-3,-3,-3,-3,-1,-1]、σ²=1、left_leaf=1。胜出为 (0,6,8)、(0,2,6)，z₀=-2、v=3/4，S=(-∞,-1/2)∪(1,∞)，p≈0.051535717653935。z=-2 是第二步相切平局，属于 S。只保留观测分量的错误 p≈0.037114119443224，凸包错误 p≈0.020921335337794。
- day：沿用 examples/day.json、σ²=4、left_leaf=0。胜出为 (0,4,8)、(4,6,8)，z₀=-11/2、v=3。设 a、b 为 8z²−68z−289 的小、大根，a≈-3.111215932167728，b≈11.611215932167728，S=(-∞,-10)∪(-7,a]∪[b,∞)，p≈0.019931682837800。-10、-7 的同增益候选字典序更早，均不属于 S。

从项目根目录执行 python3.11 -B selective_examples.py --v1 可核对夹具的 V1 选择、对比和有限有理探针；不要求基线已有新增接口。完成新增能力后，python3.11 -B selective_examples.py --verify-all 运行全部原回归及固定样例、发布失败、更正与磁盘重开联动；python3.11 -B selective_examples.py --demo 展示真实冻结事件及条件报告。扩展夹具中的核验，补充独立短例候选枚举、精确区间及端点核账和独立积分，覆盖全叶竞争、无穷尾、恒等比较、相切根和零增益平局，不把生产求解器与自身比较作为独立核验。交付简短交接不变量说明。

沿用现有 .pointwise-runtime.json 的格式，将 verify 接到包含原回归和新增独立核验的实际入口，demo 接到冻结、检验、更正后重开旧成果的演示。核验失败保持非零退出，原测试逐字保留。
