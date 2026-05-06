"""Stock/ETF universe for the unusual movers scanner."""

SECTORS = {
    "ai_semiconductor": [
        "NVDA", "AMD", "INTC", "AVGO", "QCOM", "MU", "MRVL",
        "ARM", "SMCI", "ASML", "LRCX", "KLAC", "AMAT", "TSM",
    ],
    "software": [
        "MSFT", "GOOGL", "META", "AMZN", "AAPL", "CRM", "ORCL",
        "ADBE", "SNOW", "PLTR", "MDB", "DDOG", "ZS", "CRWD",
        "PANW", "NET", "HUBS", "WDAY",
    ],
    "biotech": [
        "MRNA", "BNTX", "REGN", "AMGN", "GILD", "VRTX",
        "HIMS", "LLY", "NVO", "ABBV", "BMY", "BIIB",
    ],
    "fintech": [
        "PYPL", "SQ", "COIN", "V", "MA", "NU", "SOFI", "HOOD",
    ],
    "growth": [
        "TSLA", "UBER", "NFLX", "SPOT", "RBLX", "SHOP",
        "MELI", "ABNB", "PL",
    ],
    "large_cap": [
        "JPM", "BAC", "GS", "MS", "XOM", "CVX",
        "WMT", "COST", "HD", "BRK-B",
    ],
    "etf": [
        "SPY", "QQQ", "IWM", "XLK", "SMH",
        "XLF", "XLE", "ARKK", "XBI",
    ],
}

# Reverse map: symbol → sector
SYMBOL_SECTOR = {sym: sec for sec, syms in SECTORS.items() for sym in syms}

ALL_STOCKS = sorted(set(sym for syms in SECTORS.values() for sym in syms))
ALL_ETFS   = SECTORS["etf"]

# ── Asia markets ──────────────────────────────────────────────────────────────
ASIA_MARKETS = {
    "cn": {
        "label": "A股", "flag": "🇨🇳", "currency": "¥",
        "tz": "Asia/Shanghai",
        "open_range": (9*60+30, 15*60),      # 9:30–15:00 CST
        "benchmark": "000300.SS",             # 沪深300
        "indices": ["000001.SS", "399006.SZ"], # 上证综指、创业板
        "sectors": {
            "大盘蓝筹":  ["600519.SS", "601318.SS", "600036.SS", "000858.SZ",
                          "600900.SS", "601628.SS", "601166.SS"],
            "科技/AI":   ["002415.SZ", "300059.SZ", "688041.SS", "603893.SS",
                          "002230.SZ", "300122.SZ"],
            "半导体":    ["688981.SS", "688012.SS", "688496.SS", "002049.SZ"],
            "新能源":    ["300750.SZ", "601012.SS", "688599.SS", "300014.SZ",
                          "002594.SZ"],
            "消费/医药": ["000333.SZ", "600276.SS", "000661.SZ", "600887.SS"],
        },
    },
    "hk": {
        "label": "港股", "flag": "🇭🇰", "currency": "HK$",
        "tz": "Asia/Hong_Kong",
        "open_range": (9*60+30, 16*60),      # 9:30–16:00 HKT
        "benchmark": "^HSI",
        "indices": ["^HSI", "^HSTECH"],
        "sectors": {
            "科技互联网": ["0700.HK", "9988.HK", "3690.HK", "9618.HK",
                           "1810.HK", "9999.HK", "9626.HK"],
            "金融":       ["0939.HK", "1398.HK", "2318.HK", "0388.HK",
                           "0011.HK"],
            "医药":       ["2269.HK", "1177.HK", "6160.HK"],
            "消费/其他":  ["0941.HK", "0960.HK", "9868.HK"],
        },
    },
    "jp": {
        "label": "日本", "flag": "🇯🇵", "currency": "¥",
        "tz": "Asia/Tokyo",
        "open_range": (9*60, 15*60+30),      # 9:00–15:30 JST
        "benchmark": "^N225",
        "indices": ["^N225", "^TPX"],
        "sectors": {
            "科技/消费电子": ["6758.T", "7974.T", "9984.T", "6501.T", "6702.T"],
            "半导体/设备":   ["6857.T", "4063.T", "6723.T", "8035.T"],
            "汽车":          ["7203.T", "7267.T", "7751.T"],
            "金融":          ["8306.T", "8411.T", "8316.T"],
            "工业/精密":     ["6861.T", "6367.T", "6954.T"],
        },
    },
    "kr": {
        "label": "韩国", "flag": "🇰🇷", "currency": "₩",
        "tz": "Asia/Seoul",
        "open_range": (9*60, 15*60+30),      # 9:00–15:30 KST
        "benchmark": "^KS11",
        "indices": ["^KS11", "^KQ11"],
        "sectors": {
            "半导体":   ["005930.KS", "000660.KS"],
            "汽车":     ["005380.KS", "000270.KS"],
            "互联网":   ["035420.KS", "035720.KS"],
            "生物医药": ["068270.KS", "207940.KS", "326030.KS"],
            "电池/材料":["051910.KS", "373220.KS", "006400.KS"],
        },
    },
}

