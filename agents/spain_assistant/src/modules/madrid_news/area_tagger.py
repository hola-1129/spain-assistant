"""为每条新闻标注马德里行政区和熟知片区名称。"""

from src.core.logger import get_logger

log = get_logger(__name__)

# 马德里21个官方行政区
_OFFICIAL_DISTRICTS = {
    "Centro", "Arganzuela", "Retiro", "Salamanca", "Chamartín",
    "Tetuán", "Chamberí", "Fuencarral-El Pardo", "Moncloa-Aravaca",
    "Latina", "Carabanchel", "Usera", "Puente de Vallecas",
    "Moratalaz", "Ciudad Lineal", "Hortaleza", "Villaverde",
    "Villa de Vallecas", "Vicálvaro", "San Blas-Canillejas", "Barajas",
}

# 熟知片区/地标 → (展示名, 行政区)
_NEIGHBORHOOD_MAP: dict[str, tuple[str, str]] = {
    # Hortaleza
    "Valdebebas": ("Valdebebas", "Hortaleza"),
    "Sanchinarro": ("Sanchinarro", "Hortaleza"),
    # Fuencarral-El Pardo
    "Las Tablas": ("Las Tablas", "Fuencarral-El Pardo"),
    "Montecarmelo": ("Montecarmelo", "Fuencarral-El Pardo"),
    "Mirasierra": ("Mirasierra", "Fuencarral-El Pardo"),
    "El Pardo": ("El Pardo", "Fuencarral-El Pardo"),
    # Chamartín
    "Santiago Bernabéu": ("Bernabéu", "Chamartín"),
    "Bernabéu": ("Bernabéu", "Chamartín"),
    "Ciudad Deportiva Real Madrid": ("Chamartín", "Chamartín"),
    # Salamanca
    "Goya": ("Salamanca", "Salamanca"),
    "Recoletos": ("Salamanca", "Salamanca"),
    "Lista": ("Salamanca", "Salamanca"),
    # Retiro
    "El Retiro": ("Retiro", "Retiro"),
    "Parque del Retiro": ("Retiro", "Retiro"),
    "Museo del Prado": ("Retiro", "Retiro"),
    "Thyssen": ("Retiro", "Retiro"),
    # Centro
    "Sol": ("Centro", "Centro"),
    "Gran Vía": ("Centro", "Centro"),
    "Malasaña": ("Centro", "Centro"),
    "Chueca": ("Centro", "Centro"),
    "Lavapiés": ("Centro", "Centro"),
    "La Latina": ("Latina", "Latina"),
    "Plaza Mayor": ("Centro", "Centro"),
    "Palacio Real": ("Centro", "Centro"),
    "Cibeles": ("Centro", "Centro"),
    "Reina Sofía": ("Centro", "Centro"),
    # Chamberí
    "Almagro": ("Chamberí", "Chamberí"),
    "Ríos Rosas": ("Chamberí", "Chamberí"),
    # Carabanchel
    "Vista Alegre": ("Carabanchel", "Carabanchel"),
    # Usera
    "Pradolongo": ("Usera", "Usera"),
    "Moscardó": ("Usera", "Usera"),
    # Vallecas
    "Entrevías": ("Puente de Vallecas", "Puente de Vallecas"),
    # Barajas
    "IFEMA": ("IFEMA / Barajas", "Barajas"),
    "Ifema": ("IFEMA / Barajas", "Barajas"),
    "Aeropuerto": ("Barajas", "Barajas"),
    # San Blas-Canillejas
    "Wanda Metropolitano": ("Wanda Metropolitano", "San Blas-Canillejas"),
    # Arganzuela
    "Madrid Río": ("Madrid Río", "Arganzuela"),
    # Moncloa-Aravaca
    "Casa de Campo": ("Casa de Campo", "Moncloa-Aravaca"),
    "Ciudad Universitaria": ("Moncloa-Aravaca", "Moncloa-Aravaca"),
}

_DISTRICT_LOWER: dict[str, str] = {d.lower(): d for d in _OFFICIAL_DISTRICTS}

_IGNORE_VALUES = {"原文未说明", "madrid", "spain", "españa", "comunidad de madrid"}


def _search(text: str) -> tuple[str, str | None, str]:
    """在文本中查找地点，返回 (area_label, district_or_None, area_type)。"""
    if not text:
        return "Madrid", None, "unknown"

    tl = text.lower()

    for alias, (label, district) in _NEIGHBORHOOD_MAP.items():
        if alias.lower() in tl:
            return label, district, "neighborhood_alias"

    for dl, district in _DISTRICT_LOWER.items():
        if dl in tl:
            return district, district, "official_district"

    return "Madrid", None, "unknown"


def tag_area(article: dict) -> dict:
    """根据 zh.location_info / key_points 为文章添加区域标签字段。

    写入字段：
      area_label   — 友好展示名（如 "Valdebebas"、"Salamanca"、"Madrid"）
      area_district — 对应的马德里官方行政区（可为 None）
      area_type    — "neighborhood_alias" | "official_district" | "unknown"
    """
    loc = article.get("zh", {}).get("location_info", {})
    kp_loc = article.get("zh", {}).get("key_points", {}).get("location", "")

    parts = [
        loc.get("name", ""),
        loc.get("address", ""),
        loc.get("district", ""),
        loc.get("google_maps_query", ""),
        kp_loc,
    ]
    search_text = " ".join(
        p for p in parts if p and p.strip().lower() not in _IGNORE_VALUES
    )

    area_label, district, area_type = _search(search_text)

    # 如果 LLM 已直接给出行政区名，且我们未匹配到更具体的片区，尝试升级
    if area_type == "unknown":
        loc_d = (loc.get("district") or "").strip()
        matched = _DISTRICT_LOWER.get(loc_d.lower())
        if matched:
            area_label = matched
            district = matched
            area_type = "official_district"

    article["area_label"] = area_label
    article["area_district"] = district
    article["area_type"] = area_type
    return article
