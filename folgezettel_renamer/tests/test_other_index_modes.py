import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from folgezettel_renamer import parse_zettel_image, sync_markdown_folder


def make_image(path: Path):
    Image.new('RGB', (20, 20), 'white').save(path)


with TemporaryDirectory() as td:
    folder = Path(td)
    names = [
        'ZK_1.jpg',
        'ZK_2.jpg',
        'ZK_2_bukkyou.jpg',
        'ZK_Index_あ～い.jpg',
        'ZK_diary_2026-03-02-MO.jpg',
        'ZK_diary_2026-04-10-FR.jpg',
        'ZK_diary_2027-01-01.jpg',
        'ZK_dream_2026-04-12-night.jpg',
        'ZK_dream_symbol.jpg',
    ]
    for name in names:
        make_image(folder / name)

    p = parse_zettel_image(folder / 'ZK_diary_2026-04-10-FR.jpg', 'ZK_')
    assert p and p['kind'] == 'other' and p['category'] == 'diary'
    assert p['date_parts'] == ('2026', '04', '10')
    p = parse_zettel_image(folder / 'ZK_Index_あ～い.jpg', 'ZK_')
    assert p and p['kind'] == 'range_index' and p['label'] == 'あ～い'

    changes, result = sync_markdown_folder(folder, 'ZK_', create_missing=True)
    assert result['images'] == len(names)

    root = (folder / 'ZK.md').read_text(encoding='utf-8')
    expected_order = [
        '[Index](ZK_Index.md)',
        '[diary](ZK_diary.md)',
        '[dream](ZK_dream.md)',
        '[1](ZK_1.md)',
        '[2_Index](ZK_2_Index.md)',
    ]
    positions = [root.index(x) for x in expected_order]
    assert positions == sorted(positions), root
    assert '[Index](ZK_Index.md)\n\n[diary](ZK_diary.md)' in root
    assert '[dream](ZK_dream.md)\n\n[1](ZK_1.md)' in root

    diary = (folder / 'ZK_diary.md').read_text(encoding='utf-8')
    assert '[2026](ZK_diary_2026.md)' in diary
    assert '[2027](ZK_diary_2027.md)' in diary

    year = (folder / 'ZK_diary_2026.md').read_text(encoding='utf-8')
    assert '[2026-03](ZK_diary_2026-03.md)' in year
    assert '[2026-04](ZK_diary_2026-04.md)' in year

    month = (folder / 'ZK_diary_2026-04.md').read_text(encoding='utf-8')
    assert '[2026-04-10-FR](ZK_diary_2026-04-10-FR.md)' in month

    leaf = (folder / 'ZK_diary_2026-04-10-FR.md').read_text(encoding='utf-8')
    assert 'Parent:\n[2026-04](ZK_diary_2026-04.md)\nChild:' in leaf
    assert 'title: ZK_diary_2026-04-10-FR' in leaf

    dream = (folder / 'ZK_dream.md').read_text(encoding='utf-8')
    assert '[2026-04](ZK_dream_2026-04.md)' in dream
    assert '[symbol](ZK_dream_symbol.md)' in dream
    assert '[2026-04](ZK_dream_2026-04.md)\n\n[symbol](ZK_dream_symbol.md)' in dream
    assert not (folder / 'ZK_dream_2026.md').exists()
    dream_month = (folder / 'ZK_dream_2026-04.md').read_text(encoding='utf-8')
    assert 'Parent:\n[dream](ZK_dream.md)\nChild:' in dream_month

    global_index = (folder / 'ZK_Index.md').read_text(encoding='utf-8')
    assert '[あ～い](ZK_Index_あ～い.md)' in global_index
    index_leaf = (folder / 'ZK_Index_あ～い.md').read_text(encoding='utf-8')
    assert '![](ZK_Index_あ～い.jpg)' in index_leaf
    assert 'Parent:\n[Index](ZK_Index.md)\nChild:' in index_leaf

    topic_index = (folder / 'ZK_2_Index.md').read_text(encoding='utf-8')
    assert '[2](ZK_2.md)' in topic_index
    assert '[2_bukkyou](ZK_2_bukkyou.md)' in topic_index

print('other/index mode hierarchy tests: OK')

with TemporaryDirectory() as td:
    folder = Path(td)
    make_image(folder / 'ZK_diary_2026-04-01.jpg')
    sync_markdown_folder(folder, 'ZK_', create_missing=True)
    diary = (folder / 'ZK_diary.md').read_text(encoding='utf-8')
    assert '[2026-04](ZK_diary_2026-04.md)' in diary
    assert not (folder / 'ZK_diary_2026.md').exists()
    month = (folder / 'ZK_diary_2026-04.md').read_text(encoding='utf-8')
    assert 'Parent:\n[diary](ZK_diary.md)\nChild:' in month

    make_image(folder / 'ZK_diary_2027-01-02.jpg')
    sync_markdown_folder(folder, 'ZK_', create_missing=True)
    diary = (folder / 'ZK_diary.md').read_text(encoding='utf-8')
    assert '[2026](ZK_diary_2026.md)' in diary
    assert '[2027](ZK_diary_2027.md)' in diary
    month = (folder / 'ZK_diary_2026-04.md').read_text(encoding='utf-8')
    assert 'Parent:\n[2026](ZK_diary_2026.md)\nChild:' in month

print('adaptive year hierarchy tests: OK')