# Symbol display names (Chinese)
ASIA_NAMES = {
    # A股
    "600519.SS": "贵州茅台",   "601318.SS": "中国平安",   "600036.SS": "招商银行",
    "000858.SZ": "五粮液",     "600900.SS": "长江电力",   "601628.SS": "中国人寿",
    "601166.SS": "兴业银行",   "002415.SZ": "海康威视",   "300059.SZ": "东方财富",
    "688041.SS": "海光信息",   "603893.SS": "瑞芯微",     "002230.SZ": "科大讯飞",
    "300122.SZ": "智飞生物",   "688981.SS": "中芯国际",   "688012.SS": "中微公司",
    "688496.SS": "保隆科技",   "002049.SZ": "紫光国微",   "300750.SZ": "宁德时代",
    "601012.SS": "隆基绿能",   "688599.SS": "天合光能",   "300014.SZ": "亿纬锂能",
    "002594.SZ": "比亚迪",     "000333.SZ": "美的集团",   "600276.SS": "恒瑞医药",
    "000661.SZ": "长春高新",   "600887.SS": "伊利股份",
    "000300.SS": "沪深300",    "000001.SS": "上证综指",   "399006.SZ": "创业板指",
    # 港股
    "0700.HK":  "腾讯",        "9988.HK":  "阿里巴巴",   "3690.HK":  "美团",
    "9618.HK":  "京东",        "1810.HK":  "小米",        "9999.HK":  "网易",
    "9626.HK":  "哔哩哔哩",    "0939.HK":  "建设银行",   "1398.HK":  "工商银行",
    "2318.HK":  "中国平安",    "0388.HK":  "港交所",     "0011.HK":  "恒生银行",
    "2269.HK":  "药明生物",    "1177.HK":  "中国生物制药","6160.HK":  "百济神州",
    "0941.HK":  "中国移动",    "0960.HK":  "龙湖集团",   "9868.HK":  "小鹏汽车",
    # 日本
    "6758.T":  "Sony",         "7974.T":  "Nintendo",    "9984.T":  "SoftBank",
    "6501.T":  "Hitachi",      "6702.T":  "Fujitsu",     "6857.T":  "Advantest",
    "4063.T":  "信越化学",     "6723.T":  "Renesas",     "8035.T":  "Tokyo Electron",
    "7203.T":  "Toyota",       "7267.T":  "Honda",       "7751.T":  "Canon",
    "8306.T":  "三菱UFJ",      "8411.T":  "瑞穗FG",      "8316.T":  "三井住友",
    "6861.T":  "Keyence",      "6367.T":  "大金工业",    "6954.T":  "Fanuc",
    # 韩国
    "005930.KS": "Samsung",    "000660.KS": "SK Hynix",  "005380.KS": "Hyundai",
    "000270.KS": "Kia",        "035420.KS": "NAVER",     "035720.KS": "Kakao",
    "068270.KS": "Celltrion",  "207940.KS": "Samsung Bio","326030.KS": "SK Biopharmaceuticals",
    "051910.KS": "LG Chem",    "373220.KS": "LG Energy",  "006400.KS": "Samsung SDI",
}


def asia_all_symbols(market_key: str) -> list:
    """All tradeable symbols (excluding indices/benchmarks) for a market."""
    m = ASIA_MARKETS[market_key]
    return [s for secs in m["sectors"].values() for s in secs]


# Human-readable sector labels
SECTOR_LABELS = {
    "ai_semiconductor": "AI/半导体",
    "software":         "软件/云",
    "biotech":          "生物科技",
    "fintech":          "金融科技",
    "growth":           "成长股",
    "large_cap":        "大盘蓝筹",
    "etf":              "ETF",
}
