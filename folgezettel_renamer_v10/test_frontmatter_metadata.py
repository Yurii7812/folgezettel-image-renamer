from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from folgezettel_renamer import sync_markdown_folder


def test_exif_time_and_filename_title() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        image_path = folder / "ZK_1.jpg"
        exif = Image.Exif()
        exif[36867] = "2024:05:06 07:08:09"
        Image.new("RGB", (20, 20), "white").save(image_path, exif=exif)

        sync_markdown_folder(folder, "ZK_", create_missing=True)
        text = (folder / "ZK_1.md").read_text(encoding="utf-8")
        assert "time: 2024-05-06 07:08:09" in text
        assert "title: ZK_1" in text

        # 古い値も一括更新で修正される。
        changed = text.replace("time: 2024-05-06 07:08:09", "time: 2000-01-01 00:00:00")
        changed = changed.replace("title: ZK_1", "title: old-title")
        (folder / "ZK_1.md").write_text(changed, encoding="utf-8")
        sync_markdown_folder(folder, "ZK_", create_missing=True)
        text = (folder / "ZK_1.md").read_text(encoding="utf-8")
        assert "time: 2024-05-06 07:08:09" in text
        assert "title: ZK_1" in text
        assert "old-title" not in text


def test_fallback_to_file_time_and_index_titles() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        image_path = folder / "ZK_2.png"
        Image.new("RGB", (20, 20), "white").save(image_path)
        expected = datetime(2023, 2, 3, 4, 5, 6)
        stamp = expected.timestamp()
        os.utime(image_path, (stamp, stamp))

        sync_markdown_folder(folder, "ZK_", create_missing=True)
        text = (folder / "ZK_2.md").read_text(encoding="utf-8")
        assert "time: 2023-02-03 04:05:06" in text
        assert "title: ZK_2" in text

        root = (folder / "ZK.md").read_text(encoding="utf-8")
        index = (folder / "ZK_Index.md").read_text(encoding="utf-8")
        assert "title: ZK\n" in root
        assert "title: ZK_Index\n" in index


if __name__ == "__main__":
    test_exif_time_and_filename_title()
    test_fallback_to_file_time_and_index_titles()
    print("frontmatter metadata tests: OK")
