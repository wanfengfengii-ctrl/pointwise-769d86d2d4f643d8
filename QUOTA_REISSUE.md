# 开检前的配额改签

夜班先签两站共用的备样票。开检前，质控员可能调整总配额。中心须沿用原来两份实收件，重新给出符合新版抽样要求的票。两站收到各自的票段后，按原发行兑现分配。旧尾报的规则见 README.md。

## 站端与实收

- `issue.freeze.freeze_executable_station(revisions, issues, revision_id, issue_id)` 针对确切冻结修订返回新版站件字节。同号同修订的新版发行返回原字节。同发行号跨版本或跨修订的冲突拒办。原 `freeze_station` 仍按原接口发行 V1。
- 新版站件为中心提供每次合规本地分配的可区分身份、公共签取值和实际局部配额。即使公共取值、配额及效应都相同，两个本地分配仍分属不同的可兑现身份。私有签的名称、取值和原测留在本站。票段及来件中记录的顺序不得直接编码私签名或取值。
- 继续使用 `intake.receive.receive_station(archive, wire)` 点收新版站件。同件重投返回原 `StationReceipt`。校验覆盖实际发行身份与正文的指纹，拒收身份冲突、损坏或结构无效的版本正文，包括重复的可执行分配身份和非法的公共签取值或配额。拒收无新增。
- `issue.freeze.redeem_station_ticket(revisions, issues, issue_id, segment)` 只凭本站库独立兑现，返回 `measure.local_review.StationReview`。其 `revision_id`、完整 `assignment`、`allowed` 和 `totals` 均对应票段在这份确切发行上的分配。已知发行收到错角色、其他发行的票段、非法票段或 V1 件均拒办。再次兑现一个合法票段仍得到同一结果。

## 中心调用

| 入口 | 调用方式 |
| --- | --- |
| `report.publish.draw_ticket` | `(archive, journal, receipt_ids, quota_min, quota_max, randbelow, *, before_commit=None)` |
| `report.publish.reissue_ticket` | `(archive, journal, initial_ticket_id, quota_min, quota_max, randbelow, *, before_commit=None)` |
| `report.history.get_ticket` | `(archive, journal, ticket_id)` |

中心对象共用一个连接，站端的 `revisions` 和 `issues` 亦共用一个连接。两个签发入口在站库关闭后仅凭中心数据办理。初抽要求两个新版实收号属于同一规程并按角色顺序排列。用与 V1 相同的整数闭窗约定，只有两站均准入、公共签取值相同且配额之和落窗的完整分配参与。每个完整分配初抽等概率。仍用原规程判准入，勘误另发行。

改签只接受有可执行票段的初票，双件身份由初票给定。新版窗独立于初抽且两窗均有合格分配时，改签在新版合格分配上精确均匀，并使双站原分配同时保留的概率最大。概率以重复整个初抽及改签过程为口径，每次试验使用同一对固定窗口。整票留存要求两站分别兑现出初票的完整原分配。票段的表示与符合上述要求的随机规则由实现选择。

`randbelow(n)` 每次独立均匀返回 `[0,n)` 内的整数，`n` 为正整数。签发使用此回调作为抽取的随机输入。回调返回非法值时报 `ValueError`，回调自身异常向调用方传播，本次无新增。复领已有改签和空总体签发均不调用抽取回调。

两个签发入口返回一个 JSON 兼容字典。历史领取返回相同内容。

| 字段 | 含义 |
| --- | --- |
| `ticket_id` | 正整数票号，初票与改签共用票号空间 |
| `initial_ticket_id` | 初票为 `None`，改签为所用初票号 |
| `parents` | 按规程角色顺序的两个对象，各含 `receipt_id`、`issue_id`、`fingerprint` |
| `quota_min`, `quota_max` | 本票实际办理的闭窗 |
| `segments` | 按父件顺序的两个不透明 JSON 票段，空总体为 `None` |
| `kept` | 初票为 `None`，改签为是否整票留存的布尔值，改签到空总体为 `False` |

每张初票至多有一次已提交的改签，空新版总体的改签也计入。同初票同窗再请求直接返回存值，同初票改窗拒办。定稿、双出处和改签占用一次提交。`before_commit` 与旧尾报的拒写回调用途相同，在写入后、提交前调用。写入失败无本次结果，可重试。中心重开后按号读取存值，后续源站勘误不改变存值。非法、错配、冲突用 `ValueError`，格式合法但未知的站端发行号、实收号或用于改签的初票号用 `KeyError`。有效未知票号的 `get_ticket` 返回 `None`。

## 样例与运行

`examples/quota_reissue.py` 含两组可直接登记的规程和原测，以及可以记录抽取上界的 `ScriptedRandbelow`。运行 `python3 -B -m examples.quota_reissue` 可通过原 V1 链路核对两组固定原测的合格次数和主样例的乙站重数。

主样例中，甲站两签分别增加 0 或 1 段、0 或 2 段，乙站私签两值的配额和效应都为零。固定用旧窗 `[0,1]` 和新版窗 `[1,3]`。四种旧分配各占 1/4，六种新版分配各占 1/6，整票留存率应为 1/3。对独立整数抽取的分支按确切权重核对，允许不同的合法分支顺序和条件替换分布。相同非空窗口必保留，互不相交的非空窗口必替换，空新版总体签无可执行票。

共享签样例中，乙站禁止 `U=1` 同时 `B-gate=1`。`[0,1]` 有三种分配，`[1,1]` 有两种，`[2,2]` 无合格分配。兑现时，两个站点的 `U` 必须相同，禁止分配始终不出票。

用现有 `.pointwise-runtime.json` 交付运行入口。保留原完整回归，`verify` 还须核对抽样和改签分布、票段兑现及错发行拒办、拒写后重办和原票复领，任何核对失败返回非零。`demo` 展示实际初票、关站后改签、中心重开领取及各站独立兑现。入口从项目根目录运行。
