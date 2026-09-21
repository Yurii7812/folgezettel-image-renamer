Folgezettel画像リネーマー v10

【起動方法】
1. ダウンロードしたZIPを右クリックします。
2. 「すべて展開」を選びます。
3. 展開後のフォルダを開きます。
4. START.batをダブルクリックします。

ZIPの中から直接START.batを実行しないでください。

【基本キー】
Space : 空欄から通常IDを入力
↑     : 直前のIDを残して編集
→     : 同じ階層の次のID
↓     : 子ID
←     : 直前の変更を取り消す
T      : トピックノート
I      : Indexノート
o      : その他モード開始
O      : その他モード解除

【通常ノート】
接頭辞がZK_、IDが1aの場合:
ZK_1a.jpg

【トピックノート】
Tを押し、番号とタイトルを入力します。
例: 番号 2、タイトル bukkyou
結果: ZK_2_bukkyou.jpg

ZK_2.jpgとZK_2_bukkyou.jpgがある場合、Markdown更新でZK_2_Index.mdを作り、そのChildへ両方を登録します。

【Indexノート】
Iを押し、Index名を入力します。
例: あ～い
結果: ZK_Index_あ～い.jpg

対応するZK_Index_あ～い.mdを作成し、ZK_Index.mdのChildへ追加します。

【その他モード】
oを押すと「分類」と「名前」の入力欄が出ます。
例:
分類: diary
名前: 2026-07-31-FR
結果: ZK_diary_2026-07-31-FR.jpg

1枚確定した後もその他モードは継続します。次の画像では分類diaryを保持し、名前欄だけを入力します。
Shift+O、つまり大文字Oを押すとその他モードを解除します。

分類にはdiary、dreamなどを使用できます。
数字だけの分類は通常IDと衝突するため使用できません。

【日付を含むその他ノート】
名前の途中にYYYY-MM-DDが含まれている場合、Markdown更新時に年月階層を自動作成します。
後ろに文字が続いていても対象です。
例:
ZK_diary_2026-07-31-FR.jpg
ZK_dream_2026-04-12-night.jpg

同じ分類が1年分だけの場合:
ZK_diary.md
└─ ZK_diary_2026-07.md
   └─ ZK_diary_2026-07-31-FR.md

複数年にまたがる場合:
ZK_diary.md
├─ ZK_diary_2026.md
│  ├─ ZK_diary_2026-03.md
│  └─ ZK_diary_2026-04.md
└─ ZK_diary_2027.md
   └─ ZK_diary_2027-01.md

年が追加された場合は、既存の月ノートのParentも自動的に年ノートへ更新します。
日付を含まないその他ノートは、分類ノートのChildへ直接追加します。

【ZK.mdのChild順】
ZK.mdは次の順番で自動更新します。

[Index](ZK_Index.md)

[diary](ZK_diary.md)
[dream](ZK_dream.md)

[1](ZK_1.md)
[2_Index](ZK_2_Index.md)
[3](ZK_3.md)

最初にIndex、その後に1行空けてその他モードの分類、さらに1行空けて通常の番号ノートを並べます。
番号別Indexがある場合は、通常ノートよりZK_2_Index.mdを優先します。

【Markdown書式】
画像ノートのtitleには、拡張子を除いたファイル名を入れます。
画像ノートのtimeには、EXIF撮影日時を使用します。なければWindowsの作成日時、取得できなければ更新日時を使用します。

例:
---
time: 2026-07-31 05:13:58
title: ZK_diary_2026-07-31-FR
---

# diary_2026-07-31-FR

![](ZK_diary_2026-07-31-FR.jpg)

Parent:
[2026-07](ZK_diary_2026-07.md)
Child:
BackLink:

[Index](index.md)

画像を持たないZK.md、ZK_Index.md、年月Indexなどは、titleをファイル名にし、既存のtimeを維持します。
Child:の直後、最後のChildリンクとBackLink:の間には空行を入れません。
旧版のFOLGEZETTEL管理コメントは一括更新時に削除します。

【Markdown更新】
「Markdownを一括更新」または名前付け画面の「Markdown更新」を押し、対象フォルダを選択します。
画像と既存Markdownを走査し、Parent、Child、Index、トピックIndex、その他分類、年、月のリンクを作成・更新します。
既存本文、BackLinkの内容、ZK以外の手書きリンクは保持します。

【ID規則】
1 の子: 1a
1a の子: 1a1
1a の次: 1b
1z の次: 1aa
1a99 の次: 1a100

初回起動時は画像表示用のPillowを自動インストールする場合があります。
起動に失敗した場合は、同じフォルダのstartup_error.logを確認してください。
