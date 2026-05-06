# macro_upgrade_v1 — 宏观层升级任务

> 创建日期：2026-05-06  
> 依赖文档：`specs/finance/current_system_v1.md` § 5（宏观指标）§ 8（L-04, L-05）  
> 状态：**待确认**

---

## 背景 & 问题

当前宏观系统（`macro_scanner.py` + `regime.py` + `cross_asset.py`）存在两个核心局限：

**L-04**：无欧洲市场扫描  
**L-05**：宏观信号以异动（单日大幅波动）为主，缺乏趋势层（MA、跨指标关系）

具体表现：
- `regime.py` 只用 3 个因子（VIX、SPY-MA、QQQ-SPY 价差），状态分辨率低
- `macro_scanner.py` 的 `scan_unusual()` 检测单日 % 变化，无法识别多日趋势拐点
- 有 US10Y（10年期）但无 2Y，无法计算收益率曲线斜率（2Y-10Y），错过衰退预警
- DXY 趋势反转对持仓（WLD、EM 资产）有直接影响，但无体系化跟踪
- 无美联储/CPI 等事件日历，宏观事件前后无特殊处理逻辑

---

## 升级目标

以增量方式扩展现有系统，不重构已有模块。分 3 个独立子任务，每个可独立执行。

---

## 子任务 M-1：增强 Regime 分类器

### 当前状态（`engine/regime.py`）
3 因子，5 分制输出（risk_on / caution / risk_off）：
```
VIX level   (+2 / +1 / 0 / -2 / -3)
SPY vs MA   (+2 / +1 / -2)
QQQ-SPY 5日 (+1 / -1)
```

### 目标
新增 3 个因子，使 regime 分辨率更高，输出增加"滞胀"和"宽松重启"两种状态：

| 新增因子 | 数据源 | 逻辑 |
|---------|--------|------|
| US10Y 趋势 | ^TNX（已有）| 10Y > MA20 且上行 → 加息预期 → 扣分 |
| 2Y-10Y 利差 | ^IRX（新增）| 利差 < 0（倒挂）→ 衰退预警 → 扣分 |
| Gold vs SPY | GC=F（已有）| Gold 5日跑赢 SPY ≥5% → 避险情绪 → 扣分 |

**新增 regime 标签**：

| 得分 | 旧标签 | 新标签 |
|------|--------|--------|
| 8–10 | 风险偏好 🟢 | 风险偏好 🟢（不变）|
| 6–7 | 风险偏好 🟢 | 宽松重启 🔵（新）|
| 4–5 | 谨慎观望 🟡 | 谨慎观望 🟡（不变）|
| 2–3 | 规避风险 🔴 | 滞胀警戒 🟠（新）|
| 0–1 | 规避风险 🔴 | 规避风险 🔴（不变）|

### 影响文件
- `engine/regime.py` — 增加 3 个因子和新标签（主要修改）
- `scheduler.py` — `_macro_check()` 传参加 `^IRX` 历史（小改）
- `config.yaml` — 无需修改

### 实现步骤
1. 在 `scheduler.py` 的 `_macro_check()` 中加 `"^IRX"` 到 `get_history()` 调用
2. 在 `regime.py` 的 `classify_regime()` 中新增 3 个因子评分逻辑
3. 将 5 档标签替换为 5 档新标签

### 验收标准
- `classify_regime()` 返回新增字段 `yield_curve_note`、`gold_note`
- Telegram 宏观快照中可见 2Y-10Y 利差数值
- 不影响现有 `daily_regime` 推送频率和格式

---

## 子任务 M-2：宏观趋势层（MA 跟踪）

### 当前状态
`macro_scanner.py` 的 `scan_unusual()` 仅检测：单日涨跌幅是否超过阈值（异动）

### 目标
为以下 5 个宏观指标新增 MA 趋势跟踪，检测趋势拐点（而非单日异动）：

| 指标 | 关注逻辑 |
|------|---------|
| DXY（DX-Y.NYB）| 上穿/跌破 MA20 → 对 WLD / 大宗商品有直接影响 |
| Gold（GC=F）| 突破历史高点、跌破 MA50 |
| US10Y（^TNX）| 突破 4.5% / 跌破 4.0% 关键位 |
| VIX | 跌破 15（低波动）/ 突破 20（警戒）/ 突破 30（恐慌）|
| WTI（CL=F）| 跌破 MA50，能源板块压力 |

实现方式：在 `macro_scanner.py` 新增 `scan_trend()` 方法，独立于现有 `scan_unusual()`，避免干扰。

