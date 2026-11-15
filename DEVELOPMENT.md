# Development Notes

## ブランチ方針

### `main`

利用許可が確認済みのデータだけを公開します。

- ☆11 / ☆12: bemani2sp11 wiki
- ☆9: 胡椒氏版
- ☆10 NORMAL / HARD: NASK氏版・胡椒氏版（切り替え対応）

### NASK氏版の公開

NASK氏版 ☆10 NORMAL / HARD は、両方とも利用許可取得済みです。
`feature/nask-sp10` で開発した対応を `main` へ統合して公開します。

- 胡椒氏版と同じUI
- Skill Rating / Skill Card / JOIN監査を共通化
- 今後の難易度表更新も `main` に反映

## Skill Rating

### レベル基礎値

- ☆9: 400
- ☆10: 600
- ☆11: 800
- ☆12: 1000

難易度帯は帯ごとに 25pt 加算。

### ランプ加点

- A-EASY: +0
- EASY: +25
- NORMAL: +50
- HARD: +100
- EX-HARD: +150
- FULLCOMBO: +200

### Base Rating

適正☆の評価上位40譜面の平均。

### 下位☆Bonus

- 1つ下: 上位15譜面。HARD相当基準超過分を20%反映、最大+20
- 2つ下: 上位5譜面。EX-HARD相当基準超過分を10%反映、最大+5
- 3つ下以下: 対象外

### 推奨ランプ

- -1☆: HARD
- -2☆: EX-HARD
- -3☆以下: FULLCOMBO

## JOINルール

- `(L)` / `(H)` 明記は厳密一致
- 別譜面からランプを借りない
- 無印特殊ケースだけ明示的overrideで解決

既知override:

- Summer Vacation(CU mix) -> H
- THE SAFARI -> H
- おおきなこえで -> L

L譜面がCSVにないがA/Hがある場合は「L未記録候補」として監査表示します。

## PWA

READMEだけの変更ではService Workerのキャッシュ更新は不要です。

`index.html` などキャッシュ対象アセットを公開更新するときは、
`sw.js` の `CACHE` 名を1つ進めます。
