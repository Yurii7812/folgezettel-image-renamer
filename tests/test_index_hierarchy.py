import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from folgezettel_renamer import sync_markdown_folder


def make_image(path: Path):
    Image.new("RGB", (20, 20), "white").save(path)


def make_plain_md(path: Path, heading: str):
    path.write_text(
        "---\n"
        "time: 2026-07-31 05:00:00\n"
        "title: 260731050000\n"
        "---\n\n"
        f"# {heading}\n\n"
        "Parent:\n\n"
        "Child:\n"
        "ZK関連:\n\n"
        "その他:\n"
        "[manual](other.md)\n\n"
        "BackLink:\n\n"
        "[Index](index.md)\n",
        encoding="utf-8",
    )


def run():
    with TemporaryDirectory() as td:
        folder = Path(td)
        make_image(folder / "ZK_1.jpg")
        make_image(folder / "ZK_2.jpg")
        make_image(folder / "ZK_2_bukkyou.jpg")
        make_image(folder / "ZK_2_rekishi.jpg")
        make_image(folder / "ZK_3.jpg")
        make_image(folder / "ZK_10.jpg")

        make_plain_md(folder / "ZK_Index_あ～い.md", "あ～い")
        make_plain_md(folder / "ZK_Index_か～こ.md", "か～こ")

        changes, result = sync_markdown_folder(folder, "ZK_", create_missing=True)
        assert result["created"] >= 9, result

        root = (folder / "ZK.md").read_text(encoding="utf-8")
        assert "# ZK" in root
        assert "Parent:\nChild:\n[Index](ZK_Index.md)\n\n[1](ZK_1.md)" in root
        assert "[2_Index](ZK_2_Index.md)" in root
        assert "[2](ZK_2.md)" not in root
        assert "[3](ZK_3.md)" in root
        assert root.index("[3](ZK_3.md)") < root.index("[10](ZK_10.md)")
        assert "[10](ZK_10.md)\nBackLink:" in root
        assert "ZK関連:" not in root
        assert "その他:" not in root

        one = (folder / "ZK_1.md").read_text(encoding="utf-8")
        assert "Parent:\n[ZK](ZK.md)\nChild:" in one

        topic_index = (folder / "ZK_2_Index.md").read_text(encoding="utf-8")
        assert "# 2_Index" in topic_index
        assert "Parent:\n[ZK](ZK.md)\nChild:\n" in topic_index
        assert "[2](ZK_2.md)" in topic_index
        assert "[2_bukkyou](ZK_2_bukkyou.md)" in topic_index
        assert "[2_rekishi](ZK_2_rekishi.md)\nBackLink:" in topic_index

        two = (folder / "ZK_2.md").read_text(encoding="utf-8")
        topic = (folder / "ZK_2_bukkyou.md").read_text(encoding="utf-8")
        assert "Parent:\n[2_Index](ZK_2_Index.md)\nChild:" in two
        assert "Parent:\n[2_Index](ZK_2_Index.md)\nChild:" in topic

        global_index = (folder / "ZK_Index.md").read_text(encoding="utf-8")
        assert "Parent:\n[ZK](ZK.md)\nChild:\n" in global_index
        assert "[あ～い](ZK_Index_あ～い.md)" in global_index
        assert "[か～こ](ZK_Index_か～こ.md)" in global_index
        assert global_index.index("[あ～い]") < global_index.index("[か～こ]")

        range_index = (folder / "ZK_Index_あ～い.md").read_text(encoding="utf-8")
        assert "Parent:\n[Index](ZK_Index.md)\nChild:" in range_index
        assert "[manual](other.md)" in range_index
        assert "ZK関連:" not in range_index
        assert "その他:" not in range_index

        # 既存の手書きChildは、番号別Indexでも更新後に残る。
        make_plain_md(folder / "ZK_4_Index.md", "4_Index")
        make_image(folder / "ZK_4.jpg")
        sync_markdown_folder(folder, "ZK_", create_missing=True)
        root2 = (folder / "ZK.md").read_text(encoding="utf-8")
        assert "[4_Index](ZK_4_Index.md)" in root2
        four_index = (folder / "ZK_4_Index.md").read_text(encoding="utf-8")
        assert "[4](ZK_4.md)" in four_index
        assert "[manual](other.md)" in four_index

    print("index hierarchy tests: OK")


if __name__ == "__main__":
    run()