```python
# 新增方法签名（不修改已有方法）
def scan_trend(self, snapshot: dict) -> list[dict]:
    """检测宏观指标 MA 趋势拐点，返回与 scan_unusual 相同格式的 alert 列表"""
    ...
```

### 影响文件
- `scanner/macro_scanner.py` — 新增 `scan_trend()` 方法（增量）
- `scheduler.py` — `_macro_scan()` 中调用 `scan_trend()`（小改）

### 实现步骤
1. `macro_scanner.py` 中 `snapshot()` 已获取 5 日 MA，需补充 20/50 日 MA
2. 新增 `scan_trend()` 方法，遍历 5 个关键指标检测 MA 穿越
3. 在 `_macro_scan()` 中追加 `scan_trend()` 结果，走相同的 throttle 逻辑

### 验收标准
- DXY 上穿 MA20 时触发 Telegram 提醒，格式与现有宏观提醒一致
- 不影响 `scan_unusual()` 的现有输出

---

## 子任务 M-3：2Y-10Y 收益率曲线监控

### 当前状态
宏观 Universe 有 `^TNX`（US10Y），无 `^IRX`（US3M） / 无 2 年期利率

> **注意**：yfinance 中无直接的 US2Y ticker；可用 `^IRX`（13-week T-Bill）近似短端，或用 `^TYX`（30Y） vs `^TNX` 做曲线斜率。

### 目标
新增收益率曲线斜率跟踪，当出现倒挂或显著陡峭化时推送提醒。

**实现选择**（推荐方案 B）：

| 方案 | Ticker | 说明 |
|------|--------|------|
| A | `^IRX`（3M T-Bill）vs `^TNX`（10Y）| 经典衰退指标，但 3M 不如 2Y 标准 |
| **B** | `^FVX`（5Y）vs `^TNX`（10Y）| yfinance 可靠，5-10Y 利差也是常用指标 |
| C | FRED API | 最准确，但需额外依赖 |

推荐 B 方案，无需新增依赖，ticker 已在 yfinance 可用。

### 影响文件
- `scanner/macro_scanner.py` — `RATES_VOL` 字典加 `^FVX`，`scan_trend()` 加利差逻辑
- `engine/regime.py` — M-1 中一并处理

### 验收标准
- 利差 < 0 时 Telegram 推送 "⚠️ 收益率曲线倒挂"
- `macro_snapshot` 播报中新增利差数值行

---

## 执行顺序建议

```
M-1（Regime 增强）→ M-3（收益率曲线）→ M-2（趋势层）
```

M-1 和 M-3 共享 `^IRX`/`^FVX` 数据，可以一次拉取，建议先做。  
M-2 改动最小，但需 M-1 完成后再做（复用 snapshot 中的 MA 数据）。

---

## 进度追踪

- [x] M-1：Regime 分类器增强（2026-05-06）
  - [x] `^TNX`、`^FVX`、`GC=F` 加入 scheduler 拉取
  - [x] `regime.py` 新增 3 因子（US10Y 趋势、5Y-10Y 利差、Gold vs SPY）
  - [x] 5 档标签更新（新增宽松重启 🔵 / 滞胀警戒 🟠）
  - [x] Telegram 格式验证（yield_curve_note、gold_note 字段接入）
- [x] M-2：宏观趋势层（2026-05-06）
  - [x] `scan_trend()` 方法实现（DXY/Gold/US10Y/VIX/WTI）
  - [x] `_macro_scan()` 调用接入（unusual + trend 双轨）
  - [x] 双语 + 图标格式：`format_macro_alert()` 更新，`format_trend_alert()` 新增
- [x] M-3：收益率曲线监控（2026-05-06）
  - [x] `^FVX` 加入 `RATES_VOL` Universe
  - [x] `scan_trend()` 新增 5Y-10Y 倒挂检测（fresh inversion 触发告警）
  - [x] `format_macro_snapshot()` Rates 区块新增利差行

---

## 涉及文件汇总

| 文件 | 修改类型 | 子任务 |
|------|---------|--------|
| `engine/regime.py` | 增量修改（新增因子） | M-1 |
| `scanner/macro_scanner.py` | 增量修改（新增方法）| M-2, M-3 |
| `scheduler.py` | 小改（新增 ticker 到拉取列表）| M-1, M-3 |
| `config.yaml` | 无需修改 | — |
| `alerts/telegram_alert.py` | **不修改** | — |
