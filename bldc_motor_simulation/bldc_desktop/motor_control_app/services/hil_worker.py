"""HIL link worker: runs the BLDC model on the PC and talks binary to the STM32.

Single serial port topology
---------------------------
There is only ONE physical port (ST-LINK VCP = LPUART1) on the Nucleo in the
"No USB-Serial adapter" scenario. The STM32 speaks the binary HIL protocol on
that same port, so we:

  * read CMD frames from the STM32 (binary),
  * advance the embedded BLDC model by one control period,
  * write an FB frame back to the STM32 (binary),
  * emit a "DATA t=..." text line so the EXISTING bldc_desktop parse pipeline
    (telemetry.py -> dashboard widgets) renders the real model data unchanged.

The current PI / commutation still runs ON THE STM32 (as in hil_app.c); the
PC model only simulates the motor physics and returns hall/enc/rpm/currents.
"""

from __future__ import annotations

import queue
import re
import threading
import time

import serial
from PyQt6.QtCore import QThread, pyqtSignal

import protocol as P
from bldc_model import BLDC, MotorParams

# Control period [s] must match the STM32's HIL_APP_TS (default 100 us).
HIL_DEFAULT_TS = 100e-6
# Resolve the 20 kHz switched PWM with 50 substeps per PWM period.  The former
# dt=100 us skipped two complete PWM periods per plant step and turned every
# non-zero duty command into a full-bus ON command.
HIL_PLANT_DT = 1e-6
HIL_PWM_FREQUENCY = 20_000.0
# Host-side batching for the UI (avoid a flood of per-period signals).
HIL_EMIT_INTERVAL_S = 0.020
HIL_EMIT_MAX_LINES = 200
# These must match the firmware constants in hil_app.h.
HIL_DEFAULT_IREF = 4.0
HIL_FIRMWARE_KP = 0.1257
# Normal interactive HIL scenario: free rotor with constant + fan load.
HIL_LOCK_ROTOR_CURRENT_TEST = False


# hall (real-motor convention 1..6) -> (sector, high, low, valid)
# This mirrors current_pi_sim.c CurrentPi_DecodeHall exactly.
_DECODE_HALL = {
    1: (1, "A", "B", 1),
    2: (5, "C", "A", 1),
    3: (6, "C", "B", 1),
    4: (3, "B", "C", 1),
    5: (2, "A", "C", 1),
    6: (4, "B", "A", 1),
}

# Gate bit masks (match bldc_model AH/AL/BH/BL/CH/CL and hil_link.h).
G_AH, G_AL, G_BH, G_BL, G_CH, G_CL = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20


def _phase_char(phase: str) -> str:
    """Return the single-character phase token the UI's DATA regex expects."""
    return phase if phase in ("A", "B", "C") else "-"


def build_data_line(
    model,
    gates: int,
    iref: float,
    duty: float,
    measured_currents: tuple[float, float, float],
    enabled: bool = True,
) -> str:
    """Compose telemetry aligned to the feedback sample used by the STM32 PI."""
    hall = model.hall() & 7
    dec = _DECODE_HALL.get(hall, (0, "NONE", "NONE", 0))
    sector, high, low, valid = dec

    ia, ib, ic = measured_currents
    active = 0.0
    if gates & G_AH:
        active = ia
    elif gates & G_BH:
        active = ib
    elif gates & G_CH:
        active = ic

    err = iref - active
    # CMD duty is the PI output produced from this feedback sample.  Therefore
    # I = u - Kp*e reconstructs the firmware integrator (rounding <= 0.01%).
    integral = duty - HIL_FIRMWARE_KP * err
    bemf_v = model.v_float
    applied_v = model.vbus * duty

    return (
        f"DATA t={int(model.t * 1e6) // 1000} hall={hall} "
        f"sector={sector} high={_phase_char(high)} low={_phase_char(low)} "
        f"valid={valid} enc={model.encoder_count()} rpm={int(model.rpm())} "
        f"iref_ma={int(iref * 1000)} fake_i_ma={int(active * 1000)} "
        f"err_ma={int(err * 1000)} duty_x10={int(duty * 1000)} "
        f"integral_x10={int(integral * 1000)} bemf_mv={int(bemf_v * 1000)} "
        f"applied_mv={int(applied_v * 1000)} enabled={int(enabled)}\r\n"
    )


