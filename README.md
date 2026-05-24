# fre800slmp

[![CI](https://github.com/mokouliszt/fre800slmp/actions/workflows/ci.yml/badge.svg)](https://github.com/mokouliszt/fre800slmp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/fre800slmp.svg)](https://pypi.org/project/fre800slmp/)
[![Python](https://img.shields.io/pypi/pyversions/fre800slmp.svg)](https://pypi.org/project/fre800slmp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

三菱電機 **FREQROL-E800** シリーズインバータ向けの SLMP クライアント (Python実装)。

QnA互換 3E バイナリフレームに対応し、 TCP / UDP の両方で通信できる。
**FR-E800のマニュアル §2.10 のデバイス表記規約** (特に `W` を10進アドレスとして扱う点) に従っている。

## 特徴

- **QnA互換 3E バイナリフレーム**: マニュアル §2.10 準拠。
- **TCP / UDP の両方をサポート**: `transport="udp"` で切替可能。
- **FR-E800の基数規約に従ったアドレスパーサ**: `X`/`Y` は16進、`W` は10進
  (`W7` ⇄ Pr.7、`W902` ⇄ Pr.902)、その他は10進。
- **文字列ベースの高レベルAPI**: `inv.read("D100")`, `inv.write("M10", True)`。
- **ビット / ワード自動判定 + 型ガード**: ビットデバイスに `int` を渡したり、
  ワードデバイスに `bool` を渡したりすると `TypeError`。
- **依存ゼロ**: 標準ライブラリのみ。

## インストール

```bash
pip install fre800slmp
```

Python 3.10 以上が必要。

## クイックスタート

```python
from fre800slmp import FRE800Slmp

with FRE800Slmp("192.168.50.1", port=5010, transport="tcp") as inv:
    # パラメータ書込み (FR-E800のPr.7 = W7 加速時間, 0.1s単位)
    inv.write("W7", 30)              # 3.0秒
    print(inv.read("W7"))            # → 30

    # ワード連続読出し
    print(inv.read_range("D200", 5)) # → [int, int, int, int, int]

    # ビットアクセス
    inv.write("M10", True)
    print(inv.read("M10"))           # → True

    # 16進アドレスのビットデバイス
    print(inv.read("X1F"))           # X[0x1F] = 31番目の入力

    # 接続確認に便利なコマンド
    name, code = inv.read_type_name()
    print(name, hex(code))           # 'FR-E800-E' 0x54f
```

## インバータ側の事前設定

SLMP通信を使うには、インバータ側で以下のパラメータを事前に設定しておく:

| パラメータ | 設定値 | 説明 |
| --- | --- | --- |
| `Pr.414` | `≠ 0` | シーケンス機能動作選択。SLMPはシーケンス機能ONが前提 |
| `Pr.1427`〜`Pr.1430` のいずれか | `5010`〜`5013` | Ethernet機能選択。設定値がそのままTCP/UDPポート番号になる |
| `Pr.1424` | 1〜239 | Ethernet通信ネットワーク番号 |
| `Pr.1425` | 1〜120 | Ethernet通信局番 |
| `Pr.1434`〜`Pr.1437` | - | IPアドレス |
| `Pr.1438`〜`Pr.1441` | - | サブネットマスク |

**Ethernet仕様品 / 安全通信仕様品 / IP67仕様品はバイナリコードのみ対応**
(ASCIIコードは非対応)。本ライブラリはバイナリコードのみ実装している。

## サポートしているデバイス

マニュアル §2.10 のデバイス表に基づく:

| デバイス | 種別 | コード | 範囲 (FR-E800) | 文字列例 |
| --- | --- | --- | --- | --- |
| `SM` | bit | 0x91 | (シーケンス機能依存) | `"SM400"` |
| `SD` | word | 0xA9 | (シーケンス機能依存) | `"SD210"` |
| `X` | bit | 0x9C | H0〜H7F (**16進**) | `"X1F"` |
| `Y` | bit | 0x9D | H0〜H7F (**16進**) | `"Y20"` |
| `M` | bit | 0x90 | 0〜127 | `"M10"` |
| `D` | word | 0xA8 | 0〜255 | `"D100"` |
| `W` | word | 0xB4 | 8192点 + 飛び地 (**10進**) | `"W7"` (Pr.7), `"W902"` (Pr.902) |
| `TS`/`TC`/`TN` | bit/bit/word | 0xC1/C0/C2 | 0〜15 | `"TN5"` |
| `SS`/`SC`/`SN` | bit/bit/word | 0xC7/C6/C8 | 0点 (PC割付け次第) | `"SN0"` |
| `CS`/`CC`/`CN` | bit/bit/word | 0xC4/C3/C5 | 0〜15 | `"CN3"` |

## API リファレンス

### 高レベル: 文字列アドレス指定

| メソッド | 戻り値 | 説明 |
| --- | --- | --- |
| `read(addr)` | `int` または `bool` | 単一点を読む。ビット/ワード自動判定 |
| `write(addr, value)` | - | 単一点を書く。型ガードあり |
| `read_range(addr, count)` | `list[int]` または `list[bool]` | 連続読出 |
| `write_range(addr, values)` | - | 連続書込 |

### 低レベル: デバイスコード直接指定

| メソッド | 説明 |
| --- | --- |
| `read_words(device_code, head_no, count)` | ワード連続読出 (0x0401 / 0x0000) |
| `write_words(device_code, head_no, values)` | ワード連続書込 (0x1401 / 0x0000) |
| `read_bits(device_code, head_no, count)` | ビット連続読出 (0x0401 / 0x0001) |
| `write_bits(device_code, head_no, values)` | ビット連続書込 (0x1401 / 0x0001) |

### インバータ制御 / 形名読出し

| メソッド | 説明 |
| --- | --- |
| `remote_run(force=False, clear_devices=False)` | Remote Run (0x1001) |
| `remote_stop()` | Remote Stop (0x1002) |
| `read_type_name()` | 形名 + 形名コード (0x0101)。FR-E800実機なら `("FR-E800-E", 0x054F)` |
| `read_parameter(pr_no)` / `write_parameter(pr_no, value)` | Pr.番号でアクセスする便利ラッパ |

## エラーハンドリング

応答の終了コードが0以外のときは `SlmpError` が送出される:

```python
from fre800slmp import FRE800Slmp, SlmpError

with FRE800Slmp("192.168.50.1") as inv:
    try:
        inv.read("D9999")  # 範囲外
    except SlmpError as e:
        print(f"エラーコード: 0x{e.end_code:04X}")
```

マニュアル §2.10 に記載のエラーコード:

| コード | 意味 |
| --- | --- |
| `0x4031` | 指定したデバイスが範囲外 |
| `0x4080` | 要求データ異常 |
| `0xC059` | コマンドやサブコマンドの指定誤り |
| `0xC05B` | 指定デバイスに対して書込み/読出し不可 |
| `0xC05C` | 要求伝文に誤り |
| `0xC060` | 要求内容に誤り |
| `0xC061` | 要求データ長がデータ数と不一致 |
| `0xCEE1` | 要求伝文サイズ超過 |
| `0xCEE2` | 応答伝文サイズ超過 |

## ライセンス

MIT License — `LICENSE` を参照。
