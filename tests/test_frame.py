"""
伝文バイト列のスナップショットテスト (ネットワーク接続不要)。

ソケットをモックして、_send() が送信するバイト列が
マニュアル §2.10 の伝文フォーマット通りかを検証する。
"""

from __future__ import annotations

import struct

import pytest

from fre800slmp import Device, FRE800Slmp


class FakeSocket:
    """recv/sendallのモック。送信バイト列を記録し、応答を返す。"""

    def __init__(self, response: bytes):
        self.sent = b""
        self._response = response
        self._read_pos = 0

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def send(self, data: bytes) -> int:
        self.sent += data
        return len(data)

    def recv(self, n: int) -> bytes:
        chunk = self._response[self._read_pos:self._read_pos + n]
        self._read_pos += len(chunk)
        return chunk

    def settimeout(self, _t):
        pass

    def close(self):
        pass

    def connect(self, _addr):
        pass


def make_inv_with_response(response: bytes, transport: str = "tcp") -> tuple[FRE800Slmp, FakeSocket]:
    inv = FRE800Slmp("127.0.0.1", 5010, transport=transport)
    fake = FakeSocket(response)
    inv.sock = fake  # 直接差し込む (open() を呼ばない)
    return inv, fake


def build_response(end_code: int, payload: bytes = b"") -> bytes:
    """正常な応答ヘッダ + 応答データ。"""
    # サブヘッダ(D000) + ネット + 局 + I/O + マルチ + 長さ + 終了コード + payload
    body = struct.pack("<H", end_code) + payload
    return (
        b"\xD0\x00"
        + b"\x00\xFF"
        + struct.pack("<H", 0x03FF)
        + b"\x00"
        + struct.pack("<H", len(body))
        + body
    )


class TestRequestFrame:
    """要求伝文のバイト並びがマニュアル通りか。"""

    def test_read_words_d100(self):
        """Read D100 を 1点読出。"""
        inv, fake = make_inv_with_response(build_response(0, b"\x34\x12"))
        result = inv.read_words(Device.D, 100, 1)
        assert result == [0x1234]

        # 要求伝文の組立てを検証
        expected = (
            b"\x50\x00"                    # サブヘッダ
            + b"\x00\xFF"                  # ネットワーク, 局番
            + b"\xFF\x03"                  # 要求先I/O = 0x03FF (little)
            + b"\x00"                      # マルチドロップ
            + b"\x0C\x00"                  # 要求データ長 = 12 (little)
            + b"\x10\x00"                  # 監視タイマ = 0x0010 (little)
            + b"\x01\x04"                  # コマンド = 0x0401 (little)
            + b"\x00\x00"                  # サブコマンド = 0x0000
            + b"\x64\x00\x00"              # デバイス番号 = 100 (3バイトlittle)
            + b"\xA8"                      # デバイスコード = D = 0xA8
            + b"\x01\x00"                  # 点数 = 1
        )
        assert fake.sent == expected

    def test_read_w7_per_fr_e800_decimal(self):
        """FR-E800: W7 のデバイス番号フィールドは 0x000007 (10進の7をそのまま)。"""
        inv, fake = make_inv_with_response(build_response(0, b"\x1E\x00"))
        result = inv.read_words(Device.W, 7, 1)
        assert result == [30]
        # デバイス番号 (3バイト) + デバイスコード (1バイト)
        assert b"\x07\x00\x00\xB4" in fake.sent

    def test_write_words_d100(self):
        """Write D100 = 0x1234 を1点書込。"""
        inv, fake = make_inv_with_response(build_response(0))
        inv.write_words(Device.D, 100, [0x1234])

        expected_body = (
            b"\x10\x00"                    # 監視タイマ
            + b"\x01\x14"                  # コマンド 0x1401
            + b"\x00\x00"                  # サブコマンド 0x0000
            + b"\x64\x00\x00"              # デバイス番号 100
            + b"\xA8"                      # デバイスコード D
            + b"\x01\x00"                  # 点数 1
            + b"\x34\x12"                  # データ
        )
        assert fake.sent.endswith(expected_body)

    def test_write_bits_5_points_odd(self):
        """5点 (奇数) のビット書込みは最後のニブルが0埋め。マニュアル例: H10 H10 H10。"""
        inv, fake = make_inv_with_response(build_response(0))
        inv.write_bits(Device.M, 10, [True, False, True, False, True])
        # データ部 = 3バイト、上位ニブルから順、奇数点なので末尾は0埋め
        # 1,0,1,0,1, [0pad] → 0x10, 0x10, 0x10
        assert b"\x10\x10\x10" in fake.sent

    def test_read_bits_decode(self):
        """ビット読出: 1点を4bit, 上位ニブルから。"""
        # 5点 (奇数) を読む。応答データ: 0x10 0x10 0x10 (パターン 1,0,1,0,1)
        response = build_response(0, b"\x10\x10\x10")
        inv, _ = make_inv_with_response(response)
        result = inv.read_bits(Device.M, 10, 5)
        assert result == [True, False, True, False, True]


class TestEndianness:
    """エンディアンの取り違いがないか。"""

    def test_subheader_is_big_endian(self):
        """サブヘッダ 0x5000 はビッグエンディアン (バイト列 \\x50\\x00)。"""
        inv, fake = make_inv_with_response(build_response(0, b"\x00\x00"))
        inv.read_words(Device.D, 0, 1)
        assert fake.sent[:2] == b"\x50\x00"

    def test_word_response_little_endian(self):
        """応答のワード値はリトルエンディアン。0x1234 は \\x34\\x12 で来る。"""
        response = build_response(0, b"\x34\x12")
        inv, _ = make_inv_with_response(response)
        result = inv.read_words(Device.D, 0, 1)
        assert result[0] == 0x1234


class TestErrorPropagation:
    """終了コード != 0 で SlmpError が出るか。"""

    def test_h4031_raises(self):
        from fre800slmp import SlmpError
        response = build_response(0x4031)  # 範囲外デバイス
        inv, _ = make_inv_with_response(response)
        with pytest.raises(SlmpError) as exc_info:
            inv.read_words(Device.D, 0, 1)
        assert exc_info.value.end_code == 0x4031
