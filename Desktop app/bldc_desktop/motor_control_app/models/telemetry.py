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
