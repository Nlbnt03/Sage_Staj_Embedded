"""Main window for monitoring and controlling BLDC commutation telemetry."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from time import monotonic

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
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
    CurrentPiTelemetrySample,
    EncoderSample,
    HallTelemetrySample,
    PidTelemetrySample,
    RawHallDebugSample,
    TelemetrySample,
    is_hall_telemetry_header,
    is_telemetry_header,
    parse_encoder_telemetry,
    parse_current_pi_telemetry,
    parse_firmware_reply,
    parse_firmware_status,
    parse_hall_telemetry,
    parse_pid_telemetry,
    parse_raw_hall_debug,
    parse_telemetry,
)
from services import HilWorker, SerialWorker, discover_serial_ports
from ui.widgets import (
    CommutationAnimation,
    CurrentPidChartsDialog,
    EncoderChart,
    HallChart,
    HallPanel,
    PhaseCard,
    PhaseChart,
)


class MainWindow(QMainWindow):
    """Coordinate the dashboard, protocol parser, and serial worker."""

    TELEMETRY_ONLY_WARNING = (
        "Automatic telemetry mode: STM32 commands are not required."
    )
    MAX_LOG_LINES = 5000
    CURRENT_PI_LOG_INTERVAL_SECONDS = 0.100

    def __init__(self) -> None:
        """Build the UI and scan ports without connecting automatically."""

        super().__init__()
        self.setWindowTitle("STM32 BLDC Commutation Monitor")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)

        self._worker: QThread | None = None
        self._is_connected = False
        self._is_connecting = False
        self._is_disconnecting = False
        self._closing = False
        self._firmware_command_capable = False
        self._log_lines: deque[str] = deque(maxlen=self.MAX_LOG_LINES)
        self._command_buttons: list[QPushButton] = []
        self._pid_value_labels: dict[str, QLabel] = {}
        self._last_invalid_raw_logged: str | None = None
        self._current_pi_packets_since_log = 0
        self._last_current_pi_log_at = 0.0
        self.current_pid_charts = CurrentPidChartsDialog(self)

        self._build_ui()
        self._set_connection_visual("disconnected")
        self._set_firmware_status("Not connected", "#8b949e")
        self.refresh_ports()
        self._append_log("SYSTEM", "Application ready; no automatic connection was made.")
        self.statusBar().showMessage("Select a serial port and press Connect.")

    def _build_ui(self) -> None:
        """Assemble the control, state, chart, and UART log panels."""

        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_splitter.setChildrenCollapsible(False)

        left_dashboard = QSplitter(Qt.Orientation.Horizontal)
        left_dashboard.setChildrenCollapsible(False)
        left_dashboard.addWidget(self._build_control_panel())
        left_dashboard.addWidget(self._build_phase_panel())
        left_dashboard.setSizes([300, 350])
        left_dashboard.setStretchFactor(0, 0)
        left_dashboard.setStretchFactor(1, 1)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.addWidget(left_dashboard)
        left_splitter.addWidget(self._build_terminal_panel())
        left_splitter.setSizes([620, 245])
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 0)

        root_splitter.addWidget(left_splitter)
        root_splitter.addWidget(self._build_chart_panel())
        root_splitter.setSizes([650, 760])
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)

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
        content_layout.setSpacing(6)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        connection_group = QGroupBox("SERIAL CONNECTION")
        connection_layout = QVBoxLayout(connection_group)
        connection_layout.setSpacing(4)

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
        for baud in (
            9600,
            19200,
            38400,
            57600,
            115200,
            230400,
            460800,
            921600,
            1000000,
            1500000,
            2000000,
            3000000,
        ):
            self.baud_combo.addItem(str(baud), baud)
        self.baud_combo.setCurrentText("115200")

        serial_buttons = QGridLayout()
        serial_buttons.setSpacing(5)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primaryButton")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setObjectName("dangerButton")
        self.refresh_button = QPushButton("Refresh Ports")
        serial_buttons.addWidget(self.connect_button, 0, 0)
        serial_buttons.addWidget(self.disconnect_button, 0, 1)
        serial_buttons.addWidget(self.refresh_button, 1, 0, 1, 2)

        self.connection_status_label = QLabel()
        self.connection_status_label.setMinimumHeight(18)
        self.firmware_status_label = QLabel()
        self.firmware_status_label.setWordWrap(True)

        connection_layout.addWidget(port_label)
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(baud_label)
        connection_layout.addWidget(self.baud_combo)
        connection_layout.addLayout(serial_buttons)
        connection_layout.addSpacing(3)
        connection_layout.addWidget(self.connection_status_label)
        connection_layout.addWidget(self.firmware_status_label)

        pid_group = self._build_pid_panel()

        command_group = QGroupBox("COMMUTATION CONTROL")
        command_layout = QVBoxLayout(command_group)
        command_layout.setSpacing(4)

        command_grid = QGridLayout()
        command_grid.setSpacing(5)
        step_button = self._make_command_button("Next Step", "STEP")
        reset_button = self._make_command_button("Reset", "RESET")
        status_button = self._make_command_button("Query Status", "STATUS")
        command_grid.addWidget(step_button, 0, 0)
        command_grid.addWidget(reset_button, 0, 1)
        command_grid.addWidget(status_button, 1, 0, 1, 2)

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
            "border-radius: 6px; color: #e3b341; padding: 6px; font-size: 11px;"
        )

        command_layout.addLayout(command_grid)
        command_layout.addSpacing(3)
        command_layout.addWidget(period_label)
        command_layout.addLayout(period_row)
        command_layout.addWidget(self.apply_speed_button)
        command_layout.addSpacing(3)
        command_layout.addWidget(warning)
        command_group.setVisible(False)

        content_layout.addWidget(connection_group)
        content_layout.addWidget(self._build_hil_motor_control())
        content_layout.addWidget(pid_group)
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

    def _build_hil_motor_control(self) -> QGroupBox:
        """Build controls carried by the binary PC -> STM32 CTRL frame."""
        group = QGroupBox("HIL MOTOR CONTROL")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)

        run_grid = QGridLayout()
        start = self._make_command_button("Start", "START")
        coast = self._make_command_button("Coast", "COAST")
        brake = self._make_command_button("Brake", "BRAKE")
        forward = self._make_command_button("Forward", "FWD")
        reverse = self._make_command_button("Reverse", "REV")
        run_grid.addWidget(start, 0, 0)
        run_grid.addWidget(coast, 0, 1)
        run_grid.addWidget(brake, 0, 2)
        run_grid.addWidget(forward, 1, 0, 1, 2)
        run_grid.addWidget(reverse, 1, 2)
        layout.addLayout(run_grid)

        current_label = QLabel("Torque current reference (0–10 A)")
        current_label.setObjectName("sectionLabel")
        layout.addWidget(current_label)
        current_row = QHBoxLayout()
        self.hil_current_reference = QDoubleSpinBox()
        self.hil_current_reference.setRange(0.0, 10.0)
        self.hil_current_reference.setDecimals(1)
        self.hil_current_reference.setSingleStep(0.5)
        self.hil_current_reference.setSuffix(" A")
        self.hil_current_reference.setValue(4.0)
        apply_current = QPushButton("Apply Current")
        apply_current.clicked.connect(self._apply_hil_current)
        self._command_buttons.append(apply_current)
        current_row.addWidget(self.hil_current_reference, 1)
        current_row.addWidget(apply_current)
        layout.addLayout(current_row)

        hint = QLabel(
            "Higher current increases torque/acceleration. Coast lets the load "
            "slow the rotor; Brake slows it rapidly. Reverse applies opposite torque."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e; font-size: 10px;")
        layout.addWidget(hint)
        return group

    def _build_pid_panel(self) -> QGroupBox:
        """Create the live PID summary shown below the serial connection."""

        group = QGroupBox("CURRENT PI TELEMETRY")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        self.pid_status_label = QLabel("●  WAITING FOR CURRENT PI DATA")
        self.pid_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pid_status_label.setStyleSheet(
            "background-color: #1b2129; border: 1px solid #3d444d;"
            "border-radius: 6px; color: #8b949e; padding: 6px;"
            "font-size: 11px; font-weight: 700;"
        )
        layout.addWidget(self.pid_status_label)

        metrics = (
            ("target", "Target current"),
            ("current", "Measured current"),
            ("error", "Current error"),
            ("duty", "Duty cycle"),
            ("integral", "Integral contribution"),
            ("applied", "Applied voltage"),
            ("bemf", "Back-EMF"),
            ("commutation", "Sector / drive"),
            ("hall", "Hall / validity"),
            ("runtime", "Controller time"),
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)

        for row, (key, title) in enumerate(metrics):
            name_label = QLabel(title)
            name_label.setObjectName("sectionLabel")
            value_label = QLabel("—")
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            value_label.setStyleSheet(
                "color: #e6edf3; font-family: monospace; font-size: 12px;"
                "font-weight: 700;"
            )
            self._pid_value_labels[key] = value_label
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)

        layout.addLayout(grid)

        self.current_pid_chart_button = QPushButton("Open Current PI Charts")
        self.current_pid_chart_button.setObjectName("primaryButton")
        self.current_pid_chart_button.clicked.connect(
            self._show_current_pid_charts
        )
        layout.addWidget(self.current_pid_chart_button)
        return group

    def _build_phase_panel(self) -> QScrollArea:
        """Create the current-step display, commutation animation, and phase cards."""

        content = QWidget()
        content.setMinimumWidth(300)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(5, 0, 6, 0)
        layout.setSpacing(5)

        self.current_step_label = QLabel("Current Step: —")
        self.current_step_label.setObjectName("currentStepLabel")
        self.current_step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hall_warning_banner = QLabel()
        self.hall_warning_banner.setWordWrap(True)
        self.hall_warning_banner.setStyleSheet(
            "background-color: #3a1414; border: 1px solid #da3633;"
            "border-radius: 6px; color: #ff7b72; padding: 6px; font-size: 11px;"
            "font-weight: 700;"
        )
        self.hall_warning_banner.setVisible(False)

        animation_group = QGroupBox("COMMUTATION ANIMATION")
        animation_layout = QVBoxLayout(animation_group)
        animation_layout.setContentsMargins(8, 10, 8, 6)
        self.commutation_animation = CommutationAnimation()
        animation_layout.addWidget(self.commutation_animation)

        self.hall_panel = HallPanel()

        self.phase_a_card = PhaseCard("A")
        self.phase_b_card = PhaseCard("B")
        self.phase_c_card = PhaseCard("C")

        phase_row = QHBoxLayout()
        phase_row.setSpacing(6)
        phase_row.addWidget(self.phase_a_card, 1)
        phase_row.addWidget(self.phase_b_card, 1)
        phase_row.addWidget(self.phase_c_card, 1)

        layout.addWidget(self.current_step_label)
        layout.addWidget(self.hall_warning_banner)
        layout.addWidget(animation_group, 1)
        layout.addWidget(self.hall_panel)
        layout.addLayout(phase_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.setMinimumWidth(310)
        return scroll

    def _build_chart_panel(self) -> QWidget:
        """Create vertically stacked phase, Hall, and encoder history plots."""

        group = QGroupBox("TELEMETRY WAVEFORMS")
        layout = QVBoxLayout(group)

        self.phase_chart = PhaseChart()
        self.hall_chart = HallChart()
        self.encoder_chart = EncoderChart()
        charts = (self.phase_chart, self.hall_chart, self.encoder_chart)
        for source_chart in charts:
            for target_chart in charts:
                if source_chart is not target_chart:
                    source_chart.scale_combo.currentIndexChanged.connect(
                        target_chart.scale_combo.setCurrentIndex
                    )

        chart_splitter = QSplitter(Qt.Orientation.Vertical)
        chart_splitter.setChildrenCollapsible(False)
        chart_splitter.addWidget(self.phase_chart)
        chart_splitter.addWidget(self.hall_chart)
        chart_splitter.addWidget(self.encoder_chart)
        chart_splitter.setSizes([280, 280, 280])
        chart_splitter.setStretchFactor(0, 1)
        chart_splitter.setStretchFactor(1, 1)
        chart_splitter.setStretchFactor(2, 1)

        layout.addWidget(chart_splitter)
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
    ) -> QPushButton:
        """Create and track a button for one documented firmware command."""

        button = QPushButton(label)
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
        self._reset_pid_panel("WAITING FOR CURRENT PI DATA")
        self.current_pid_charts.clear()
        self._current_pi_packets_since_log = 0
        self._last_current_pi_log_at = 0.0
        self._update_control_availability()

        worker = HilWorker(str(port), int(baud_rate), parent=self)
        worker.connected.connect(self._on_serial_connected)
        worker.lines_received.connect(self._on_serial_lines)
        worker.command_sent.connect(
            lambda command: self._append_log("TX", command)
        )
        worker.error_occurred.connect(self._on_serial_error)
        worker.connection_closed.connect(self._on_connection_closed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._append_log(
            "SYSTEM",
            f"HIL link connecting to {port} at {baud_rate} baud "
            f"(free-run motor; interactive current/direction control)…",
        )
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
        self._append_log("SYSTEM", f"HIL linked to {port}.")
        self._append_log(
            "SYSTEM",
            "HIL scenario: free rotor, 24 V / 20 kHz PWM, fan + constant load.",
        )
        self.statusBar().showMessage(
            "Use HIL Motor Control for current, coast, brake and direction.", 8000
        )

    def _on_serial_lines(self, lines: list[str]) -> None:
        """Process a worker batch while rendering high-rate DATA only once."""

        latest_current_sample: CurrentPiTelemetrySample | None = None
        latest_current_line = ""
        current_sample_count = 0

        for line in lines:
            current_sample = parse_current_pi_telemetry(line)
            if current_sample is None:
                self._on_serial_line(line)
                continue

            self._buffer_current_pi_sample(current_sample)
            latest_current_sample = current_sample
            latest_current_line = line
            current_sample_count += 1

        if latest_current_sample is None:
            return

        self._apply_current_pi_telemetry(
            latest_current_sample, append_chart_sample=False
        )
        if not self._firmware_command_capable:
            self._set_firmware_status("Current PI telemetry active", "#3fb950")

        self._current_pi_packets_since_log += current_sample_count
        now = monotonic()
        if (
            now - self._last_current_pi_log_at
            >= self.CURRENT_PI_LOG_INTERVAL_SECONDS
        ):
            self._append_log(
                f"RX ×{self._current_pi_packets_since_log}",
                latest_current_line,
            )
            self._current_pi_packets_since_log = 0
            self._last_current_pi_log_at = now

    def _on_serial_line(self, line: str) -> None:
        """Classify one received line and update only validated state."""

        hall_sample = parse_hall_telemetry(line)
        if hall_sample is not None:
            self._append_log("RX", line)
            self._apply_hall_telemetry(hall_sample)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Hall telemetry active", "#3fb950"
                )
            return

        raw_hall_sample = parse_raw_hall_debug(line)
        if raw_hall_sample is not None:
            self._append_log("RX", line)
            self._apply_raw_hall_debug(raw_hall_sample)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Raw Hall bench-test telemetry active", "#3fb950"
                )
            return

        current_pi_sample = parse_current_pi_telemetry(line)
        if current_pi_sample is not None:
            self._append_log("RX", line)
            self._apply_current_pi_telemetry(current_pi_sample)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Current PI telemetry active", "#3fb950"
                )
            return

        pid_sample = parse_pid_telemetry(line)
        if pid_sample is not None:
            self._append_log("RX", line)
            self._apply_pid_telemetry(pid_sample)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Legacy current PI telemetry active", "#3fb950"
                )
            return

        encoder_sample = parse_encoder_telemetry(line)
        if encoder_sample is not None:
            self._append_log("RX", line)
            self.encoder_chart.append_sample(encoder_sample.count)
            return

        if is_hall_telemetry_header(line):
            self._append_log("RX", line)
            if not self._firmware_command_capable:
                self._set_firmware_status(
                    "Automatic Hall telemetry detected", "#3fb950"
                )
            return

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
        self.commutation_animation.set_step(
            sample.step, sample.phase_a, sample.phase_b, sample.phase_c, valid=True
        )
        self._set_hall_warning(True, "")

    def _apply_hall_telemetry(self, sample: HallTelemetrySample) -> None:
        """Update all live indicators from one validated Hall telemetry sample."""

        if sample.valid:
            self.current_step_label.setText(f"Current Step: STEP {sample.step}")
        else:
            self.current_step_label.setText("Current Step: — (invalid Hall code)")

        self.hall_panel.set_sample(
            sample.raw, sample.rpm, sample.direction, sample.valid
        )
        self.phase_a_card.set_state(sample.phase_a)
        self.phase_b_card.set_state(sample.phase_b)
        self.phase_c_card.set_state(sample.phase_c)
        self.phase_chart.append_sample(
            sample.phase_a,
            sample.phase_b,
            sample.phase_c,
        )
        self.hall_chart.append_sample(sample.step)
        self.commutation_animation.set_step(
            sample.step,
            sample.phase_a,
            sample.phase_b,
            sample.phase_c,
            valid=sample.valid,
        )
        self._set_hall_warning(sample.valid, sample.raw)

    def _apply_raw_hall_debug(self, sample: RawHallDebugSample) -> None:
        """Update the Hall-related indicators from one raw bench-test sample.

        This format only carries the raw 3-bit Hall code; it has no phase or
        rpm/direction data, so those indicators are left at "unknown" rather
        than fabricated.
        """

        if sample.valid:
            self.current_step_label.setText(f"Current Step: STEP {sample.step}")
        else:
            self.current_step_label.setText("Current Step: — (invalid Hall code)")

        self.hall_panel.set_sample(sample.raw, 0, "UNKNOWN", sample.valid)
        self.hall_chart.append_sample(sample.step)
        self.commutation_animation.set_step(
            sample.step, None, None, None, valid=sample.valid
        )
        self._set_hall_warning(sample.valid, sample.raw)

    def _apply_pid_telemetry(self, sample: PidTelemetrySample) -> None:
        """Keep the former SIM fake-current format backward-compatible."""

        status_text = "ACTIVE" if sample.enabled else "DISABLED"
        status_color = "#3fb950" if sample.enabled else "#e3b341"
        self._set_pid_status(status_text, status_color)

        # The legacy fake-data field names say RPM, but their values now carry
        # milliamps. Keeping the parser backward-compatible lets the existing
        # STM test firmware drive the new current-control UI unchanged.
        target_current_a = sample.target_rpm / 1000.0
        measured_current_a = sample.rpm / 1000.0
        error_current_a = sample.error_rpm / 1000.0

        values = {
            "target": f"{target_current_a:.3f} A",
            "current": f"{measured_current_a:.3f} A",
            "error": f"{error_current_a:+.3f} A",
            "duty": f"{sample.duty_percent:.1f} %",
            "integral": f"{sample.integral:.1f} %",
            "applied": "—",
            "bemf": "—",
            "commutation": "—",
            "hall": "—",
            "runtime": f"{sample.time_ms / 1000.0:.3f} s",
        }
        for key, text in values.items():
            self._pid_value_labels[key].setText(text)

        self.current_pid_charts.append_sample(
            time_ms=sample.time_ms,
            target_current_a=target_current_a,
            measured_current_a=measured_current_a,
            error_current_a=error_current_a,
            duty_percent=sample.duty_percent,
            integral_percent=sample.integral,
        )

    def _apply_current_pi_telemetry(
        self,
        sample: CurrentPiTelemetrySample,
        *,
        append_chart_sample: bool = True,
    ) -> None:
        """Apply one real DATA packet to current, Hall, phase, and chart UI."""

        status_text = "ACTIVE" if sample.enabled else "DISABLED"
        status_color = "#3fb950" if sample.enabled else "#e3b341"
        self._set_pid_status(status_text, status_color)

        raw_hall = f"{sample.hall_state:03b}"
        validity = "OK" if sample.valid else "INVALID"
        drive = f"S{sample.sector} · {sample.high_phase}→{sample.low_phase}"
        values = {
            "target": f"{sample.current_reference_a:.3f} A",
            "current": f"{sample.measured_current_a:.3f} A",
            "error": f"{sample.error_current_a:+.3f} A",
            "duty": f"{sample.duty_percent:.1f} %",
            "integral": f"{sample.integral_percent:.1f} %",
            "applied": f"{sample.applied_voltage_v:.3f} V",
            "bemf": f"{sample.bemf_v:.3f} V",
            "commutation": drive,
            "hall": f"{raw_hall} · {validity}",
            "runtime": f"{sample.time_ms / 1000.0:.3f} s",
        }
        for key, text in values.items():
            self._pid_value_labels[key].setText(text)

        if sample.valid:
            self.current_step_label.setText(
                f"Current Step: STEP {sample.sector}"
            )
        else:
            self.current_step_label.setText("Current Step: — (invalid Hall code)")

        phase_states = {"A": 0, "B": 0, "C": 0}
        if sample.high_phase in phase_states:
            phase_states[sample.high_phase] = 1
        if sample.low_phase in phase_states:
            phase_states[sample.low_phase] = -1

        phase_a = phase_states["A"]
        phase_b = phase_states["B"]
        phase_c = phase_states["C"]
        direction = "UNKNOWN"
        if sample.rpm > 5:
            direction = "FWD"
        elif sample.rpm < -5:
            direction = "REV"
        self.hall_panel.set_sample(raw_hall, sample.rpm, direction, sample.valid)
        self.hall_chart.append_sample(sample.sector if sample.valid else 0)
        self.phase_a_card.set_state(phase_a)
        self.phase_b_card.set_state(phase_b)
        self.phase_c_card.set_state(phase_c)
        self.phase_chart.append_sample(phase_a, phase_b, phase_c)
        self.commutation_animation.set_step(
            sample.sector,
            phase_a,
            phase_b,
            phase_c,
            valid=sample.valid,
        )
        self.encoder_chart.append_sample(sample.encoder_count)
        self._set_hall_warning(sample.valid, raw_hall)

        if append_chart_sample:
            self._buffer_current_pi_sample(sample)

    def _buffer_current_pi_sample(
        self, sample: CurrentPiTelemetrySample
    ) -> None:
        """Preserve every 1 kHz PI sample without repainting dashboard widgets."""

        self.current_pid_charts.append_sample(
            time_ms=sample.time_ms,
            target_current_a=sample.current_reference_a,
            measured_current_a=sample.measured_current_a,
            error_current_a=sample.error_current_a,
            duty_percent=sample.duty_percent,
            integral_percent=sample.integral_percent,
        )

    def _show_current_pid_charts(self) -> None:
        """Open or focus the non-modal current PI chart window."""

        self.current_pid_charts.show()
        self.current_pid_charts.raise_()
        self.current_pid_charts.activateWindow()

    def _set_pid_status(self, text: str, color: str) -> None:
        """Update the PID panel's compact activity indicator."""

        self.pid_status_label.setText(f"●  {text}")
        self.pid_status_label.setStyleSheet(
            "background-color: #1b2129; border: 1px solid #3d444d;"
            f"border-radius: 6px; color: {color}; padding: 6px;"
            "font-size: 11px; font-weight: 700;"
        )

    def _reset_pid_panel(self, status: str) -> None:
        """Clear stale PID values when a serial session changes."""

        self._set_pid_status(status, "#8b949e")
        for label in self._pid_value_labels.values():
            label.setText("—")

    def _set_hall_warning(self, valid: bool, raw: str) -> None:
        """Show, hide, and log the invalid Hall-pattern (000/111) warning."""

        if valid:
            self.hall_warning_banner.setVisible(False)
            self._last_invalid_raw_logged = None
            return

        self.hall_warning_banner.setText(
            f"⚠ Invalid Hall pattern detected: raw={raw or '???'} — 000 and 111 "
            "are not valid 3-bit Hall codes."
        )
        self.hall_warning_banner.setVisible(True)

        if raw != self._last_invalid_raw_logged:
            self._append_log(
                "WARNING",
                f"Invalid Hall code detected (raw={raw}); 000/111 patterns "
                "are not valid Hall codes.",
            )
            self.statusBar().showMessage(
                f"Invalid Hall pattern detected: raw={raw}", 6000
            )
            self._last_invalid_raw_logged = raw

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

    def _apply_hil_current(self) -> None:
        """Send the selected torque-current reference to the STM32 PI."""
        self._send_command(f"IREF {self.hil_current_reference.value():.1f}")

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
        self._reset_pid_panel("DISCONNECTED")
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
