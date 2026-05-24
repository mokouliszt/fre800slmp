# Changelog

## 0.1.0 (2026-05-25)

初版。

- QnA互換 3E バイナリフレーム実装
- TCP / UDP の両トランスポート対応
- FR-E800のマニュアル §2.10 デバイス表記規約に従ったアドレスパーサ
  (X/Yは16進、Wは10進、その他は10進)
- 文字列アドレス指定の高レベルAPI (`read` / `write` / `read_range` / `write_range`)
- 型ガード (ビットデバイスにint、ワードデバイスにbool は TypeError)
- Remote Run / Remote Stop / Read Type Name コマンド対応
- パラメータアクセス便利ラッパ (`read_parameter` / `write_parameter`)
