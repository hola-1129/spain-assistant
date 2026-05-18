# 数据源（v1，全部免费）

| # | 名称 | 用途 | 文档 | 备注 |
|---|------|------|------|------|
| 1 | DexScreener API | DEX 池子、价格、成交量、流动性、新币趋势 | https://docs.dexscreener.com/api/reference | 免费，~300 req/min；适合短线异动 |
| 2 | GeckoTerminal API | 多链 DEX 池子、OHLCV、流动性 | https://www.geckoterminal.com/dex-api | 免费公开，30 req/min；DexScreener 补充 |
| 3 | CoinGecko API | Top-100 加密资产价格、24h 成交量、市值、7日变化 | https://docs.coingecko.com/reference/coins-markets | 免费公开；Finance Bot 的 Top-100 crypto_scan 已迁移至此 |
| 4 | DeFiLlama API | 链 TVL、协议 TVL、稳定币流动 | https://defillama.com/docs/api | 免费，无需 key；判断大环境 |
| 5 | Polymarket Gamma API | events、markets、tags、series | https://docs.polymarket.com/#gamma-markets-api | 免费读取 |
| 6 | Polymarket CLOB API | orderbook、prices、spreads | https://docs.polymarket.com/#clob-api | 第一版**只读取**，不交易 |
| 7 | Polymarket Data API | trades、市场成交、仓位 | https://docs.polymarket.com/#data-api | 第一版**只读取**，不交易 |

## 端点速查

### DexScreener
- 搜索/热门：`GET https://api.dexscreener.com/latest/dex/search?q={query}`
- 链对：`GET https://api.dexscreener.com/latest/dex/pairs/{chain}/{pairAddress}`
- Token：`GET https://api.dexscreener.com/latest/dex/tokens/{tokenAddress}`

### GeckoTerminal
- 链列表：`GET https://api.geckoterminal.com/api/v2/networks`
- 热门池子：`GET https://api.geckoterminal.com/api/v2/networks/{network}/trending_pools`
- 新池子：`GET https://api.geckoterminal.com/api/v2/networks/{network}/new_pools`
- OHLCV：`GET https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}`

### CoinGecko
- Top-100 markets：`GET https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&price_change_percentage=24h,7d`

### DeFiLlama
- 链 TVL：`GET https://api.llama.fi/v2/chains`
- 协议 TVL：`GET https://api.llama.fi/protocols`
- 稳定币：`GET https://stablecoins.llama.fi/stablecoins`

### Polymarket
- Gamma events：`GET https://gamma-api.polymarket.com/events?closed=false&limit=...&tag={tag}`
- Gamma markets：`GET https://gamma-api.polymarket.com/markets?closed=false&limit=...`
- CLOB orderbook：`GET https://clob.polymarket.com/book?token_id={token_id}`
- CLOB prices：`GET https://clob.polymarket.com/prices-history?market={condition_id}`
- Data trades：`GET https://data-api.polymarket.com/trades?market={condition_id}`

## 限速与礼貌

各源在 `config.yaml.rate_limit` 下设置最小间隔。所有请求统一 `timeout` 防止挂死，
失败时记录日志、跳过本轮、不重试到死。
