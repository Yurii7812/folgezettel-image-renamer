from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from PIL import Image

from folgezettel_renamer import FolgezettelApp, ImageItem


def make_image(path: Path):
    Image.new('RGB', (30, 30), 'white').save(path)


with TemporaryDirectory() as td:
    folder = Path(td)
    for name in ('scan1.jpg', 'scan2.jpg', 'scan3.jpg'):
        make_image(folder / name)

    root = tk.Tk()
    root.withdraw()
    app = FolgezettelApp(root)
    app.folder = folder
    app.items = [ImageItem(name, name) for name in ('scan1.jpg', 'scan2.jpg', 'scan3.jpg')]
    app.auto_markdown_var.set(False)
    app.start_naming()
    root.update()

    app.on_other_start()
    app.other_category_var.set('diary')
    app.other_name_var.set('2026-07-31-FR')
    app.confirm_other_note()
    root.update()
    assert (folder / 'ZK_diary_2026-07-31-FR.jpg').exists()
    assert app.other_mode_active
    assert app.current_index == 1
    assert app.input_active
    assert app.other_category_var.get() == 'diary'

    app.other_name_var.set('2026-08-01-SA')
    app.confirm_other_note()
    root.update()
    assert (folder / 'ZK_diary_2026-08-01-SA.jpg').exists()
    assert app.current_index == 2
    assert app.other_category_var.get() == 'diary'

    app.on_other_exit()
    root.update()
    assert not app.other_mode_active
    assert not app.input_active

    app.on_index()
    app.index_label_var.set('あ～い')
    app.confirm_index_note()
    root.update()
    assert (folder / 'ZK_Index_あ～い.jpg').exists()

    root.destroy()

print('UI mode tests: OK')
