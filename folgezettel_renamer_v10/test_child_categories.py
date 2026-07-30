from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from folgezettel_renamer import sync_markdown_folder


def make_image(path: Path):
    Image.new("RGB", (20, 20), "white").save(path)


def run():
    with TemporaryDirectory() as td:
        folder = Path(td)
        make_image(folder / "ZK_1.jpg")
        make_image(folder / "ZK_1a.jpg")
        make_image(folder / "ZK_1n.jpg")
        make_image(folder / "ZK_1a1.jpg")

        # v6以前の形式を含む既存ファイルも、簡潔な形式へ更新できること。
        (folder / "ZK_1.md").write_text(
            """---
time: old
title: old
---

# 1

![](ZK_1.jpg)

Parent:
[External parent](parent-note.md)

Child:
ZK関連:
<!-- FOLGEZETTEL:CHILD:START -->
[Stale ZK child](ZK_999.md)
<!-- FOLGEZETTEL:CHILD:END -->

その他:
[External child](other-note.md)
[[Free memo]]

BackLink:
<!-- FOLGEZETTEL:BACKLINK:START -->
[[Keep backlink]]
<!-- FOLGEZETTEL:BACKLINK:END -->

[Index](index.md)
""",
            encoding="utf-8",
        )

        sync_markdown_folder(folder, "ZK_", create_missing=True)
        content = (folder / "ZK_1.md").read_text(encoding="utf-8")

        assert "ZK関連:" not in content
        assert "その他:" not in content
        assert "FOLGEZETTEL:CHILD" not in content
        assert "FOLGEZETTEL:BACKLINK" not in content
        assert "ZK_999.md" not in content
        assert (
            "Parent:\n"
            "[ZK](ZK.md)\n"
            "[External parent](parent-note.md)\n"
            "Child:\n"
        ) in content
        assert (
            "Child:\n"
            "[1a](ZK_1a.md)\n"
            "[1n](ZK_1n.md)\n\n"
            "[External child](other-note.md)\n"
            "[[Free memo]]\n"
            "BackLink:"
        ) in content
        assert "[[Keep backlink]]" in content

        # 繰り返し更新しても自動リンク・手書きリンクを重複させない。
        sync_markdown_folder(folder, "ZK_", create_missing=True)
        content2 = (folder / "ZK_1.md").read_text(encoding="utf-8")
        assert content2.count("[1a](ZK_1a.md)") == 1
        assert content2.count("[External child](other-note.md)") == 1
        assert content2.count("[ZK](ZK.md)") == 1

        child = (folder / "ZK_1a.md").read_text(encoding="utf-8")
        assert "Parent:\n[1](ZK_1.md)\nChild:\n" in child
        assert "[1a1](ZK_1a1.md)\nBackLink:" in child

    print("child formatting tests: OK")


if __name__ == "__main__":
    run()
