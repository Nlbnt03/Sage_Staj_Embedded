"""Main window for monitoring and controlling BLDC commutation telemetry."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from models import (
    TelemetrySample,
    is_telemetry_header,
    parse_firmware_reply,
    parse_firmware_status,
    parse_telemetry,
)
from services import SerialWorker, discover_serial_ports
from ui.widgets import PhaseCard, PhaseChart


class MainWindow(QMainWindow):
    """Coordinate the dashboard, protocol parser, and serial worker."""

    TELEMETRY_ONLY_WARNING = (
        "Firmware telemetry-only mode: commands may be ignored."
    )
    MAX_LOG_LINES = 5000

    def __init__(self) -> None:
        """Build the UI and scan ports without connecting automatically."""

        super().__init__()
        self.setWindowTitle("STM32 BLDC Commutation Monitor")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)

        self._worker: SerialWorker | None = None
        self._is_connected = False
        self._is_connecting = False
        self._is_disconnecting = False
        self._closing = False
        self._firmware_command_capable = False
        self._log_lines: deque[str] = deque(maxlen=self.MAX_LOG_LINES)
        self._command_buttons: list[QPushButton] = []

        self._build_ui()
        self._set_connection_visual("disconnected")
        self._set_firmware_status("Not connected", "#8b949e")
        self.refresh_ports()
        self._append_log("SYSTEM", "Application ready; no automatic connection was made.")
        self.statusBar().showMessage("Select a serial port and press Connect.")

    def _build_ui(self) -> None:
        """Assemble the control, state, chart, and UART log panels."""

        root_splitter = QSplitter(Qt.Orientation.Vertical)
        root_splitter.setChildrenCollapsible(False)

        dashboard_splitter = QSplitter(Qt.Orientation.Horizontal)
        dashboard_splitter.setChildrenCollapsible(False)
        dashboard_splitter.addWidget(self._build_control_panel())
        dashboard_splitter.addWidget(self._build_phase_panel())
        dashboard_splitter.addWidget(self._build_chart_panel())
        dashboard_splitter.setSizes([300, 350, 760])
        dashboard_splitter.setStretchFactor(0, 0)
        dashboard_splitter.setStretchFactor(1, 0)
        dashboard_splitter.setStretchFactor(2, 1)

        root_splitter.addWidget(dashboard_splitter)
        root_splitter.addWidget(self._build_terminal_panel())
        root_splitter.setSizes([620, 245])
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 0)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.addWidget(root_splitter)
        self.setCentralWidget(container)

    def _build_control_panel(self) -> QScrollArea:
        """Create serial settings and future firmware command controls."""

        content = QWidget()
        content.setMinimumWidth(275)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)

        connection_group = QGroupBox("SERIAL CONNECTION")
        connection_layout = QVBoxLayout(connection_group)

        port_label = QLabel("Port")
        port_label.setObjectName("sectionLabel")
        self.port_combo = QComboBox()
        self.port_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.port_combo.setMinimumContentsLength(22)

        baud_label = QLabel("Baud rate · 8-N-1 · no flow control")
        baud_label.setObjectName("sectionLabel")
        self.baud_combo = QComboBox()
        for baud in (9600, 19200, 38400, 57600, 115200, 230400, 460800):
            self.baud_combo.addItem(str(baud), baud)
        self.baud_combo.setCurrentText("115200")

        serial_buttons = QGridLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primaryButton")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setObjectName("dangerButton")
        self.refresh_button = QPushButton("Refresh Ports")
        serial_buttons.addWidget(self.connect_button, 0, 0)
        serial_buttons.addWidget(self.disconnect_button, 0, 1)
        serial_buttons.addWidget(self.refresh_button, 1, 0, 1, 2)

        self.connection_status_label = QLabel()
        self.connection_status_label.setMinimumHeight(25)
        self.firmware_status_label = QLabel()
        self.firmware_status_label.setWordWrap(True)

        connection_layout.addWidget(port_label)
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(baud_label)
        connection_layout.addWidget(self.baud_combo)
        connection_layout.addLayout(serial_buttons)
        connection_layout.addSpacing(5)
        connection_layout.addWidget(self.connection_status_label)
        connection_layout.addWidget(self.firmware_status_label)

        command_group = QGroupBox("COMMUTATION CONTROL")
        command_layout = QVBoxLayout(command_group)

        command_grid = QGridLayout()
        start_button = self._make_command_button("Start", "START", primary=True)
        stop_button = self._make_command_button("Stop", "STOP", danger=True)
        step_button = self._make_command_button("Next Step", "STEP")
        reset_button = self._make_command_button("Reset", "RESET")
        status_button = self._make_command_button("Query Status", "STATUS")
        command_grid.addWidget(start_button, 0, 0)
        command_grid.addWidget(stop_button, 0, 1)
        command_grid.addWidget(step_button, 1, 0)
        command_grid.addWidget(reset_button, 1, 1)
        command_grid.addWidget(status_button, 2, 0, 1, 2)

        period_label = QLabel("Step period (50–1000 ms)")
        period_label.setObjectName("sectionLabel")
        period_row = QHBoxLayout()
        self.period_slider = QSlider(Qt.Orientation.Horizontal)
        self.period_slider.setRange(50, 1000)
        self.period_slider.setSingleStep(10)
        self.period_slider.setPageStep(50)
        self.period_slider.setValue(200)
        self.period_spinbox = QSpinBox()
        self.period_spinbox.setRange(50, 1000)
        self.period_spinbox.setSingleStep(10)
        self.period_spinbox.setSuffix(" ms")
        self.period_spinbox.setValue(200)
        period_row.addWidget(self.period_slider, 1)
        period_row.addWidget(self.period_spinbox)

        self.apply_speed_button = QPushButton("Apply Speed")
        self.apply_speed_button.clicked.connect(self._apply_period)
        self._command_buttons.append(self.apply_speed_button)

        warning = QLabel(self.TELEMETRY_ONLY_WARNING)
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background-color: #2d2415; border: 1px solid #9e6a03;"
            "border-radius: 6px; color: #e3b341; padding: 8px;"
        )

        command_layout.addLayout(command_grid)
        command_layout.addSpacing(6)
        command_layout.addWidget(period_label)
        command_layout.addLayout(period_row)
        command_layout.addWidget(self.apply_speed_button)
        command_layout.addSpacing(6)
        command_layout.addWidget(warning)

        content_layout.addWidget(connection_group)
        content_layout.addWidget(command_group)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setMinimumWidth(285)
        scroll.setMaximumWidth(345)

        self.connect_button.clicked.connect(self._connect_serial)
        self.disconnect_button.clicked.connect(self._disconnect_serial)
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.period_slider.valueChanged.connect(self.period_spinbox.setValue)
        self.period_spinbox.valueChanged.connect(self.period_slider.setValue)
        return scroll

    def _build_phase_panel(self) -> QWidget:
        """Create the current-step display and three phase cards."""

        panel = QWidget()
        panel.setMinimumWidth(315)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 0, 5, 0)

        self.current_step_label = QLabel("Current Step: —")
        self.current_step_label.setObjectName("currentStepLabel")
        self.current_step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.phase_a_card = PhaseCard("A")
        self.phase_b_card = PhaseCard("B")
        self.phase_c_card = PhaseCard("C")

        layout.addWidget(self.current_step_label)
        layout.addSpacing(6)
        layout.addWidget(self.phase_a_card, 1)
        layout.addWidget(self.phase_b_card, 1)
        layout.addWidget(self.phase_c_card, 1)
        return panel

    def _build_chart_panel(self) -> QWidget:
        """Create the real-time plot panel."""

        group = QGroupBox("PHASE WAVEFORMS")
        layout = QVBoxLayout(group)
        self.phase_chart = PhaseChart()
        layout.addWidget(self.phase_chart)
        return group

    def _build_terminal_panel(self) -> QGroupBox:
        """Create the timestamped, bounded UART terminal."""

        group = QGroupBox("UART TERMINAL")
        layout = QVBoxLayout(group)

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.document().setMaximumBlockCount(self.MAX_LOG_LINES)
        self.terminal.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )

        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self._clear_log)
        save_button = QPushButton("Save Log")
        save_button.clicked.connect(self._save_log)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(clear_button)
        actions.addWidget(save_button)

        layout.addWidget(self.terminal, 1)
        layout.addLayout(actions)
        return group

    def _make_command_button(
        self,
        label: str,
        command: str,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        """Create and track a button for one documented firmware command."""

        button = QPushButton(label)
        if primary:
            button.setObjectName("primaryButton")
        elif danger:
            button.setObjectName("dangerButton")
        button.clicked.connect(
            lambda _checked=False, value=command: self._send_command(value)
        )
        self._command_buttons.append(button)
        return button

    def refresh_ports(self) -> None:
        """Rescan serial ports while preserving the current selection if possible."""

        previous_port = self.port_combo.currentData()
        self.port_combo.clear()

        try:
            ports = discover_serial_ports()
        except Exception as exc:  # Device enumeration errors vary by OS/driver.
            self.port_combo.addItem("Port scan failed", None)
            self._append_log("ERROR", f"Serial port scan failed: {exc}")
            QMessageBox.warning(
                self,
                "Port Scan Failed",
                f"Serial ports could not be scanned.\n\n{exc}",
            )
            self._update_control_availability()
            return

        if not ports:
            self.port_combo.addItem("No serial ports found", None)
            self._append_log("SYSTEM", "No serial ports were found.")
        else:
            for port in ports:
                self.port_combo.addItem(port.display_name, port.device)

            if previous_port:
                previous_index = self.port_combo.findData(previous_port)
                if previous_index >= 0:
                    self.port_combo.setCurrentIndex(previous_index)
            self._append_log("SYSTEM", f"Found {len(ports)} serial port(s).")

        self._update_control_availability()

    def _connect_serial(self) -> None:
        """Start a new worker; opening the port itself happens off the UI thread."""

        if self._worker is not None and self._worker.isRunning():
            return

        port = self.port_combo.currentData()
        baud_rate = self.baud_combo.currentData()
        if not port or not baud_rate:
            QMessageBox.warning(
                self,
                "Serial Port Required",
                "Select an available serial port before connecting.",
            )
            return

        self._is_connecting = True
        self._is_disconnecting = False
        self._is_connected = False
        self._firmware_command_capable = False
        self._set_connection_visual("connecting")
        self._set_firmware_status("Waiting for firmware telemetry…", "#e3b341")
        self._update_control_availability()

        worker = SerialWorker(str(port), int(baud_rate), self)
        worker.connected.connect(self._on_serial_connected)
        worker.line_received.connect(self._on_serial_line)
        worker.command_sent.connect(
            lambda command: self._append_log("TX", command)
        )
        worker.error_occurred.connect(self._on_serial_error)
        worker.connection_closed.connect(self._on_connection_closed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._append_log("SYSTEM", f"Connecting to {port} at {baud_rate} baud…")
        worker.start()

    def _disconnect_serial(self) -> None:
        """Request worker shutdown without waiting in the UI event handler."""

        if self._worker is None or not self._worker.isRunning():
            return
        self._append_log("SYSTEM", "Disconnect requested.")
        self._is_disconnecting = True
        self._set_connection_visual("disconnecting")
        self._update_control_availability()
        self._worker.stop()

    def _on_serial_connected(self, port: str) -> None:
        """Transition controls after the worker has successfully opened the port."""

        self._is_connecting = False
        self._is_disconnecting = False
        self._is_connected = True
        self._set_connection_visual("connected")
        self._set_firmware_status("Connected; awaiting telemetry", "#58a6ff")
        self._update_control_availability()
        self._append_log("SYSTEM", f"Connected to {port}.")
        self._append_log("WARNING", self.TELEMETRY_ONLY_WARNING)
        self.statusBar().showMessage(self.TELEMETRY_ONLY_WARNING, 8000)

    def _on_serial_line(self, line: str) -> None:
        """Classify one received line and update only validated state."""

        sample = parse_telemetry(line)
        if sample is not None:
            self._append_log("RX", line)
            self._apply_telemetry(sample)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Telemetry active · command support unknown", "#e3b341"
                )
            return

        if is_telemetry_header(line):
            self._append_log("RX", line)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Telemetry-only mode detected", "#e3b341"
                )
            return

        status = parse_firmware_status(line)
        if status is not None:
            self._append_log("RX", line)
            self._firmware_command_capable = True
            run_text = "RUNNING" if status.running else "STOPPED"
            self._set_firmware_status(
                f"Command-capable · {run_text} · {status.period_ms} ms",
                "#3fb950",
            )
            if 50 <= status.period_ms <= 1000:
                self.period_spinbox.setValue(status.period_ms)
            self.current_step_label.setText(f"Current Step: STEP {status.step}")
            return

        reply = parse_firmware_reply(line)
        if reply is not None:
            source = "RX" if reply.kind == "ok" else "FW ERROR"
            self._append_log(source, line)
            self._firmware_command_capable = True
            if reply.kind == "ok":
                detail = f" · {reply.message}" if reply.message else ""
                self._set_firmware_status(
                    f"Command-capable{detail}", "#3fb950"
                )
            else:
                self._set_firmware_status(
                    f"Firmware error · {reply.message or 'Unknown error'}",
                    "#f85149",
                )
                self.statusBar().showMessage(
                    f"Firmware rejected a command: {reply.message}", 8000
                )
            return

        # Unparsed data remains visible for diagnosis but cannot mutate state.
        self._append_log("RX?", line)

    def _apply_telemetry(self, sample: TelemetrySample) -> None:
        """Update all live indicators from one validated telemetry sample."""

        self.current_step_label.setText(f"Current Step: STEP {sample.step}")
        self.phase_a_card.set_state(sample.phase_a)
        self.phase_b_card.set_state(sample.phase_b)
        self.phase_c_card.set_state(sample.phase_c)
        self.phase_chart.append_sample(
            sample.phase_a,
            sample.phase_b,
            sample.phase_c,
        )

    def _send_command(self, command: str) -> None:
        """Queue a protocol command only while a live connection exists."""

        if (
            not self._is_connected
            or self._is_disconnecting
            or self._worker is None
            or not self._worker.isRunning()
        ):
            QMessageBox.warning(
                self,
                "Not Connected",
                "Connect to an STM32 serial port before sending commands.",
            )
            return

        if not self._worker.enqueue_command(command):
            QMessageBox.warning(
                self,
                "Command Not Queued",
                "The command is invalid or the send queue is full. Please try again.",
            )
            return

        self.statusBar().showMessage(self.TELEMETRY_ONLY_WARNING, 5000)

    def _apply_period(self) -> None:
        """Send the selected step period using the future PERIOD command."""

        self._send_command(f"PERIOD {self.period_spinbox.value()}")

    def _on_serial_error(self, message: str) -> None:
        """Report open/read/write failures without blocking worker cleanup."""

        self._append_log("ERROR", message)
        if not self._closing:
            QMessageBox.critical(
                self,
                "Serial Connection Error",
                f"The serial connection could not continue.\n\n{message}",
            )

    def _on_connection_closed(self, reason: str) -> None:
        """Restore disconnected controls after requested or unexpected closure."""

        was_connected = self._is_connected
        self._is_connected = False
        self._is_connecting = False
        self._is_disconnecting = False
        self._firmware_command_capable = False
        self._set_connection_visual("disconnected")
        self._set_firmware_status("Not connected", "#8b949e")
        self._update_control_availability()

        if reason == "error":
            self._append_log("SYSTEM", "Serial connection closed after an error.")
        elif was_connected:
            self._append_log("SYSTEM", "Serial connection closed.")

    def _on_worker_finished(self) -> None:
        """Release the completed worker and allow a new connection."""

        sender = self.sender()
        if sender is self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._update_control_availability()

    def _set_connection_visual(self, state: str) -> None:
        """Apply a clear color and label for the connection state."""

        states = {
            "connected": ("●  Connected", "#3fb950"),
            "connecting": ("●  Connecting…", "#e3b341"),
            "disconnecting": ("●  Disconnecting…", "#e3b341"),
            "disconnected": ("●  Disconnected", "#f85149"),
        }
        text, color = states[state]
        self.connection_status_label.setText(text)
        self.connection_status_label.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: 700;"
        )

    def _set_firmware_status(self, text: str, color: str) -> None:
        """Update the firmware capability/status label."""

        self.firmware_status_label.setText(f"Firmware: {text}")
        self.firmware_status_label.setStyleSheet(
            f"color: {color}; font-size: 12px;"
        )

    def _update_control_availability(self) -> None:
        """Keep connection and command controls consistent with current state."""

        busy = (
            self._is_connecting
            or self._is_connected
            or self._is_disconnecting
        )
        has_port = self.port_combo.currentData() is not None
        self.port_combo.setEnabled(not busy)
        self.baud_combo.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.connect_button.setEnabled(not busy and has_port)
        self.disconnect_button.setEnabled(
            (self._is_connecting or self._is_connected)
            and not self._is_disconnecting
        )
        for button in self._command_buttons:
            button.setEnabled(
                self._is_connected and not self._is_disconnecting
            )

    def _append_log(self, source: str, message: str) -> None:
        """Append one timestamped line while enforcing a memory bound."""

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] [{source}] {message}"
        self._log_lines.append(formatted)
        self.terminal.appendPlainText(formatted)

    def _clear_log(self) -> None:
        """Clear both the terminal widget and its save buffer."""

        self._log_lines.clear()
        self.terminal.clear()

    def _save_log(self) -> None:
        """Save the visible UART session to a user-selected UTF-8 file."""

        default_name = f"bldc_uart_{datetime.now():%Y%m%d_%H%M%S}.log"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save UART Log",
            default_name,
            "Log files (*.log);;Text files (*.txt);;All files (*)",
        )
        if not filename:
            return

        try:
            Path(filename).write_text(
                "\n".join(self._log_lines) + ("\n" if self._log_lines else ""),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Log Save Failed",
                f"The UART log could not be saved.\n\n{exc}",
            )
            return

        self.statusBar().showMessage(f"Log saved to {filename}", 6000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the serial worker before Qt destroys its thread object."""

        self._closing = True
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            if not self._worker.wait(1500):
                self._closing = False
                QMessageBox.warning(
                    self,
                    "Serial Port Busy",
                    "The serial worker is still closing. Please try again.",
                )
                event.ignore()
                return
        event.accept()
