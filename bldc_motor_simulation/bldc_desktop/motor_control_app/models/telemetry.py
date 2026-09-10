"""Typed models and strict parsers for the STM32 text protocol."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """A validated six-step commutation telemetry sample."""

    step: int
    phase_a: int
    phase_b: int
    phase_c: int


@dataclass(frozen=True, slots=True)
class HallTelemetrySample:
    """A validated Hall-sensor six-step commutation telemetry sample."""

    raw: str
    step: int
    direction: Literal["FWD", "REV", "UNKNOWN"]
    rpm: int
    phase_a: int
    phase_b: int
    phase_c: int
    valid: bool


@dataclass(frozen=True, slots=True)
class RawHallDebugSample:
    """A validated sample from the raw ``HALL: <raw> (state=<n>)`` debug format."""

    raw: str
    step: int
    valid: bool


@dataclass(frozen=True, slots=True)
class EncoderSample:
    """A validated sample from the ``ENC: cnt=.. deg=.. rpm=..`` debug format."""

    count: int
    degrees: int
    rpm: int


@dataclass(frozen=True, slots=True)
class PidTelemetrySample:
    """One validated, scaled sample from the PID simulation telemetry stream."""

    time_ms: int
    target_rpm: int
    rpm: int
    error_rpm: int
    duty_percent: float
    model_rpm: int
    encoder_count: int
    integral: float
    kp: float
    ki: float
    kd: float
    load_rpm: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class CurrentPiTelemetrySample:
    """One validated sample from the combined commutation/current PI stream."""

    time_ms: int
    hall_state: int
    sector: int
    high_phase: str
    low_phase: str
    valid: bool
    encoder_count: int
    rpm: int
    current_reference_a: float
    measured_current_a: float
    error_current_a: float
    duty_percent: float
    integral_percent: float
    bemf_v: float
    applied_voltage_v: float
    enabled: bool


@dataclass(frozen=True, slots=True)
class FirmwareStatus:
    """Structured representation of a future STATUS response."""

    running: bool
    period_ms: int
    step: int


@dataclass(frozen=True, slots=True)
class FirmwareReply:
    """Structured representation of an OK or ERR firmware response."""

    kind: Literal["ok", "error"]
    message: str


_TELEMETRY_RE = re.compile(
    r"^\s*STEP\s+(?P<step>[1-6])\s*\|\s*"
    r"A\s*:\s*(?P<a>-1|0|1)\s*\|\s*"
    r"B\s*:\s*(?P<b>-1|0|1)\s*\|\s*"
    r"C\s*:\s*(?P<c>-1|0|1)\s*$",
    re.IGNORECASE,
)

_STATUS_RE = re.compile(
    r"^\s*STATUS\s+RUN=(?P<run>[01])\s+"
    r"PERIOD=(?P<period>\d+)\s+STEP=(?P<step>[1-6])\s*$",
    re.IGNORECASE,
)

_REPLY_RE = re.compile(
    r"^\s*(?P<kind>OK|ERR)(?:\s+(?P<message>.+?))?\s*$",
    re.IGNORECASE,
)

_TELEMETRY_HEADER_RE = re.compile(
    r"^\s*MOTOR\s+FAZ\s+SIMULASYONU\s*\|\s*"
    r"1=HIGH\s+-1=LOW\s+0=FLOAT\s*$",
    re.IGNORECASE,
)

_HALL_TELEMETRY_RE = re.compile(
    r"^\s*HALL,raw=(?P<raw>[01]{3}),step=(?P<step>[0-6]),"
    r"dir=(?P<dir>FWD|REV|UNKNOWN),rpm=(?P<rpm>\d+),"
    r"a=(?P<a>-1|0|1),b=(?P<b>-1|0|1),c=(?P<c>-1|0|1),"
    r"valid=(?P<valid>[01])\s*$",
    re.IGNORECASE,
)

_RAW_HALL_DEBUG_RE = re.compile(
    r"^\s*HALL:\s*(?P<raw>[01]{3})\s*\(state=(?P<state>[0-7])\)\s*$",
    re.IGNORECASE,
)

_ENCODER_DEBUG_RE = re.compile(
    r"^\s*ENC:\s*cnt=(?P<cnt>-?\d+)\s+deg=(?P<deg>-?\d+)\s+rpm=(?P<rpm>-?\d+)\s*$",
    re.IGNORECASE,
)

_PID_TELEMETRY_RE = re.compile(
    r"^\s*SIM\s+"
    r"t=(?P<time>\d+)\s+"
    r"target=(?P<target>-?\d+)\s+"
    r"rpm=(?P<rpm>-?\d+)\s+"
    r"err=(?P<error>-?\d+)\s+"
    r"duty_x10=(?P<duty>-?\d+)\s+"
    r"model_rpm=(?P<model>-?\d+)\s+"
    r"enc_cnt=(?P<encoder>-?\d+)\s+"
    r"integral_x10=(?P<integral>-?\d+)\s+"
    r"kp_x10000=(?P<kp>-?\d+)\s+"
    r"ki_x10000=(?P<ki>-?\d+)\s+"
    r"kd_x10000=(?P<kd>-?\d+)\s+"
    r"load_rpm=(?P<load>-?\d+)\s+"
    r"enabled=(?P<enabled>[01])\s*$",
    re.IGNORECASE,
)

_CURRENT_PI_TELEMETRY_RE = re.compile(
    r"^\s*DATA\s+"
    r"t=(?P<time>\d+)\s+"
    r"hall=(?P<hall>[0-7])\s+"
    r"sector=(?P<sector>[0-6])\s+"
    r"high=(?P<high>A|B|C|NONE|-)\s+"
    r"low=(?P<low>A|B|C|NONE|-)\s+"
    r"valid=(?P<valid>[01])\s+"
    r"enc=(?P<encoder>-?\d+)\s+"
    r"rpm=(?P<rpm>-?\d+)\s+"
    r"iref_ma=(?P<reference>-?\d+)\s+"
    r"fake_i_ma=(?P<measured>-?\d+)\s+"
    r"err_ma=(?P<error>-?\d+)\s+"
    r"duty_x10=(?P<duty>-?\d+)\s+"
    r"integral_x10=(?P<integral>-?\d+)\s+"
    r"bemf_mv=(?P<bemf>-?\d+)\s+"
    r"applied_mv=(?P<applied>-?\d+)\s+"
    r"enabled=(?P<enabled>[01])\s*$",
    re.IGNORECASE,
)

_HALL_TELEMETRY_HEADER_RE = re.compile(
    r"^\s*BLDC\s+HALL\s+TELEMETRY\s*\|\s*HALL=ABC\s*\|\s*"
    r"A/B/C:\s*1=HIGH\s+-1=LOW\s+0=FLOAT\s*$",
    re.IGNORECASE,
)

_PHASE_STATES_TO_STEP = {
    (1, -1, 0): 1,
    (1, 0, -1): 2,
    (0, 1, -1): 3,
    (-1, 1, 0): 4,
    (-1, 0, 1): 5,
    (0, -1, 1): 6,
}

_HALL_RAW_TO_STEP = {
    "001": 1,
    "101": 2,
    "100": 3,
    "110": 4,
    "010": 5,
    "011": 6,
}

# Bench motorunun elle çevrilmesiyle doğrulanmış gerçek fiziksel Hall sırası
# 110->010->011->001->101->100 (tekrarlı); bu, genel _HALL_RAW_TO_STEP
# eşlemesinin 4,5,6,1,2,3 şeklindeki aynı döngüsüdür, yalnızca başlangıç
# noktası 110'un STEP1 sayılacağı şekilde kaydırılmıştır. Bir kaydırma
# olduğundan fiziksel komşuluğu korur; yalnızca parse_raw_hall_debug
# tarafından, terminaldeki ham Hall verisini daha okunaklı bir 1..6 sırasında
# göstermek için kullanılır.
_BENCH_HALL_DISPLAY_STEP = {
    "110": 1,
    "010": 2,
    "011": 3,
    "001": 4,
    "101": 5,
    "100": 6,
}


def parse_telemetry(line: str) -> TelemetrySample | None:
    """Parse one telemetry line, returning ``None`` when it is invalid."""

    match = _TELEMETRY_RE.fullmatch(line)
    if match is None:
        return None

    return TelemetrySample(
        step=int(match.group("step")),
        phase_a=int(match.group("a")),
        phase_b=int(match.group("b")),
        phase_c=int(match.group("c")),
    )


def commutation_step_from_phases(
    phase_a: int, phase_b: int, phase_c: int
) -> int | None:
    """Return the six-step index represented by one A/B/C phase tuple."""

    return _PHASE_STATES_TO_STEP.get((phase_a, phase_b, phase_c))


def parse_firmware_status(line: str) -> FirmwareStatus | None:
    """Parse a future firmware STATUS response."""

    match = _STATUS_RE.fullmatch(line)
    if match is None:
        return None

    return FirmwareStatus(
        running=match.group("run") == "1",
        period_ms=int(match.group("period")),
        step=int(match.group("step")),
    )


def parse_firmware_reply(line: str) -> FirmwareReply | None:
    """Parse future ``OK ...`` and ``ERR ...`` responses."""

    match = _REPLY_RE.fullmatch(line)
    if match is None:
        return None

    kind = "ok" if match.group("kind").upper() == "OK" else "error"
    return FirmwareReply(kind=kind, message=(match.group("message") or "").strip())


def is_telemetry_header(line: str) -> bool:
    """Return whether a line is the current firmware's telemetry header."""

    return _TELEMETRY_HEADER_RE.fullmatch(line) is not None


