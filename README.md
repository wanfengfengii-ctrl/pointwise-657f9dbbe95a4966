# 离线水质复核归档 V1

Python 3.11 标准库工程，无安装依赖。模拟客户是试验水厂质控组：采样管理员接纳仪器离线 JSON、分析员固定资料并定位变化、复核员取得普通对比和可复算交付包，安排人工复测。结果不直接控制设备。V1 普通报告明确注明未校正选段，不提供选择后推断。

## 一天工作

1. 管理员接收按仪器顺序排列的等间隔浓度行，确认序列及源版本。
2. 整批校验 mg/L 单位、连续 row_no 和精确有理值，合法后一次接纳为不可变修订。
3. 分析员固定修订、正的已知噪声方差、最小叶长和切分次数；实际贪心轨迹无法完成则不建立任务。
4. 全部当前叶段的合法切点按精确平方损失下降竞争，保存有序胜出切分和最终叶段统计。
5. 分析负载与任务关联共同提交，完整结果才对外可读。
6. 复核员指定最终相邻两叶，生成左均值减右均值的普通正态报告。
7. 报告共同提交后导出固定修订、任务、分析和报告；自足核验成功才交付。
8. 管理员用新源版本更正；新任务使用新资料，关闭重开后旧成果仍固定原资料。

## 输入和计算

examples/day.json 是有限仪器样例。每行必须恰含 row_no、value；row_no 从 0 连续递增且等于数组位置，不排序、不补行。批次非空。接受 int、Fraction、有理数字符串；拒绝 float、bool、None、非有限数及零分母。允许负浓度。Fraction 和字符串均按精确值规范化。所有行共享 mg/L，已知噪声方差单位为 (mg/L)^2。

同序列、同源版本、同规范负载重放返回原修订 ID；改变数值或更正父身份抛 ConflictError。更正父必须是同一序列的已有修订，新更正使用新源版本。更正不覆盖旧修订。合法样例的显式重复导入幂等；修改样例后沿用旧版本会冲突。

区间为零基半开 [l,r)，候选为 (l,c,r)，两子叶均满足 min_leaf。增益为左和平方/左长度 + 右和平方/右长度 - 父和平方/父长度。前缀统计、SSE、增益及平局比较均使用 Fraction。每步在全部当前叶间竞争；同增益选 (l,c,r) 字典序最小者。零增益仍切分。V1 不限定 8–40 行、叶长 2 或两次切分；零次切分合法。

标准样例 [1,1,2,2,7,7,9,9]，方差 4、min_leaf=2、splits=2，依次选择 (0,4,8)、(4,6,8)，增益 169/2、4，最终叶均值 3/2、7、9，SSE 为 1、0、0。比较前两叶时系数为四个 1/4、两个 -1/2、两个 0，z=-11/2，系数平方和 3/4，对比方差 3，普通双侧 p 约 0.00149616428974555。

普通概率为 erfc(|z|/sqrt(2*variance))，零对比为 1，极端尾部可下溢为 0。目标绝对误差 1e-12。精确 z、方差和系数保留 Fraction；standard_error 为 40 位 Decimal 平方根的字符串展示，概率为有限 float。普通报告的警示是业务结果的一部分。

## Python API

从项目根目录调用：

```python
from delivery.app import WaterQualityApp

with WaterQualityApp.open("quality.sqlite") as app:
    revision_id = app.put_series(
        "water", "day-1", "mg/L",
        [{"row_no": i, "value": v}
         for i, v in enumerate([1,1,2,2,7,7,9,9])])
    task_id = app.create_analysis(revision_id, 4, 2, 2)
    analysis_id = app.execute_analysis(task_id)
    report_id = app.report_contrast(analysis_id, 0)
    report = app.read_result(report_id)
    package = app.export_report(report_id)
```

六个门面接口的返回值：put_series 返回修订 ID，create_analysis 返回固定任务 ID，execute_analysis 返回分析 ID，report_contrast 返回报告 ID；read_result 返回包含 artifact_id、kind、parent_id、data 的独立嵌套字典，内部统计为 Fraction；export_report 返回 JSON 可编码、自足的版本化包。成功任务和相同父分析/left_leaf 的报告重复调用复用原成果。left_leaf 是最终叶编号，从 0 开始，必须存在右邻。

sampling 拥有修订与重放；selection 拥有点值候选、分段和统计；inference 拥有相邻对比和普通报告；archive 拥有固定任务、编码、发布关联与事务；delivery 装配入口及交付核验。内部不可变 dataclass 与 tuple 不暴露可写存储引用。调用者修改输入或返回对象不改变历史。

未知修订为 sampling.revisions.UnknownRevision；未知任务为 archive.schema.UnknownTask；未知成果为 UnknownResult；损坏编码、摘要或父链为 CorruptArtifact；非法输入或叶编号为 ValueError。异常拒绝本次成果，不重算替代损坏历史。read_result 只解码、核对固定身份及算术一致性，不重新选段或计算概率。导出按固定父链收集资料，核验器使用包内资料重新计算，不打开原数据库，不补用当前修订。

## 运行

所有命令从项目根目录执行。初始化不隐式导入样例、不清空用户资料；重复启动和初始化保持已存资料，未知结构版本明确拒绝。

```sh
python3.11 -B -m unittest discover -s tests -t . -v
python3.11 -B -m delivery.app demo
python3.11 -B -m delivery.app init --db quality.sqlite
python3.11 -B -m delivery.app import --db quality.sqlite examples/day.json
```

导入输出 revision_id。继续使用各命令实际输出的 ID：

```sh
python3.11 -B -m delivery.app create --db quality.sqlite REVISION_ID --noise-variance 4 --min-leaf 2 --splits 2
python3.11 -B -m delivery.app execute --db quality.sqlite TASK_ID
python3.11 -B -m delivery.app report --db quality.sqlite ANALYSIS_ID --left-leaf 0
python3.11 -B -m delivery.app read --db quality.sqlite REPORT_ID
python3.11 -B -m delivery.app export --db quality.sqlite REPORT_ID --out review.json
python3.11 -B -m delivery.app verify-package review.json
```

 demo 在自有临时目录内运行真实导入、分段、普通报告、更正和重开旧包的完整流程，并自动清理。核验成功退出 0，包校验失败退出 1，输入或归档错误退出 2；unittest 失败也返回非零。命令清单见 .pointwise-runtime.json、run-manifest.json，后者的 ID 模板须替换为实际回执。

## 正常回归与发布边界

 tests/reference.py 直接求和及枚举当前候选，独立核对生产前缀统计和选择规则；普通概率另用手算常量和 Simpson 积分核账。原六个测试文件覆盖标准样例、有限序列穷举、大数平移、全叶竞争、零增益平局、真实轨迹不可执行、整批拒绝、规范重放、合法更正、系数和噪声绑定、历史隔离、重复初始化、重开、发布失败回滚重试、父链损坏与 CLI 退出码。

SQLite 成果负载与关联索引在同一 BEGIN IMMEDIATE 事务中提交。WaterQualityApp.open 的可选 fault_hook(stage, kind) 在 before_insert、after_insert、before_commit 调用，kind 为 analysis 或 report；钩子抛异常会回滚本次发布。测试通过真实事务和另一个数据库连接检查提交前不可见，通过独立临时副本检查损坏拒绝。钩子没有成功捷径或替代计算。

公开成果只保存观测输入上的胜出切分与最终叶统计，不保存全部竞争条件或连续条件集合。范围不含在线采样、设备控制、未知方差估计、多变量树、自动剪枝或网页。
