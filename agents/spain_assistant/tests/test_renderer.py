"""测试 HTML 渲染（不依赖网络和 LLM）。"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


MOCK_ARTICLES = [
    {
        "hash_id": "abc123",
        "title": "Actividad infantil en el Retiro",
        "url": "https://diario.madrid.es/test",
        "date": "2026-05-14",
        "importance": "A",
        "labels": ["亲子/儿童活动", "文化活动"],
        "summary": "Actividades para niños en el Parque del Retiro.",
        "content": "",
        "district": "Retiro",
        "category": "Cultura",
        "image_url": "",
        "fetched_at": "2026-05-14T08:30:00Z",
        "source": "https://diario.madrid.es/blog/notas-de-prensa/",
        "zh": {
            "chinese_title": "Retiro 公园周末儿童活动",
            "one_line_summary": "适合3-10岁孩子的免费户外活动",
            "key_points": {
                "time": "2026年5月15日 10:00-14:00",
                "location": "Retiro 公园",
                "audience": "3-10岁儿童及家长",
                "change": "免费手工艺工作坊",
                "practical": "免费，无需预约，先到先得",
            },
            "local_perspective": "Retiro 公园是马德里最受欢迎的家庭周末去处之一，此类活动通常人多，建议早到。",
            "family_advice": "适合3-10岁孩子\n免费参加，无需预约\n建议10点前到达，人会比较多\n带防晒霜和零食",
            "keywords": ["Retiro", "儿童活动", "免费"],
        },
        "article_url": "articles/abc123.html",
    }
]


def test_render_produces_html():
    """验证 render_all 能生成 index.html 和单篇页面。"""
    import src.core.config as cfg

    with tempfile.TemporaryDirectory() as tmp:
        # 临时覆盖 public_dir
        orig = cfg.public_dir
        cfg.public_dir = Path(tmp) / "public"
        cfg.public_dir.mkdir()

        try:
            from src.modules.madrid_news.renderer import render_all
            render_all(MOCK_ARTICLES)

            assert (cfg.public_dir / "index.html").exists(), "index.html 未生成"
            assert (cfg.public_dir / "articles" / "abc123.html").exists(), "单篇页面未生成"
            assert (cfg.public_dir / "data" / "latest.json").exists(), "latest.json 未生成"

            data = json.loads((cfg.public_dir / "data" / "latest.json").read_text())
            assert len(data) == 1
            assert data[0]["hash_id"] == "abc123"

            print("render test passed.")
        finally:
            cfg.public_dir = orig


if __name__ == "__main__":
    test_render_produces_html()
