# 带材双站随机化复核台

带材厂甲、乙线按同批换位签验收样段。站端核对指定修订在一次实际换位下的受检配额和厚度差，并发行固定证据。分析员在关闭两站库后，用指定的两份实收件签报。夜班按报告号查看当时用于复查判断的原定稿。

## 运行

需要 Python 3.11 和标准库 SQLite。从项目根目录执行回归和演示。

```sh
python3 -B check_project.py
python3 -B demo.py
```

平台在物化时提供 `check_project.py`。直接运行同一完整 unittest 套件可用 `python3 -B -m unittest discover -s tests -t . -v`。演示从 `examples/` 装入有限规程和原测，在临时目录建立两站库和一个中心库，关闭站库后签报，再重开中心按号领取。

## 一天的工作流程

1. 试验员把同一规程登记在两个站库。规程固定试验号、角色顺序、公共签与局部规则。
2. 现场将带出处的各组测量导入本站库，形成单站首版。勘误按显式前版替换指定测量组，新旧修订均可核账。
3. 现场选择一次完整换位，核对准入、实际样段数、有符号厚度差和逐组出处。
4. 发行指定修订并固定发行号，保存可重取的 V1 站件。
5. 中心点收校验后的站件，将来件正文和实收首执共同提交。同一合法件可重取首执。
6. 站库关闭后，分析员用有序双实收身份、总配额闭区间和超限阈值申请签报。
7. 中心计算合格次数和超限次数，共同提交原请求、定稿和报告首执。
8. 夜班通过报告号领取原定稿、父件及首执。源端勘误、另发新报告和中心重开均保留原记录。

## Python 接口

`storage.open_database(path)` 提供连接上下文。每个站库连接上使用 `measure.revisions.RevisionStore(db)` 和 `issue.register.IssueRegister(db)`，通过 `RevisionStore.registry` 访问该站的规程库。在中心连接上使用 `intake.archive.IntakeArchive(db)` 和 `report.journal.ReportJournal(db)`。各库初始化创建缺失结构。写接口管理独立事务，调用时连接须处于空闲事务状态。同一个业务入口组合的中心存储对象或站存储对象须使用同一个连接。

| 入口 | 输入和返回 |
| --- | --- |
| `design.registry.register_protocol` | `(registry, trial_id, roles, public_draws, private_draws=None, local_rules=None)`，返回固定 `Protocol`。`roles` 是有序双角色，私有签和局部规则按角色提供。 |
| `measure.imports.record_revision` | `(store, RevisionInput(trial_id, role, rows, parent_id=None))`，返回 `MeasurementRevision`。出处中 `record` 与 `segment` 的组合键定位测量组。 |
| `measure.local_review.review_station` | `(store, revision_id, assignment)`，返回 `StationReview`，包含 `allowed`、`totals.quota`、`totals.effect` 和逐组 `totals.contributions`。 |
| `issue.freeze.freeze_station` | `(revisions, issues, revision_id, issue_id)`，返回固定站件字节。已登记的同号同修订可重取。 |
| `intake.receive.receive_station` | `(archive, wire)`，返回中心的 `StationReceipt`。`archive.get_receipt(id)` 取首执，`archive.get_station(id)` 取首执、站件和验证后的正文。 |
| `report.publish.publish_report` | `(archive, journal, receipt_ids, quota_min, quota_max, threshold, *, before_commit=None)`，返回 `ReportRecord` 和 `ReportReceipt`。测试可传入无参数的 `before_commit` 拒写函数，使尚未提交的本次写入撤销。 |
| `report.history.get_report` | `(archive, journal, report_id)`，返回 `HistoricalReport` 的原定稿、请求顺序下的两件父件及首执，未知报告号得到 `None`。 |

`registry.get_protocol(trial_id)`、`store.get_revision(revision_id)` 与 `issues.get_issue(issue_id)` 分别用于源端追溯。修订号是站库本地身份。发行号供中心去重，需在中心范围内唯一。实收号和报告号由各自的中心库分配。两类首执的 token 是持久保存的凭据值，不参与核算。

## 规程和输入

每站最多六个二元签，其中公共签最多三个。公共签清单按名称固定，同名公共签在同批各站使用同一个取值。私有签只在本站识别，所以两站私有签即使同名也各自取值。`assignment` 必须恰好覆盖本站签名，取值为整数 `0` 或 `1`。一条局部规则的 `when` 是部分取值匹配，匹配时执行闭区间 `quota_min` 至 `quota_max`，或使用 `forbid: true` 排除整组。省略上限表示无上界，空 `when` 对每组分配生效。核账返回实际贡献和准入结论。

一行测量由 `source`、`draw` 和两个依次对应取值 `0`、`1` 的 `choices` 构成。每个取值有 `treated`、`control` 和非负整数 `quota`。样例以微米记读数，按受检减对照形成有符号效应。读数和阈值支持整数、`Fraction` 和整数或分数文本。原测组按出处排序，重复出处或未知签拒绝整批。每试验每角色可登记一个首版。勘误引用同规程同角色的前版，替换该前版中存在的出处键，保留前版其余记录。

## 站件与条件样本

V1 站件是规范 JSON 字节，外封带试验、角色、发行号、规程指纹、冻结修订号和内容指纹。内容指纹覆盖身份和正文，用于检验传输内容一致性。规程有序角色、规范公共签名、本站私有签数以及有序计数条目在正文内。每条计数保留公共取值、实际局部配额、有理效应和合规私有分配重数。按公共取值可缺省没有合规分配的条目。原测、样段编号、来源字段和私有签原名保存在站库。

中心按同一公共取值组合两个站件，每一对计数相乘。通过本站规则的分配还需满足请求的整批配额闭区间，才计入合格数。两站效应和大于或等于阈值的合格分配计入尾部。合格次数大于零时状态为 `calculated`，概率为 `Fraction(尾部次数, 合格次数)`。合格次数为零时状态为 `no_eligible_allocations`，概率为 `None`。计算采用有限枚举与精确算术。

样例甲站配额与效应为 U，乙站配额为私有签 V，效应为 1−U。配额为 [0,1]、阈值为 2 时只有 (U,V) 为 (0,0)、(0,1)、(1,0) 的三次分配合格，尾部为零。乙站勘误为效应 U 后，(1,0) 恰好达到阈值，尾概率为 1/3。配额区间 [3,3] 得到无合格分配。

非法字段、冲突定义、无效分配及跨试验或错位父件以 `ValueError` 拒绝。合法格式但未知的试验、修订和实收身份以 `KeyError` 拒绝。事务内的拒写或 SQLite 错误传播给调用方，本次未提交记录一起回滚。历史领取读取持久定稿和指定父件。

## 回归覆盖

`tests/test_measure.py` 核对原测批次、局部规则、规程固定、方向和指定前版勘误。`tests/test_exchange.py` 核对站件冻结、分签正文、原首执复投、同号冲突及坏来件拒收。`tests/test_report.py` 从固定原测独立枚举合格分配，核对断源签报、资格筛选、精确边界、重数、错件和拒写回滚。`tests/test_history.py` 核对勘误后按号领取、重开持久状态和未知报告号。
