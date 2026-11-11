# M0-T06 NYSE 交易日历与时钟

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | T01 已合并 |
| 阻塞 | T10（冻结时钟 fixture）；M2/M4/M10 大量使用 |
| 分支 | `feat/m0-t06-calendar-clock` |
| 建议规模 | 中 |
| 负责 Agent | _未分配_ |

## 目标
封装 NYSE 交易日历与可替换时钟，按 `CONTRACTS.md §7`。所有"下一交易日 / 是否开盘 / 收盘时间"逻辑今后**只能**经此模块。

## 范围
**包含**
1. `core/calendar.py`：基于 `exchange_calendars` 的 `XNYS`，显式范围 `2020-01-01 ~ 2030-12-31`（超出抛 `CalendarRangeError`）；实现契约中的全部函数与 `Session`。
2. `core/clock.py`：`Clock` 协议、`SystemClock`、`FrozenClock`、`get_clock/set_clock/reset_clock`。`FrozenClock.advance` 可模拟时间流逝。
3. 所有函数严格区分"带时区 datetime"与"date"；传入不带时区的 `datetime` 一律 `ValueError`。
4. 半日市 `close_at = 13:00 ET`；夏令时下 UTC 偏移正确（`close_at` 转 UTC：EDT 为 20:00Z/EST 为 21:00Z，半日市为 17:00Z/18:00Z）。
5. 模块内缓存日历对象（进程内单例），线程安全。

**不包含**：盘前盘后时段、其他交易所。

## 文件所有权
- **拥有**：`backend/app/core/calendar.py`、`backend/app/core/clock.py`
- **新增测试**：`backend/tests/unit/core/test_calendar.py`、`test_clock.py`

## 测试数据要求（重要）
测试中的节假日/半日市期望值**必须由你对照 NYSE 官方休市与提前收盘公告核对后写入**，并在测试文件头注释写明核对来源与日期。下列为协调者提供的待核对参考，**以官方公告为准**，如有出入请在 PR 中指出：
- 休市：2026-01-01、2026-01-19（MLK）、2026-02-16、2026-04-03（耶稣受难日）、2026-05-25、2026-06-19、2026-07-03（独立日顺延）、2026-09-07、2026-11-26（感恩节）、2026-12-25
- 提前收盘（13:00 ET）：2026-11-27、2026-12-24
- 夏令时切换（美国）：2026-03-08（开始）、2026-11-01（结束）
- 同样覆盖 2024、2025 年的全部休市日与半日市（如 2024-07-03、2024-11-29、2024-12-24）

## 验收标准
- [ ] 2024、2025、2026 年每一个休市日 `is_trading_day == False`，每个半日市 `is_half_day == True`（参数化测试，数据已与官方核对）
- [ ] 周末均非交易日；`next_trading_day(周五)` = 下周一（含遇节假日顺延的情形，如 2026-07-02 → 2026-07-06）
- [ ] `previous_trading_day` 与 `next_trading_day` 互为逆运算（属性测试：随机日期范围内，`prev(next(d)) <= d`，且二者结果均为交易日）
- [ ] `get_session` 对非交易日抛 `NotATradingDay`；开收盘时间含正确时区；UTC 转换在夏令时前后均正确（2026-03-06 周五 vs 2026-03-09 周一，收盘 UTC 偏移不同）
- [ ] `is_market_open`：开盘前 1 秒 False、开盘瞬间 True、收盘瞬间 False、半日市 13:00 后 False；不带时区抛 `ValueError`（测试）
- [ ] `trading_days_between` 闭区间、升序、空区间返回空列表、`start > end` 抛 `ValueError`
- [ ] 超出 2020–2030 抛 `CalendarRangeError`
- [ ] `FrozenClock`：`now()` 固定、`advance` 生效、`set_clock/reset_clock` 可替换与恢复；`now()` 必为 UTC 带时区
- [ ] `import-linter` 通过（确认除 `core/calendar.py` 外无人 import `exchange_calendars`）
- [ ] `make check` 全绿；覆盖率 ≥ 95%
