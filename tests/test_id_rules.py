import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from folgezettel_renamer import child_id, increment_letters, next_sibling_id, normalize_id


def run_tests():
    assert increment_letters("a") == "b"
    assert increment_letters("z") == "aa"
    assert increment_letters("az") == "ba"
    assert increment_letters("zz") == "aaa"

    assert next_sibling_id("1") == "2"
    assert next_sibling_id("1a") == "1b"
    assert next_sibling_id("1z") == "1aa"
    assert next_sibling_id("1a99") == "1a100"
    assert next_sibling_id("1a1z") == "1a1aa"

    assert child_id("1") == "1a"
    assert child_id("1a") == "1a1"
    assert child_id("1a1") == "1a1a"

    assert normalize_id("１Ａ２Ｂ") == "1a2b"
    print("All ID rule tests passed.")


if __name__ == "__main__":
    run_tests()
