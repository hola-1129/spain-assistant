# signal_layer_v1 — 信号层优化任务

> 创建日期：2026-05-06  
> 依赖文档：`specs/finance/current_system_v1.md` § 4（信号库）  
> 状态：**待确认**

---

## 背景 & 问题

当前信号层（`signals/momentum.py` + `volatility.py` + `volume.py` + `engine/inflection.py`）共 21 种信号，核心问题是：

- **MACD 只跟踪柱状图过零**（histogram crossing zero），未实现传统的 MACD 线与信号线交叉，后者噪音更少
- **无 RSI 背离检测**：价格创新高但 RSI 未跟进（顶背离），是最可靠的反转预警之一，当前完全缺失
- **成交量层无趋势积累信号**：`volume.py` 只看当日量比，无 OBV（On-Balance Volume）累积趋势，无法识别多日派发/吸筹
- **信号评分与宏观 Regime 脱节**：熊市 Regime（risk_off）下 bullish 信号和牛市 Regime 下使用相同权重，误触发率高

---

## 升级目标

以增量方式新增信号，不修改现有信号逻辑。分 4 个独立子任务。

---

## 子任务 S-1：MACD 信号线交叉

### 当前状态（`signals/momentum.py`）
`_macd_hist()` 返回当日和前日柱状图值，当前只检测**柱状图过零**：
```python
if h_prev < 0 <= h_now:   # macd_golden
elif h_prev > 0 >= h_now: # macd_death
```

### 问题
MACD 柱状图过零是滞后信号；**MACD 线上穿信号线**（传统金叉）出现更早，且假信号更少（尤其在趋势行情中）。

### 目标
新增检测 MACD 线（快线）vs 信号线（慢线）的交叉：

```python
# 新增辅助函数
def _macd_lines(close: pd.Series, fast=12, slow=26, sig=9):
    macd_line   = close.ewm(span=fast).mean() - close.ewm(span=slow).mean()
    signal_line = macd_line.ewm(span=sig).mean()
    return macd_line, signal_line
```

| 新信号 | 触发条件 | 方向 | 建议权重 |
|--------|---------|------|---------|
| `macd_line_cross_up` | MACD 线从下穿越信号线 | bullish | 1.4 |
| `macd_line_cross_down` | MACD 线从上穿越信号线 | bearish | 1.4 |

### 影响文件
- `signals/momentum.py` — 新增 `_macd_lines()` 和 2 个信号检测（增量）
- `engine/inflection.py` — `_WEIGHTS` 加 2 条新权重

### 实现步骤
1. `momentum.py`：新增 `_macd_lines()` 函数
2. `momentum.py`：在 `analyze_momentum()` 现有 MACD 块下方追加新检测
3. `inflection.py`：`_WEIGHTS` 加 `"macd_line_cross_up": 1.4, "macd_line_cross_down": 1.4`

### 验收标准
- 传统 MACD 金叉（线叉）触发 `macd_line_cross_up`，与 `macd_golden`（柱状图叉）可共存
- 单独触发时 score 贡献正确（strength=0.6，score += 1.4×0.6 = 0.84）

---

## 子任务 S-2：RSI 背离检测

### 当前状态
`momentum.py` 检测 RSI 绝对值（超买/超卖）和 RSI 过 50，但**不检测价格与 RSI 的背离**。

### 问题
背离（divergence）是技术分析中最有效的反转信号：
- 顶背离：价格创近期新高，RSI 未创新高 → 动能衰减，下跌概率高
- 底背离：价格创近期新低，RSI 未创新低 → 卖压减弱，反弹概率高

### 目标
在 `analyze_momentum()` 中新增背离检测（看最近 15 个交易日内的摆动高/低点）：

```python
# 伪代码
def _find_divergence(close, rsi_series, lookback=15):
    # 找最近两个价格摆动高点（或低点）
    # 比较对应 RSI 值，检测方向不一致
    ...
```

| 新信号 | 触发条件 | 方向 | 建议权重 |
|--------|---------|------|---------|
| `rsi_divergence_bear` | 价格高点抬升，RSI 高点下降（顶背离）| bearish | 1.6 |
| `rsi_divergence_bull` | 价格低点下降，RSI 低点抬升（底背离）| bullish | 1.6 |

### 影响文件
- `signals/momentum.py` — 新增 `_find_divergence()` 辅助函数 + 2 个信号检测
- `engine/inflection.py` — `_WEIGHTS` 加 2 条新权重

### 实现步骤
1. `momentum.py`：新增 `_find_divergence(close, rsi, lookback=15)` → 返回 `"bull"` / `"bear"` / `None`
2. `momentum.py`：在 RSI 块末尾调用，检测结果追加到 signals
3. `inflection.py`：`_WEIGHTS` 加 `"rsi_divergence_bull": 1.6, "rsi_divergence_bear": 1.6`

### 验收标准
- 顶背离：price[-1] > price_swing_high，rsi[-1] < rsi_swing_high → `rsi_divergence_bear`
- 底背离：price[-1] < price_swing_low，rsi[-1] > rsi_swing_low → `rsi_divergence_bull`
- 背离检测要求价格摆动幅度 ≥ 2%（过滤噪音）

---

## 子任务 S-3：OBV 趋势确认

### 当前状态（`signals/volume.py`）
只看当日量比（`vol_now / vol_avg`），无法识别多日累积走势。

### 问题
单日量比高可能是随机噪音；OBV（On-Balance Volume）通过累积方式反映多日资金进出方向：
- OBV 持续上升但价格横盘 → 吸筹，潜在上攻
- OBV 持续下降但价格横盘 → 派发，潜在下跌

