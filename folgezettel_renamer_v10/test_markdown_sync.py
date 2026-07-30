from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image

from folgezettel_renamer import (
    parent_id,
    sync_markdown_folder,
    restore_markdown_changes,
)


def make_image(path: Path):
    Image.new('RGB', (20, 20), 'white').save(path)


def run():
    assert parent_id('1') is None
    assert parent_id('1a') == '1'
    assert parent_id('1n') == '1'
    assert parent_id('1aa') == '1'
    assert parent_id('1a1') == '1a'
    assert parent_id('1a100') == '1a'
    assert parent_id('1a1b') == '1a1'

    with TemporaryDirectory() as td:
        folder = Path(td)
        make_image(folder / 'ZK_1.jpg')
        make_image(folder / 'ZK_1a.jpg')
        make_image(folder / 'ZK_1n.jpg')
        make_image(folder / 'ZK_1a1.jpg')
        make_image(folder / 'ZK_2_bukkyou.png')

        changes, result = sync_markdown_folder(folder, 'ZK_', create_missing=True)
        assert result['created'] == 8, result
        one = (folder / 'ZK_1.md').read_text(encoding='utf-8')
        assert 'Parent:\n[ZK](ZK.md)\nChild:' in one
        assert '[1a](ZK_1a.md)' in one
        assert '[1n](ZK_1n.md)' in one
        child = (folder / 'ZK_1a.md').read_text(encoding='utf-8')
        assert 'Parent:\n[1](ZK_1.md)\nChild:' in child
        assert '[1a1](ZK_1a1.md)' in child
        topic = (folder / 'ZK_2_bukkyou.md').read_text(encoding='utf-8')
        assert '# 2_bukkyou' in topic
        assert '![](ZK_2_bukkyou.png)' in topic
        assert 'Parent:\n[2_Index](ZK_2_Index.md)\nChild:' in topic

        # Existing personal text and BackLink survive relationship updates.
        p = folder / 'ZK_1.md'
        custom = p.read_text(encoding='utf-8').replace(
            'BackLink:\n\n[Index](index.md)',
            'BackLink:\n[[my-manual-link]]\n\n[Index](index.md)'
        ) + '\n\nMY PERSONAL TEXT\n'
        p.write_text(custom, encoding='utf-8')
        make_image(folder / 'ZK_1z.jpg')
        changes2, result2 = sync_markdown_folder(folder, 'ZK_', create_missing=True)
        one2 = p.read_text(encoding='utf-8')
        assert '[1z](ZK_1z.md)' in one2
        assert '[[my-manual-link]]' in one2
        assert 'MY PERSONAL TEXT' in one2

        # Undo helper can restore all changed markdown files.
        restore_markdown_changes(folder, changes2)
        restored = p.read_text(encoding='utf-8')
        assert '[1z](ZK_1z.md)' not in restored

    print('markdown sync tests: OK')


if __name__ == '__main__':
    run()
