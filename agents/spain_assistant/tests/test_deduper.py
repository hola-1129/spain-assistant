"""测试去重逻辑。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.storage import compute_hash, is_seen, mark_seen


def test_hash_deterministic():
    h1 = compute_hash("Título de prueba", "2026-05-14")
    h2 = compute_hash("Título de prueba", "2026-05-14")
    assert h1 == h2


def test_dedup_flow():
    state = {"seen_hashes": {}}
    h = compute_hash("Test article", "2026-05-14")
    assert not is_seen(h, state)
    mark_seen(h, state)
    assert is_seen(h, state)


def test_different_titles_different_hash():
    h1 = compute_hash("Article A", "2026-05-14")
    h2 = compute_hash("Article B", "2026-05-14")
    assert h1 != h2


if __name__ == "__main__":
    test_hash_deterministic()
    test_dedup_flow()
    test_different_titles_different_hash()
    print("All tests passed.")