### 目标
新增 `_obv()` 函数，检测 OBV 的 10 日趋势斜率：

```python
def _obv(hist: pd.DataFrame) -> pd.Series:
    direction = hist["Close"].diff().apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
    return (direction * hist["Volume"]).cumsum()
```

| 新信号 | 触发条件 | 方向 | 建议权重 |
|--------|---------|------|---------|
| `obv_rising` | OBV 10日线斜率 > 0 且近期创新高 | bullish | 0.8 |
| `obv_falling` | OBV 10日线斜率 < 0 且近期创新低 | bearish | 0.8 |

仅在 OBV 与价格方向**一致**时触发（排除背离情形，背离由 S-2 处理）。

### 影响文件
- `signals/volume.py` — 新增 `_obv()` 函数 + 2 个信号检测（增量）
- `engine/inflection.py` — `_WEIGHTS` 加 2 条新权重

### 实现步骤
1. `volume.py`：新增 `_obv(hist)` 函数
2. `volume.py`：在 `analyze_volume()` 末尾追加 OBV 趋势检测（需 ≥ 15 日历史）
3. `inflection.py`：`_WEIGHTS` 加 `"obv_rising": 0.8, "obv_falling": 0.8`

### 验收标准
- NVDA 在明显趋势行情中，OBV 信号与价格方向一致
- `obv_rising` / `obv_falling` 不与 `volume_spike` 同时出现（OBV 是多日信号，量比是单日信号，逻辑独立）

---

## 子任务 S-4：Regime 感知评分调整

### 当前状态（`engine/inflection.py`）
`detect_inflection()` 签名：
```python
def detect_inflection(symbol, hist, min_score=2.5) -> Optional[InflectionEvent]:
```
信号权重固定，与宏观 Regime 无关。

### 问题
在 `risk_off` Regime 中，bullish 信号（如 `reclaim_ma50`）可能是反弹陷阱；在 `risk_on` Regime 中，bearish 信号误触发率也更高。权重应随 Regime 动态调整以减少误报。

### 目标
新增可选参数 `regime`，根据 Regime 对信号方向做小幅权重调整：

```python
def detect_inflection(
    symbol: str,
    hist: pd.DataFrame,
    min_score: float = 2.5,
    regime: str = "neutral",   # 新增参数，默认 neutral（兼容现有调用）
) -> Optional[InflectionEvent]:
    ...
    # 计算 score 时对逆势方向信号降权 20%
    _regime_factor = {
        "risk_on":     {"bullish": 1.0, "bearish": 0.8},
        "recovery":    {"bullish": 1.0, "bearish": 0.9},
        "caution":     {"bullish": 1.0, "bearish": 1.0},
        "stagflation": {"bullish": 0.85, "bearish": 1.0},
        "risk_off":    {"bullish": 0.8,  "bearish": 1.0},
    }.get(regime, {"bullish": 1.0, "bearish": 1.0})
```

### 影响文件
- `engine/inflection.py` — `detect_inflection()` 新增 `regime` 参数（默认值保持兼容）
- `scheduler.py` — `_check_inflection()` 调用处传入当前 `regime_result["risk_level"]`

### 实现步骤
1. `inflection.py`：新增 `regime` 参数和 `_regime_factor` 字典
2. `inflection.py`：score 计算改为 `weight * strength * _regime_factor[s.direction]`
3. `scheduler.py`：`_macro_check()` 中缓存 `regime_result`，供后续 `_check_inflection()` 读取

### 验收标准
- `risk_off` Regime 下，bullish 信号单条得分乘以 0.8（日志可验证）
- 现有不传 `regime` 参数的调用行为不变（默认 neutral = 无调整）
- 不影响现有 Telegram 消息格式

---

## 执行顺序建议

```
S-1（MACD 线叉）→ S-3（OBV）→ S-2（RSI 背离）→ S-4（Regime 感知）
```

- S-1、S-3 改动最小，新增独立函数，无依赖关系
- S-2 需实现摆动点检测，复杂度最高，单独执行
- S-4 需依赖 S-1~S-3 完成后统一验证 score 计算

---

## 进度追踪

- [x] S-1：MACD 信号线交叉（2026-05-06）
  - [x] `_macd_lines()` 实现
  - [x] `macd_line_cross_up / down` 检测
  - [x] `inflection.py` 权重更新（1.4）
- [x] S-2：RSI 背离检测（2026-05-06）
  - [x] `_rsi_series()` + `_find_divergence()` 实现（含 NaN 防护）
  - [x] `rsi_divergence_bull / bear` 检测（lookback=20，幅度阈值 2%）
  - [x] `inflection.py` 权重更新（1.6）
- [ ] S-3：OBV 趋势确认
  - [ ] `_obv()` 实现
  - [ ] `obv_rising / falling` 检测
  - [ ] `inflection.py` 权重更新
- [ ] S-4：Regime 感知评分
  - [ ] `detect_inflection()` 新增 `regime` 参数
  - [ ] `scheduler.py` 传入 regime 上下文

---

## 涉及文件汇总

| 文件 | 修改类型 | 子任务 |
|------|---------|--------|
| `signals/momentum.py` | 增量修改（新增函数 + 检测）| S-1, S-2 |
| `signals/volume.py` | 增量修改（新增函数 + 检测）| S-3 |
| `engine/inflection.py` | 小改（权重表 + 参数）| S-1, S-2, S-3, S-4 |
| `scheduler.py` | 小改（传入 regime 参数）| S-4 |
| `signals/volatility.py` | **不修改** | — |
| `alerts/telegram_alert.py` | **不修改** | — |
