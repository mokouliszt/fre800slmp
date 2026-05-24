"""
FR-E800 SLMP クライアント (QnA互換 3Eフレーム / バイナリコード)。

参考: 三菱電機 FREQROL-E800 取扱説明書（通信編） §2.10
※Ethernet仕様品 / 安全通信仕様品 / IP67仕様品 はバイナリコードのみ対応。

事前のインバータ側設定:
  Pr.414  シーケンス機能動作選択  ≠ 0           (SLMPはシーケンス機能ONが前提)
  Pr.1427〜1430 のどれか            = 5010〜5013 (SLMP/TCPポート番号)
  Pr.1424 Ethernet通信ネットワーク番号
  Pr.1425 Ethernet通信局番
  Pr.1434〜1441 IPアドレス / サブネットマスク
"""

from __future__ import annotations

import socket
import struct
from typing import Optional

from .address import Device, parse_address


class SlmpError(Exception):
    """応答の終了コードが 0 以外だったときに送出される。"""

    def __init__(self, end_code: int):
        self.end_code = end_code
        super().__init__(f"SLMP end code = 0x{end_code:04X}")


class FRE800Slmp:
    """FR-E800シリーズ向け SLMPクライアント (3Eバイナリフレーム)。"""

    def __init__(
        self,
        host: str,
        port: int = 5010,
        transport: str = "tcp",
        network: int = 0x00,
        station: int = 0xFF,
        timeout: float = 3.0,
        monitoring_timer: int = 0x0010,
    ):
        """
        Parameters
        ----------
        host : str
            インバータのIPアドレス。
        port : int
            SLMPのポート。Pr.1427〜1430で設定した値 (5010〜5013)。
        transport : str
            ``"tcp"`` または ``"udp"``。同じポート番号でTCP/UDP両方を受け付ける。
            UDPの方が回線負荷は低いが、TCPの方が信頼性が高い (マニュアル §2.10)。
        network : int
            アクセス先のネットワーク番号。自局なら ``0x00``。
        station : int
            アクセス先の局番。自局 (network=0x00) なら ``0xFF``。
        timeout : float
            ソケット操作のタイムアウト秒数。
        monitoring_timer : int
            待ち時間 (0.25s単位)。``0x0010`` で約4秒。
        """
        if transport not in ("tcp", "udp"):
            raise ValueError("transport は 'tcp' か 'udp'")
        self.addr = (host, port)
        self.transport = transport
        self.network = network
        self.station = station
        self.timeout = timeout
        self.monitoring_timer = monitoring_timer
        self.sock: Optional[socket.socket] = None

    # --- 接続管理 -------------------------------------------------------
    def open(self) -> None:
        if self.transport == "tcp":
            s = socket.create_connection(self.addr, timeout=self.timeout)
        else:  # udp
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # connect() で相手を固定 → send/recv が使える (sendto/recvfrom 不要)
            s.connect(self.addr)
        s.settimeout(self.timeout)
        self.sock = s

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def __enter__(self) -> "FRE800Slmp":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- 伝文の組立て / 送受信 -----------------------------------------
    def _send(self, command: int, subcommand: int, request_data: bytes) -> bytes:
        assert self.sock is not None, "open() を呼んでから使う"
        # 監視タイマ(2) + コマンド(2) + サブコマンド(2) + 要求データ
        payload = (
            struct.pack("<HHH", self.monitoring_timer, command, subcommand)
            + request_data
        )
        # サブヘッダ(0x5000) + 局情報 + I/O番号 + マルチドロップ + 要求データ長
        header = (
            b"\x50\x00"                              # サブヘッダ (big endian, 固定)
            + bytes([self.network, self.station])    # ネット番号, 局番
            + struct.pack("<H", 0x03FF)              # 要求先ユニットI/O番号 (固定)
            + b"\x00"                                # マルチドロップ局番
            + struct.pack("<H", len(payload))        # 要求データ長
        )
        request = header + payload

        if self.transport == "tcp":
            self.sock.sendall(request)
            # TCPはストリームなので応答ヘッダ9バイト → 応答長を見て本体を読む
            resp_head = self._recv_exact(9)
            resp_len = struct.unpack("<H", resp_head[7:9])[0]
            body = self._recv_exact(resp_len)
        else:  # udp
            self.sock.send(request)
            # UDPは1データグラムで応答全部が届く (要求最大2047B / 応答最大2048B)
            datagram = self.sock.recv(4096)
            if len(datagram) < 11:
                raise ConnectionError(f"短すぎる応答: {len(datagram)} バイト")
            resp_len = struct.unpack("<H", datagram[7:9])[0]
            body = datagram[9:9 + resp_len]
            if len(body) != resp_len:
                raise ConnectionError(
                    f"応答データ長不一致: 期待 {resp_len}, 実際 {len(body)}"
                )

        end_code = struct.unpack("<H", body[:2])[0]
        if end_code != 0:
            raise SlmpError(end_code)
        return body[2:]

    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connection closed by inverter")
            buf += chunk
        return buf

    # --- デバイス番号(3バイト) + デバイスコード(1バイト) を組む --------
    @staticmethod
    def _device_field(device_code: int, head_no: int) -> bytes:
        # デバイス番号は3バイト・リトルエンディアン
        return head_no.to_bytes(3, "little") + bytes([device_code])

    # --- 低レベルAPI: ワード読み書き ----------------------------------
    def read_words(self, device_code: int, head_no: int, count: int) -> list[int]:
        """ワードデバイスを連続読出 (Device Read, ワード単位 0x0000)。"""
        req = self._device_field(device_code, head_no) + struct.pack("<H", count)
        resp = self._send(0x0401, 0x0000, req)
        return list(struct.unpack(f"<{count}H", resp))

    def write_words(self, device_code: int, head_no: int, values: list[int]) -> None:
        """ワードデバイスを連続書込 (Device Write, ワード単位 0x0000)。"""
        body = (
            self._device_field(device_code, head_no)
            + struct.pack(f"<H{len(values)}H", len(values), *values)
        )
        self._send(0x1401, 0x0000, body)

    # --- 低レベルAPI: ビット読み書き ----------------------------------
    def read_bits(self, device_code: int, head_no: int, count: int) -> list[bool]:
        """
        ビットデバイスを連続読出 (Device Read, ビット単位 0x0001)。

        1点を4bitで表現し、上位ニブルから順に詰めて返ってくる。
        """
        req = self._device_field(device_code, head_no) + struct.pack("<H", count)
        resp = self._send(0x0401, 0x0001, req)
        out: list[bool] = []
        for i in range(count):
            byte = resp[i // 2]
            nibble = (byte >> 4) if (i % 2 == 0) else (byte & 0x0F)
            out.append(nibble != 0)
        return out

    def write_bits(self, device_code: int, head_no: int, values: list[bool]) -> None:
        """ビットデバイスを連続書込 (Device Write, ビット単位 0x0001)。"""
        count = len(values)
        buf = bytearray((count + 1) // 2)  # 奇数点なら最後のニブルは0埋め
        for i, v in enumerate(values):
            nib = 0x1 if v else 0x0
            if i % 2 == 0:
                buf[i // 2] |= (nib << 4)
            else:
                buf[i // 2] |= nib
        body = (
            self._device_field(device_code, head_no)
            + struct.pack("<H", count) + bytes(buf)
        )
        self._send(0x1401, 0x0001, body)

    # --- 文字列アドレス指定の高レベルAPI -------------------------------
    def read(self, address: str):
        """
        単一点を読む。ビットデバイスなら ``bool``、ワードデバイスなら ``int``。

        例:
            >>> inv.read("D100")
            >>> inv.read("M10")
            >>> inv.read("W7")    # FR-E800のPr.7
        """
        a = parse_address(address)
        if a.kind == "bit":
            return self.read_bits(a.device_code, a.number, 1)[0]
        return self.read_words(a.device_code, a.number, 1)[0]

    def write(self, address: str, value) -> None:
        """
        単一点を書く。ビットは ``bool``、ワードは ``int`` を渡す。

        例:
            >>> inv.write("D100", 1234)
            >>> inv.write("M10", True)
        """
        a = parse_address(address)
        if a.kind == "bit":
            if not isinstance(value, bool):
                raise TypeError(f"{address} はビットデバイス: 値は bool で渡す")
            self.write_bits(a.device_code, a.number, [bool(value)])
        else:
            if isinstance(value, bool):
                raise TypeError(f"{address} はワードデバイス: 値は int で渡す")
            v = (value & 0xFFFF) if value < 0 else int(value)
            self.write_words(a.device_code, a.number, [v])

    def read_range(self, address: str, count: int):
        """
        先頭アドレスから連続読出。ビットなら ``list[bool]``、ワードなら ``list[int]``。

        例:
            >>> inv.read_range("D100", 5)
            >>> inv.read_range("M0", 16)
        """
        a = parse_address(address)
        if a.kind == "bit":
            return self.read_bits(a.device_code, a.number, count)
        return self.read_words(a.device_code, a.number, count)

    def write_range(self, address: str, values: list) -> None:
        """
        先頭アドレスから連続書込。

        例:
            >>> inv.write_range("D100", [1, 2, 3])
            >>> inv.write_range("M0", [True, False, True])
        """
        a = parse_address(address)
        if a.kind == "bit":
            if not all(isinstance(v, bool) for v in values):
                raise TypeError(f"{address} はビットデバイス: list[bool] を渡す")
            self.write_bits(a.device_code, a.number, list(values))
        else:
            if any(isinstance(v, bool) for v in values):
                raise TypeError(f"{address} はワードデバイス: list[int] を渡す")
            adjusted = [(v & 0xFFFF) if v < 0 else int(v) for v in values]
            self.write_words(a.device_code, a.number, adjusted)

    # --- リモート制御 / 形名読出し -------------------------------------
    def remote_run(self, force: bool = False, clear_devices: bool = False) -> None:
        """Remote Run コマンド (0x1001)。``force=True`` で強制実行モード。"""
        mode = 0x0300 if force else 0x0100
        clear = 0x01 if clear_devices else 0x00
        body = struct.pack("<H", mode) + bytes([clear, 0x00])
        self._send(0x1001, 0x0000, body)

    def remote_stop(self) -> None:
        """Remote Stop コマンド (0x1002)。"""
        self._send(0x1002, 0x0000, b"\x01\x00")

    def read_type_name(self) -> tuple[str, int]:
        """
        Read Type Name コマンド (0x0101)。

        FR-E800実機なら 16バイトの形名文字列 (例: "FR-E800-E") と
        形名コード ``0x054F`` (固定) が返る。
        """
        resp = self._send(0x0101, 0x0000, b"")
        name = resp[:16].decode("ascii").rstrip()
        type_code = struct.unpack("<H", resp[16:18])[0]
        return name, type_code

    # --- インバータ向けの便利ラッパ ------------------------------------
    def read_parameter(self, pr_no: int) -> int:
        """
        パラメータ Pr.N を読み出す。

        Pr.0〜999 → W0〜W999、Pr.1000〜1499 → W1000〜W1499。
        (マニュアル §2.10「リンクレジスタ - パラメータ」)
        """
        if not (0 <= pr_no <= 1499):
            raise ValueError("Pr番号は0〜1499")
        return self.read_words(Device.W, pr_no, 1)[0]

    def write_parameter(self, pr_no: int, value: int) -> None:
        """パラメータ Pr.N に書込み。"""
        if not (0 <= pr_no <= 1499):
            raise ValueError("Pr番号は0〜1499")
        if value < 0:
            value = value & 0xFFFF
        self.write_words(Device.W, pr_no, [value])


__all__ = ["FRE800Slmp", "SlmpError"]
