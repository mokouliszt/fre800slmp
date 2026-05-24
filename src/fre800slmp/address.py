"""
FR-E800 デバイス定義とアドレス文字列パーサ。

基数規約はマニュアル §2.10 のデバイス表に従う:
  X, Y → 16進 (H0～H7F)
  W    → 10進 (FR-E800特有。Pr.N → W{N}: Pr.7 ⇄ W7, Pr.902 ⇄ W902)
  その他 → 10進
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class Device:
    """マニュアル §2.10 のデバイスコード一覧。"""

    SM = 0x91  # 特殊リレー       (bit)
    SD = 0xA9  # 特殊レジスタ     (word)
    X = 0x9C   # 入力             (bit)  範囲: H0～H7F (16進)
    Y = 0x9D   # 出力             (bit)  範囲: H0～H7F (16進)
    M = 0x90   # 内部リレー       (bit)  範囲: 0～127  (10進)
    D = 0xA8   # データレジスタ   (word) 範囲: 0～255  (10進)
    W = 0xB4   # リンクレジスタ   (word) ← パラメータはここ。8192点 (FR-E800では10進表記)
    # タイマ
    TS = 0xC1  # タイマ接点       (bit)
    TC = 0xC0  # タイマコイル     (bit)
    TN = 0xC2  # タイマ現在値     (word)
    # 積算タイマ
    SS = 0xC7  # 接点             (bit)
    SC = 0xC6  # コイル           (bit)
    SN = 0xC8  # 現在値           (word)
    # カウンタ
    CS = 0xC4  # カウンタ接点     (bit)
    CC = 0xC3  # カウンタコイル   (bit)
    CN = 0xC5  # カウンタ現在値   (word)


# (デバイスコード, kind, 番号の基数)
_DEVICE_TABLE: dict[str, tuple[int, str, int]] = {
    "SM": (Device.SM, "bit",  10),
    "SD": (Device.SD, "word", 10),
    "X":  (Device.X,  "bit",  16),
    "Y":  (Device.Y,  "bit",  16),
    "M":  (Device.M,  "bit",  10),
    "D":  (Device.D,  "word", 10),
    "W":  (Device.W,  "word", 10),
    "TS": (Device.TS, "bit",  10),
    "TC": (Device.TC, "bit",  10),
    "TN": (Device.TN, "word", 10),
    "SS": (Device.SS, "bit",  10),
    "SC": (Device.SC, "bit",  10),
    "SN": (Device.SN, "word", 10),
    "CS": (Device.CS, "bit",  10),
    "CC": (Device.CC, "bit",  10),
    "CN": (Device.CN, "word", 10),
}

# 長いプレフィックス (SM, SD, TS, ...) を先に試すために長さ降順で並べる
_ADDRESS_RE = re.compile(
    r"^(" + "|".join(sorted(_DEVICE_TABLE, key=len, reverse=True))
    + r")([0-9A-F]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Address:
    """パース済みのデバイスアドレス。"""

    device_code: int
    number: int
    kind: str  # "bit" or "word"
    raw: str   # 入力文字列 (大文字化済)


def parse_address(addr: str) -> Address:
    """
    "D100", "W7", "M10", "X1F", "SM400" のような文字列をパースする。

    基数は ``_DEVICE_TABLE`` 参照。失敗時は ``ValueError``。
    """
    s = addr.strip().upper()
    m = _ADDRESS_RE.match(s)
    if not m:
        raise ValueError(f"アドレス書式が不正: {addr!r}")
    name, num = m.group(1), m.group(2)
    code, kind, base = _DEVICE_TABLE[name]
    try:
        n = int(num, base)
    except ValueError as e:
        raise ValueError(
            f"{name}{num} の番号部 {num!r} は {base}進数として解釈できない"
        ) from e
    return Address(code, n, kind, s)


__all__ = ["Device", "Address", "parse_address"]
