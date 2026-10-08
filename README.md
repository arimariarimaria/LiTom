## description
- このキーボードは無線分割式 50% 19mm スライドロータリー トラックボール内蔵のキーボードになります。

## ビルドガイド
- ビルドガイド
  - 作成中

- 購入後のセットアップ
  - https://frequent-breeze-833.notion.site/LoTom-2ace518048a380438cd8c65c32c07ce9

## スペック
- ファームウェア
  - ZMK を使用しています
  - ZMKStudio および DYAStudio に対応しております
- ハードウェア
  - 48 キー
  - choc v2、lofree 系列のスイッチが使用可能
  - 右手側が central,左手側が peripheral になります
  - 両手に OLED 内蔵
  - 左手にサイドにスライドロータリーを２つ内蔵
    - デフォルトでは左がマウススクロール、下側がタブ切り替えになっております
  - 右手にサイドにスライドロータリーを1つ内蔵
    - デフォルトでは左がマウススクロール
  - トラックボール19mm
    - ケースごとマグネットで張り付いているので、脱着可能です
  - 単4電池対応 2 つ必要です

## キーマップについて

- DYAStudioにて確認・編集を行なってください
  - https://studio.dya.cormoran.works/

- ZMK keymap-editor も使用できます
  - マクロ設定などを使いたい場合はこちらを使うとべんりです
  - https://nickcoutsos.github.io/keymap-editor
  - ご使用の時は本リポジトリをフォークしてお使いください
    - ※フォークしてマクロ等にパスワードなどを設定する際はリポジトリが public になってしまい情報漏洩につながりますのでご注意ください

### キーマップ図

キーマップを変更すると、GitHub Actions により以下の図も自動更新されます。

[![LiTom キーマップ](keymap-svg/LiTom.svg)](keymap-svg/LiTom.svg)

### レイヤー

- レイヤー 0 は Mac、レイヤー 1 は Windows 用の基本配列です
  - Windows 配列では Mac の Command の位置に Ctrl、Control の位置に Windows キーを配置しています
  - 基本配列のタブ用ロータリーは、Mac では従来どおり、Windows では Ctrl+PageUp/PageDown です
- レイヤー 2 がオートマウスレイヤーです
  - トラックボール操作で一時的に有効になり、400ms 操作がなければ解除されます
  - デフォルトのトラックボールのcpiは600cpiです
- レイヤー 3 がトラックボール時のスクロールレイヤーです
- レイヤー 4〜6 は Arrow / Num / Function、レイヤー 7 は BT です
- 補助レイヤーは共通で、従来のショートカットを引き継いでいます

### DYA Studio の追加機能

マクロ8件、コンボ16件（既存7件を含む）、USB・Bluetooth 接続先別の基本配列選択に対応しています。
マクロ・コンボはファームウェアを再ビルドせずに編集できます。
初回の移行、Windows / Mac の割り当て、保存方法は [DYA Studio 設定ガイド](docs/dya-studio.md) を参照してください。

## その他

不明な点がある場合は下記アカウントにご連絡ください
https://x.com/tomcat09131
