from pathlib import Path
from tempfile import TemporaryDirectory

from folgezettel_renamer import (
    FolgezettelApp,
    ImageItem,
    increment_letters,
    next_sibling_id,
    normalize_title,
)


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeEntry:
    def focus_set(self):
        pass


def make_app(folder: Path, items: list[ImageItem]):
    app = object.__new__(FolgezettelApp)
    app.folder = folder
    app.items = items
    app.current_index = 0
    app.undo_stack = []
    app.prefix_var = FakeVar("ZK_")
    app.status_var = FakeVar("")
    app.topic_id_entry = FakeEntry()
    app.topic_title_entry = FakeEntry()
    app.hide_input = lambda: None
    app.save_project = lambda: None
    app.load_current_image = lambda: None
    return app


def test_rules():
    assert increment_letters("z") == "aa"
    assert next_sibling_id("1z") == "1aa"
    assert next_sibling_id("1a99") == "1a100"
    assert normalize_title("  Bu Kkyou  ") == "bu_kkyou"


def test_topic_and_plain_id_can_coexist():
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "scan1.jpg").write_bytes(b"one")
        (folder / "scan2.jpg").write_bytes(b"two")
        items = [
            ImageItem("scan1.jpg", "scan1.jpg"),
            ImageItem("scan2.jpg", "scan2.jpg"),
        ]
        app = make_app(folder, items)

        app.commit_topic_note("2", "bukkyou")
        assert (folder / "ZK_2_bukkyou.jpg").exists()
        assert items[0].folgezettel_id == "2"
        assert items[0].topic_title == "bukkyou"

        app.commit_id("2")
        assert (folder / "ZK_2.jpg").exists()
        assert items[1].folgezettel_id == "2"
        assert items[1].topic_title is None


if __name__ == "__main__":
    test_rules()
    test_topic_and_plain_id_can_coexist()
    print("All tests passed")
