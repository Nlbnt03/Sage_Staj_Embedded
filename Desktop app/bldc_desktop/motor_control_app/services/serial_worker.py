"""Non-blocking serial transport implemented as a dedicated QThread."""

from __future__ import annotations

import queue
import re
import threading
import time

import serial
from PyQt6.QtCore import QThread, pyqtSignal


class SerialWorker(QThread):
    """Own a serial connection and perform all blocking I/O off the UI thread."""

    connected = pyqtSignal(str)
    line_received = pyqtSignal(str)
    command_sent = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    connection_closed = pyqtSignal(str)

    _EXACT_COMMANDS = {"STEP", "RESET", "STATUS"}
    _PERIOD_COMMAND_RE = re.compile(r"^PERIOD\s+(\d+)$")
    _MAX_PENDING_COMMANDS = 100
    _MAX_LINE_BYTES = 4096

    def __init__(self, port: str, baud_rate: int, parent=None) -> None:
        """Configure the worker; the port is opened later inside ``run``."""

        super().__init__(parent)
        self._port = port
        self._baud_rate = baud_rate
        self._stop_requested = threading.Event()
        self._commands: queue.Queue[str] = queue.Queue(
            maxsize=self._MAX_PENDING_COMMANDS
        )

    def enqueue_command(self, command: str) -> bool:
        """Validate and queue a command without blocking the calling thread."""

        normalized = command.strip().upper()
        if not self._is_valid_command(normalized):
            return False

        try:
            self._commands.put_nowait(normalized)
        except queue.Full:
            return False
        return True

    def stop(self) -> None:
        """Request a prompt, cooperative shutdown of the serial loop."""

        self._stop_requested.set()

    def run(self) -> None:
        """Open the port, exchange data, and close it safely on every exit path."""

        serial_port: serial.Serial | None = None
        close_reason = "requested"

        try:
            if self._stop_requested.is_set():
                return

            serial_port = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.10,
                write_timeout=0.50,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )

            # ST-LINK VCP, port kapalıyken eski telemetriyi kısa süre tamponda
            # tutabilir. Açılışta bu birikimi temizle; STM güncel Hall durumunu
            # en geç 500 ms içinde yeniden gönderecektir.
            serial_port.reset_input_buffer()
            time.sleep(0.05)
            serial_port.reset_input_buffer()
            self.connected.emit(self._port)

            buffer = bytearray()

            while not self._stop_requested.is_set():
                self._write_pending_commands(serial_port)

                chunk = serial_port.read(serial_port.in_waiting or 1)
                if not chunk:
                    continue
                buffer.extend(chunk)

                while b"\n" in buffer:
                    raw_line, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                    if line:
                        self.line_received.emit(line)

                if len(buffer) > self._MAX_LINE_BYTES:
                    # No newline ever arrived for this much data; drop it rather
                    # than let an unterminated stream grow the buffer forever.
                    buffer.clear()

        except (serial.SerialException, OSError, ValueError) as exc:
            if self._stop_requested.is_set():
                close_reason = "requested"
            else:
                close_reason = "error"
                self.error_occurred.emit(
                    f"Serial connection error on {self._port}: {exc}"
                )
        finally:
            if serial_port is not None and serial_port.is_open:
                try:
                    serial_port.close()
                except (serial.SerialException, OSError):
                    pass
            self.connection_closed.emit(close_reason)

    def _write_pending_commands(self, serial_port: serial.Serial) -> None:
        """Drain queued commands and write each using CRLF framing."""

        while not self._stop_requested.is_set():
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return

            payload = f"{command}\r\n".encode("ascii")
            written = serial_port.write(payload)
            if written != len(payload):
                raise serial.SerialTimeoutException(
                    f"Only {written} of {len(payload)} command bytes were written."
                )
            self.command_sent.emit(command)

    @classmethod
    def _is_valid_command(cls, command: str) -> bool:
        """Allow only the documented command vocabulary and safe period values."""

        if command in cls._EXACT_COMMANDS:
            return True

        match = cls._PERIOD_COMMAND_RE.fullmatch(command)
        if match is None:
            return False
        return 50 <= int(match.group(1)) <= 1000
