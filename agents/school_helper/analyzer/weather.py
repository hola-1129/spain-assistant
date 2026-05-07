"""Open-Meteo 每日天气预报查询。免 key、欧洲覆盖好；最多 16 天。

一次性 init 拉取 daily 数据按日期索引。lookup(date) 返回紧凑中文摘要
（如 "☀️ 晴 22°/12°C 降水 10%"）；超出预报范围 / 拉取失败时返回空串，不阻塞主流程。
"""

from __future__ import annotations

import requests

from utils.logger import setup_logger

logger = setup_logger("weather")

# WMO weather codes → (emoji, 中文)
_WMO_CODE: dict[int, tuple[str, str]] = {
    0:  ("☀️", "晴"),
    1:  ("🌤",  "晴间多云"),
    2:  ("⛅",  "局部多云"),
    3:  ("☁️", "阴"),
    45: ("🌫",  "雾"),
    48: ("🌫",  "雾凇"),
    51: ("🌦",  "毛毛雨"),
    53: ("🌦",  "小雨"),
    55: ("🌧",  "中雨"),
    56: ("🌧",  "冻雨"),
    57: ("🌧",  "冻雨"),
    61: ("🌧",  "小雨"),
    63: ("🌧",  "中雨"),
    65: ("🌧",  "大雨"),
    66: ("🌧",  "冻雨"),
    67: ("🌧",  "冻雨"),
    71: ("🌨",  "小雪"),
    73: ("🌨",  "中雪"),
    75: ("❄️",  "大雪"),
    77: ("❄️",  "雪粒"),
    80: ("🌦",  "阵雨"),
    81: ("🌧",  "阵雨"),
    82: ("🌧",  "强阵雨"),
    85: ("🌨",  "阵雪"),
    86: ("❄️",  "强阵雪"),
    95: ("⛈",   "雷雨"),
    96: ("⛈",   "雷暴冰雹"),
    99: ("⛈",   "雷暴冰雹"),
}


class WeatherForecast:
    """实例化时拉一次 Open-Meteo daily 数据，所有事件共享同一份预报。"""

    def __init__(self, *,
                 latitude: float = 40.52,           # La Moraleja, Madrid 默认
                 longitude: float = -3.63,
                 timezone: str = "Europe/Madrid",
                 forecast_days: int = 3,
                 timeout_s: int = 10):
        self._by_date: dict[str, dict] = {}
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":      latitude,
            "longitude":     longitude,
            "daily":         "weathercode,temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max",
            "timezone":      timezone,
            "forecast_days": forecast_days,
        }
        try:
            resp = requests.get(url, params=params, timeout=timeout_s)
            resp.raise_for_status()
            daily = resp.json().get("daily", {}) or {}
            dates  = daily.get("time", []) or []
            codes  = daily.get("weathercode", []) or []
            tmax   = daily.get("temperature_2m_max", []) or []
            tmin   = daily.get("temperature_2m_min", []) or []
            pprob  = daily.get("precipitation_probability_max", []) or []
            for i, d in enumerate(dates):
                self._by_date[d] = {
                    "code":   codes[i]  if i < len(codes)  else None,
                    "t_max":  tmax[i]   if i < len(tmax)   else None,
                    "t_min":  tmin[i]   if i < len(tmin)   else None,
                    "p_prob": pprob[i]  if i < len(pprob)  else None,
                }
            logger.info(f"Open-Meteo 已加载 {len(self._by_date)} 天预报")
        except Exception as e:
            logger.warning(f"Open-Meteo 拉取失败，天气字段将留空: {e}")

    def lookup(self, date_str: str) -> str:
        """YYYY-MM-DD → 紧凑中文天气串。无数据返回空串。"""
        if not date_str:
            return ""
        d = self._by_date.get(date_str)
        if not d:
            return ""
        bits: list[str] = []
        code = d.get("code")
        if isinstance(code, int) and code in _WMO_CODE:
            emoji, label = _WMO_CODE[code]
            bits.append(f"{emoji} {label}")
        t_max, t_min = d.get("t_max"), d.get("t_min")
        if t_max is not None and t_min is not None:
            bits.append(f"{round(t_max)}°/{round(t_min)}°C")
        p_prob = d.get("p_prob")
        if isinstance(p_prob, (int, float)) and p_prob >= 10:
            bits.append(f"降水 {int(p_prob)}%")
        return " ".join(bits)