def parse_hall_telemetry(line: str) -> HallTelemetrySample | None:
    """Parse one Hall-sensor telemetry line, returning ``None`` when it is invalid."""

    match = _HALL_TELEMETRY_RE.fullmatch(line)
    if match is None:
        return None

    sample = HallTelemetrySample(
        raw=match.group("raw"),
        step=int(match.group("step")),
        direction=match.group("dir").upper(),  # type: ignore[arg-type]
        rpm=int(match.group("rpm")),
        phase_a=int(match.group("a")),
        phase_b=int(match.group("b")),
        phase_c=int(match.group("c")),
        valid=match.group("valid") == "1",
    )

    expected_step = _HALL_RAW_TO_STEP.get(sample.raw)
    phase_step = commutation_step_from_phases(
        sample.phase_a, sample.phase_b, sample.phase_c
    )

    if sample.valid:
        if expected_step != sample.step or phase_step != sample.step:
            return None
    elif sample.raw not in {"000", "111"} or sample.step != 0:
        return None

    return sample


def parse_raw_hall_debug(line: str) -> RawHallDebugSample | None:
    """Parse one ``HALL: <raw> (state=<n>)`` bench-test debug line.

    ``step`` uses ``_BENCH_HALL_DISPLAY_STEP`` so the chart reads as a plain
    1..6 cycle starting from this bench motor's first observed Hall code,
    rather than the firmware's raw 0-7 state number or the documented
    protocol's differently-started ``_HALL_RAW_TO_STEP`` labeling.
    """

    match = _RAW_HALL_DEBUG_RE.fullmatch(line)
    if match is None:
        return None

    raw = match.group("raw")
    if int(raw, 2) != int(match.group("state")):
        return None

    step = _BENCH_HALL_DISPLAY_STEP.get(raw, 0)
    return RawHallDebugSample(raw=raw, step=step, valid=step != 0)


