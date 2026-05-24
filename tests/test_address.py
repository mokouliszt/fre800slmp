"""アドレスパーサのユニットテスト (ネットワーク接続不要)。"""

import pytest

from fre800slmp import Device, parse_address


class TestParseValid:
    """正常系: 文字列が正しいAddressに変換される。"""

    def test_word_decimal(self):
        a = parse_address("D100")
        assert a.device_code == Device.D
        assert a.number == 100
        assert a.kind == "word"

    def test_w_is_decimal_per_fr_e800_manual(self):
        """FR-E800のWは10進。Pr.902 ⇄ W902。"""
        a = parse_address("W902")
        assert a.device_code == Device.W
        assert a.number == 902  # 16進だと 0x902 = 2306 になってしまう
        assert a.kind == "word"

    def test_w_small_number(self):
        """Pr.7 ⇄ W7。"""
        a = parse_address("W7")
        assert a.device_code == Device.W
        assert a.number == 7

    def test_x_is_hex(self):
        """X はマニュアル §2.10 で H0〜H7F (16進)。"""
        a = parse_address("X1F")
        assert a.device_code == Device.X
        assert a.number == 0x1F  # = 31

    def test_y_is_hex(self):
        a = parse_address("Y20")
        assert a.device_code == Device.Y
        assert a.number == 0x20  # = 32

    def test_bit_device_m(self):
        a = parse_address("M10")
        assert a.device_code == Device.M
        assert a.number == 10
        assert a.kind == "bit"

    def test_special_relay_two_char_prefix(self):
        """SMはSの後にMで2文字プレフィックス。SMをMと誤認しないこと。"""
        a = parse_address("SM400")
        assert a.device_code == Device.SM
        assert a.number == 400
        assert a.kind == "bit"

    def test_special_register(self):
        a = parse_address("SD210")
        assert a.device_code == Device.SD
        assert a.number == 210
        assert a.kind == "word"

    def test_timer_current_value(self):
        a = parse_address("TN5")
        assert a.device_code == Device.TN
        assert a.kind == "word"

    def test_counter_contact(self):
        a = parse_address("CS3")
        assert a.device_code == Device.CS
        assert a.kind == "bit"

    def test_lowercase_input_ok(self):
        a = parse_address("d100")
        assert a.device_code == Device.D
        assert a.number == 100

    def test_mixed_case(self):
        a = parse_address("Sm400")
        assert a.device_code == Device.SM
        assert a.number == 400

    def test_whitespace_stripped(self):
        a = parse_address("  D100  ")
        assert a.number == 100


class TestParseInvalid:
    """異常系: ValueErrorが出る。"""

    @pytest.mark.parametrize("bad", [
        "Z100",      # 未知デバイス
        "100",       # デバイスプレフィックスなし
        "M-1",       # 負値
        "",          # 空文字
        "D",         # 番号なし
        "DG",        # 番号部に英字 (Dデバイスは10進)
    ])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            parse_address(bad)

    def test_w_with_hex_chars(self):
        """W は10進規約。Aを含む文字列は10進として失敗する。"""
        with pytest.raises(ValueError):
            parse_address("WAB")


class TestAddressDataclass:
    """Address dataclass の挙動。"""

    def test_frozen(self):
        a = parse_address("D100")
        with pytest.raises(Exception):
            a.number = 200  # type: ignore[misc]

    def test_raw_uppercased(self):
        a = parse_address("d100")
        assert a.raw == "D100"
