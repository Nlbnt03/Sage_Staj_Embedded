"""
protocol.py
===========
PC <-> STM32 arasindaki ikili (binary) cerceve formati.

Cerceve:
    0xA5 0x5A | TYPE(1) | LEN(1) | PAYLOAD(LEN) | CRC16_LO | CRC16_HI
    CRC16-CCITT (poly 0x1021, init 0xFFFF), TYPE+LEN+PAYLOAD uzerinden.

TYPE 0x10  CMD  (STM32 -> PC) : inverter komutu
TYPE 0x11  FB   (PC -> STM32) : sensor geri beslemesi
TYPE 0x12  CFG  (STM32 -> PC) : yuk / vbus ayari (opsiyonel)
TYPE 0x13  LOG  (PC -> STM32) : bilgi (kullanilmiyor, rezerve)

Tum alanlar little-endian, paketlenmis (padding yok).
"""

import struct

SOF0, SOF1 = 0xA5, 0x5A
T_CMD, T_FB, T_CFG, T_CTRL = 0x10, 0x11, 0x12, 0x13

# --- payload formatlari -----------------------------------------------------
# CMD: seq(u32) mode(u8) gates(u8) da(u16) db(u16) dc(u16)   -> 12 bayt
CMD_FMT = "<IBBHHH"
CMD_LEN = struct.calcsize(CMD_FMT)

# FB: seq(u32) t_us(u32) enc(i32) speed_x10(i32) hall(u8) flags(u8)
#     ia_mA(i16) ib_mA(i16) ic_mA(i16) vbus_mV(u16) vfloat_mV(i16) torque_uNm(i32)
FB_FMT = "<IIiiBBhhhHhi"
FB_LEN = struct.calcsize(FB_FMT)

# CFG: load_uNm(i32) vbus_mV(u16) flags(u8) reserved(u8)
CFG_FMT = "<IHBB"
CFG_LEN = struct.calcsize(CFG_FMT)

# CTRL: seq(u32) iref_mA(u16) flags(u8) reserved(u8) -> 8 bayt
CTRL_FMT = "<IHBB"
CTRL_LEN = struct.calcsize(CTRL_FMT)
CTRL_ENABLE = 0x01
CTRL_REVERSE = 0x02
CTRL_RESET_PI = 0x04
CTRL_BRAKE = 0x08


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def build(ftype: int, payload: bytes) -> bytes:
    head = bytes((ftype, len(payload)))
    c = crc16(head + payload)
    return bytes((SOF0, SOF1)) + head + payload + struct.pack("<H", c)


def pack_cmd(seq, mode, gates, da=0, db=0, dc=0) -> bytes:
    """duty degerleri 0..10000 (= %0..%100)"""
    return build(T_CMD, struct.pack(CMD_FMT, seq & 0xFFFFFFFF, mode & 0xFF,
                                    gates & 0xFF, da & 0xFFFF, db & 0xFFFF, dc & 0xFFFF))


def unpack_cmd(payload: bytes):
    seq, mode, gates, da, db, dc = struct.unpack(CMD_FMT, payload)
    return dict(seq=seq, mode=mode, gates=gates,
                duty=(da / 10000.0, db / 10000.0, dc / 10000.0))


def pack_ctrl(seq: int, iref_a: float, flags: int) -> bytes:
    """Build a UI -> STM32 run/direction/current-reference control frame."""
    iref_ma = max(0, min(10_000, int(round(iref_a * 1000.0))))
    payload = struct.pack(
        CTRL_FMT, seq & 0xFFFFFFFF, iref_ma, flags & 0xFF, 0
    )
    return build(T_CTRL, payload)


def pack_fb(seq, t_us, enc, speed_x10, hall, flags,
            ia_mA, ib_mA, ic_mA, vbus_mV, vfloat_mV, torque_uNm) -> bytes:
    def s16(x): return max(-32768, min(32767, int(x)))
    return build(T_FB, struct.pack(
        FB_FMT, seq & 0xFFFFFFFF, t_us & 0xFFFFFFFF, int(enc), int(speed_x10),
        hall & 0xFF, flags & 0xFF, s16(ia_mA), s16(ib_mA), s16(ic_mA),
        max(0, min(65535, int(vbus_mV))), s16(vfloat_mV), int(torque_uNm)))


def unpack_fb(payload: bytes):
    (seq, t_us, enc, sp10, hall, flags,
     ia, ib, ic, vbus, vfl, tq) = struct.unpack(FB_FMT, payload)
    return dict(seq=seq, t_us=t_us, enc=enc, rpm=sp10 / 10.0, hall=hall, flags=flags,
                ia=ia / 1000.0, ib=ib / 1000.0, ic=ic / 1000.0,
                vbus=vbus / 1000.0, vfloat=vfl / 1000.0, torque=tq / 1e6)


class FrameParser:
    """Bayt akisindan cerceve cikaran durum makinesi (STM32 tarafiyla ayni mantik)."""

    def __init__(self):
        self.buf = bytearray()
        self.errors = 0

    def feed(self, data: bytes):
        """Gelen baytlari ekler ve tamamlanan (type, payload) cerceveleri dondurur."""
        self.buf.extend(data)
        out = []
        while True:
            # SOF ara
            idx = self.buf.find(bytes((SOF0, SOF1)))
            if idx < 0:
                if len(self.buf) > 1:
                    del self.buf[:-1]
                break
            if idx > 0:
                del self.buf[:idx]
                self.errors += 1
            if len(self.buf) < 4:
                break
            ftype = self.buf[2]
            ln = self.buf[3]
            total = 4 + ln + 2
            if len(self.buf) < total:
                break
            payload = bytes(self.buf[4:4 + ln])
            rx = self.buf[4 + ln] | (self.buf[5 + ln] << 8)
            if crc16(bytes(self.buf[2:4]) + payload) == rx:
                out.append((ftype, payload))
                del self.buf[:total]
            else:
                self.errors += 1
                del self.buf[:2]
        return out