def parse_encoder_telemetry(line: str) -> EncoderSample | None:
    """Parse one ``ENC: cnt=.. deg=.. rpm=..`` bench-test debug line."""

    match = _ENCODER_DEBUG_RE.fullmatch(line)
    if match is None:
        return None

    return EncoderSample(
        count=int(match.group("cnt")),
        degrees=int(match.group("deg")),
        rpm=int(match.group("rpm")),
    )


def parse_pid_telemetry(line: str) -> PidTelemetrySample | None:
    """Parse and scale one ``SIM t=...`` PID telemetry line."""

    match = _PID_TELEMETRY_RE.fullmatch(line)
    if match is None:
        return None

    return PidTelemetrySample(
        time_ms=int(match.group("time")),
        target_rpm=int(match.group("target")),
        rpm=int(match.group("rpm")),
        error_rpm=int(match.group("error")),
        duty_percent=int(match.group("duty")) / 10.0,
        model_rpm=int(match.group("model")),
        encoder_count=int(match.group("encoder")),
        integral=int(match.group("integral")) / 10.0,
        kp=int(match.group("kp")) / 10000.0,
        ki=int(match.group("ki")) / 10000.0,
        kd=int(match.group("kd")) / 10000.0,
        load_rpm=int(match.group("load")),
        enabled=match.group("enabled") == "1",
    )


def parse_current_pi_telemetry(line: str) -> CurrentPiTelemetrySample | None:
    """Parse and scale one real ``DATA t=...`` current PI telemetry line."""

    match = _CURRENT_PI_TELEMETRY_RE.fullmatch(line)
    if match is None:
        return None

    high_phase = match.group("high").upper()
    low_phase = match.group("low").upper()
    if high_phase in {"A", "B", "C"} and high_phase == low_phase:
        return None

    return CurrentPiTelemetrySample(
        time_ms=int(match.group("time")),
        hall_state=int(match.group("hall")),
        sector=int(match.group("sector")),
        high_phase=high_phase,
        low_phase=low_phase,
        valid=match.group("valid") == "1",
        encoder_count=int(match.group("encoder")),
        rpm=int(match.group("rpm")),
        current_reference_a=int(match.group("reference")) / 1000.0,
        measured_current_a=int(match.group("measured")) / 1000.0,
        error_current_a=int(match.group("error")) / 1000.0,
        duty_percent=int(match.group("duty")) / 10.0,
        integral_percent=int(match.group("integral")) / 10.0,
        bemf_v=int(match.group("bemf")) / 1000.0,
        applied_voltage_v=int(match.group("applied")) / 1000.0,
        enabled=match.group("enabled") == "1",
    )


def is_hall_telemetry_header(line: str) -> bool:
    """Return whether a line is the current firmware's Hall telemetry header."""

    return _HALL_TELEMETRY_HEADER_RE.fullmatch(line) is not None