class HilWorker(QThread):
    """Own a serial link to the STM32 and run the PC-side motor model."""

    connected = pyqtSignal(str)
    lines_received = pyqtSignal(list)
    command_sent = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    connection_closed = pyqtSignal(str)

    _EXACT_COMMANDS = {"START", "COAST", "BRAKE", "FWD", "REV"}
    _IREF_RE = re.compile(r"^IREF\s+([0-9]+(?:\.[0-9]+)?)$")
    _MAX_PENDING_COMMANDS = 32

    def __init__(
        self,
        port: str,
        baud_rate: int,
        ts: float = HIL_DEFAULT_TS,
        vbus: float = 24.0,
        iref: float = HIL_DEFAULT_IREF,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._port = port
        self._baud_rate = baud_rate
        self._ts = ts
        self._iref = iref
        self._stop_requested = threading.Event()
        self._commands: queue.Queue[str] = queue.Queue(
            maxsize=self._MAX_PENDING_COMMANDS
        )
        self._enabled = True
        self._reverse = False
        self._brake = False
        self._ctrl_seq = 0
        self._control_dirty = True
        if ts < HIL_PLANT_DT:
            raise ValueError("Control period cannot be smaller than plant timestep")
        self._model = BLDC(
            MotorParams(Vdc=vbus),
            dt=HIL_PLANT_DT,
            pwm_freq=HIL_PWM_FREQUENCY,
            average_pwm=False,
        )
        self._model.set_load(
            T_load=0.01, k2=8e-7, lock=HIL_LOCK_ROTOR_CURRENT_TEST
        )

    def stop(self) -> None:
        self._stop_requested.set()

    def enqueue_command(self, command: str) -> bool:
        """Validate and queue an interactive HIL motor command."""
        normalized = command.strip().upper()
        match = self._IREF_RE.fullmatch(normalized)
        if normalized not in self._EXACT_COMMANDS and match is None:
            return False
        if match is not None and not 0.0 <= float(match.group(1)) <= 10.0:
            return False
        try:
            self._commands.put_nowait(normalized)
        except queue.Full:
            return False
        return True

    def run(self) -> None:
        serial_port: serial.Serial | None = None
        close_reason = "requested"
        pending: list[str] = []
        try:
            if self._stop_requested.is_set():
                return

            serial_port = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.005,
                write_timeout=0.50,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            serial_port.reset_input_buffer()
            time.sleep(0.05)
            serial_port.reset_input_buffer()
            self.connected.emit(self._port)

            parser = P.FrameParser()
            seq_rx = 0
            last_currents: tuple[float, float, float] | None = None
            last_emit = time.monotonic()

            self._write_pending_controls(serial_port)
            # Lockstep: wait for a CMD, run one model period, reply with FB.
            while not self._stop_requested.is_set():
                self._write_pending_controls(serial_port)
                chunk = serial_port.read(1024)
                if chunk:
                    for ftype, payload in parser.feed(chunk):
                        if ftype != P.T_CMD or len(payload) != P.CMD_LEN:
                            continue
                        c = P.unpack_cmd(payload)
                        seq_rx = c["seq"]
                        model = self._model

                        # This CMD was calculated by the STM32 from the previous
                        # FB sample. Emit the pair together so current, error,
                        # duty and integral share the same controller timestamp.
                        # COAST handshake frames are not PI outputs; excluding
                        # them avoids a fabricated integral point at startup.
                        active_drive = (
                            last_currents is not None
                            and c["mode"] == 1 and c["gates"] != 0
                        )
                        stopped_drive = (
                            last_currents is not None
                            and (not self._enabled or self._iref <= 0.0)
                        )
                        if active_drive or stopped_drive:
                            pending.append(build_data_line(
                                model, c["gates"],
                                self._iref if self._enabled else 0.0,
                                c["duty"][0], last_currents,
                                enabled=self._enabled,
                            ))

                        model.set_command(c["mode"], c["gates"], c["duty"])
                        model.advance(self._ts)

                        ia, ib, ic = model.measured_currents()
                        frame = P.pack_fb(
                            seq=seq_rx,
                            t_us=int(model.t * 1e6),
                            enc=model.encoder_count(),
                            speed_x10=int(model.rpm() * 10),
                            hall=model.hall(),
                            flags=(model.encoder_index() << 0),
                            ia_mA=ia * 1000, ib_mA=ib * 1000, ic_mA=ic * 1000,
                            vbus_mV=model.vbus * 1000,
                            vfloat_mV=model.v_float * 1000,
                            torque_uNm=int(model.Te * 1e6),
                        )
                        serial_port.write(frame)
                        last_currents = (ia, ib, ic)

                now = time.monotonic()
                if pending and now - last_emit >= HIL_EMIT_INTERVAL_S:
                    self.lines_received.emit(pending.copy())
                    pending.clear()
                    last_emit = now
                if len(pending) >= HIL_EMIT_MAX_LINES:
                    self.lines_received.emit(pending.copy())
                    pending.clear()
                    last_emit = now

        # A QThread otherwise exits silently on model/programming errors. Report
        # every normal exception to the UI so a link failure has a useful cause.
        except Exception as exc:
            if self._stop_requested.is_set():
                close_reason = "requested"
            else:
                close_reason = "error"
                self.error_occurred.emit(
                    f"Serial connection error on {self._port}: {exc}"
                )
        finally:
            if pending:
                self.lines_received.emit(pending.copy())
            if serial_port is not None and serial_port.is_open:
                try:
                    serial_port.close()
                except (serial.SerialException, OSError):
                    pass
            self.connection_closed.emit(close_reason)

    def _write_pending_controls(self, serial_port: serial.Serial) -> None:
        """Apply queued UI commands and send one combined CTRL frame."""
        reset_pi = False
        changed = self._control_dirty
        emitted: list[str] = []

        while not self._stop_requested.is_set():
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                break

            emitted.append(command)
            changed = True
            if command == "START":
                self._enabled = True
                self._brake = False
                reset_pi = True
            elif command == "COAST":
                self._enabled = False
                self._brake = False
                reset_pi = True
            elif command == "BRAKE":
                self._enabled = False
                self._brake = True
                reset_pi = True
            elif command == "FWD":
                self._reverse = False
                self._enabled = True
                self._brake = False
                reset_pi = True
            elif command == "REV":
                self._reverse = True
                self._enabled = True
                self._brake = False
                reset_pi = True
            else:
                match = self._IREF_RE.fullmatch(command)
                if match is not None:
                    self._iref = float(match.group(1))

        if not changed:
            return

        flags = 0
        if self._enabled:
            flags |= P.CTRL_ENABLE
        if self._reverse:
            flags |= P.CTRL_REVERSE
        if reset_pi:
            flags |= P.CTRL_RESET_PI
        if self._brake:
            flags |= P.CTRL_BRAKE
        self._ctrl_seq += 1
        frame = P.pack_ctrl(self._ctrl_seq, self._iref, flags)
        written = serial_port.write(frame)
        if written != len(frame):
            raise serial.SerialTimeoutException("Incomplete HIL CTRL frame")
        self._control_dirty = False
        for command in emitted:
            self.command_sent.emit(command)
