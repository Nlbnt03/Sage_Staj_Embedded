"""Reusable phase and chart widgets for the monitoring dashboard."""

from __future__ import annotations

import time
from collections import deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PhaseCard(QFrame):
    """Show one motor phase as a number, label, and state color."""

    _STATE_DETAILS = {
        1: ("+1", "HIGH", "#2ea043"),
        0: ("0", "FLOAT", "#8b949e"),
        -1: ("-1", "LOW", "#da3633"),
        None: ("—", "WAITING", "#484f58"),
    }

    def __init__(self, phase_name: str, parent: QWidget | None = None) -> None:
        """Create a card for phase A, B, or C."""

        super().__init__(parent)
        self.setObjectName("phaseCard")
        self.setMinimumHeight(145)

        title = QLabel(f"PHASE {phase_name}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #9da7b3; font-size: 13px; font-weight: 700;"
        )

        self._value_label = QLabel("—")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet("font-size: 38px; font-weight: 800;")

        self._description_label = QLabel("WAITING")
        self._description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description_label.setStyleSheet("font-size: 15px; font-weight: 700;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self._value_label)
        layout.addWidget(self._description_label)
        layout.addStretch()

        self.set_state(None)

    def set_state(self, value: int | None) -> None:
        """Apply a validated phase state without affecting other cards."""

        if value not in self._STATE_DETAILS:
            return

        numeric, description, color = self._STATE_DETAILS[value]
        self._value_label.setText(numeric)
        self._description_label.setText(description)
        self._value_label.setStyleSheet(
            f"color: {color}; font-size: 38px; font-weight: 800;"
        )
        self._description_label.setStyleSheet(
            f"color: {color}; font-size: 15px; font-weight: 700;"
        )
        self.setStyleSheet(
            "QFrame#phaseCard {"
            "background-color: #161b22;"
            f"border: 2px solid {color};"
            "border-radius: 11px;"
            "}"
        )


class PhaseChart(QWidget):
    """Render a bounded, rolling 60-second three-phase step chart."""

    HISTORY_SECONDS = 60.0
    DEFAULT_SCALE_SECONDS = 10.0
    SCALE_OPTIONS = (1, 2, 5, 10, 30, 60)
    MAX_SAMPLES = 6000

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create plot items and a throttled repaint timer."""

        super().__init__(parent)
        self._origin = time.monotonic()
        self._visible_seconds = self.DEFAULT_SCALE_SECONDS
        self._samples: deque[tuple[float, int, int, int]] = deque(
            maxlen=self.MAX_SAMPLES
        )

        axis = pg.AxisItem(orientation="left")
        axis.setTicks(
            [[(-1, "-1  LOW"), (0, "0  FLOAT"), (1, "+1  HIGH")]]
        )
        self._plot = pg.PlotWidget(axisItems={"left": axis})
        self._plot.setBackground("#0b0f14")
        self._plot.showGrid(x=True, y=True, alpha=0.18)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.setYRange(-1.25, 1.25, padding=0)
        self._plot.setXRange(0, self._visible_seconds, padding=0)
        self._plot.setLabel("bottom", "Elapsed time", units="s")
        self._plot.setLabel("left", "Phase state")
        self._plot.addLegend(offset=(12, 8), brush="#161b22", pen="#30363d")

        self._phase_a_curve = self._plot.plot(
            name="Phase A", pen=pg.mkPen("#3fb950", width=2)
        )
        self._phase_b_curve = self._plot.plot(
            name="Phase B", pen=pg.mkPen("#f0a020", width=2)
        )
        self._phase_c_curve = self._plot.plot(
            name="Phase C", pen=pg.mkPen("#58a6ff", width=2)
        )

        clear_button = QPushButton("Clear Chart")
        clear_button.clicked.connect(self.clear)

        header = QHBoxLayout()
        title = QLabel("REAL-TIME PHASE HISTORY")
        title.setObjectName("sectionLabel")
        scale_label = QLabel("Time scale")
        scale_label.setObjectName("sectionLabel")
        self.scale_combo = QComboBox()
        self.scale_combo.setToolTip(
            "Choose a shorter window to spread out dense commutation transitions."
        )
        for seconds in self.SCALE_OPTIONS:
            self.scale_combo.addItem(f"{seconds} s", float(seconds))
        self.scale_combo.setCurrentIndex(
            self.scale_combo.findData(self.DEFAULT_SCALE_SECONDS)
        )
        self.scale_combo.currentIndexChanged.connect(self._change_time_scale)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(scale_label)
        header.addWidget(self.scale_combo)
        header.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self._plot, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._redraw)
        self._refresh_timer.start()

    def append_sample(self, phase_a: int, phase_b: int, phase_c: int) -> None:
        """Append one sample with a monotonic timestamp."""

        elapsed = time.monotonic() - self._origin
        self._samples.append((elapsed, phase_a, phase_b, phase_c))

    def clear(self) -> None:
        """Clear samples and restart the elapsed-time axis."""

        self._samples.clear()
        self._origin = time.monotonic()
        self._phase_a_curve.clear()
        self._phase_b_curve.clear()
        self._phase_c_curve.clear()
        self._plot.setXRange(0, self._visible_seconds, padding=0)

    def _change_time_scale(self) -> None:
        """Apply the selected horizontal window while retaining 60 s of history."""

        selected = self.scale_combo.currentData()
        if selected is None:
            return
        self._visible_seconds = float(selected)
        latest_sample_time = self._samples[-1][0] if self._samples else 0.0
        right_edge = max(self._visible_seconds, latest_sample_time)
        self._plot.setXRange(
            max(0.0, right_edge - self._visible_seconds),
            right_edge,
            padding=0,
        )

    def _redraw(self) -> None:
        """Repaint from sample time so the chart freezes when telemetry stops."""

        if not self._samples:
            return

        latest_sample_time = self._samples[-1][0]
        cutoff = latest_sample_time - self.HISTORY_SECONDS
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        timestamps = [sample[0] for sample in self._samples]
        phase_a = [sample[1] for sample in self._samples]
        phase_b = [sample[2] for sample in self._samples]
        phase_c = [sample[3] for sample in self._samples]

        x_step, a_step = self._as_step_series(timestamps, phase_a)
        _, b_step = self._as_step_series(timestamps, phase_b)
        _, c_step = self._as_step_series(timestamps, phase_c)

        self._phase_a_curve.setData(x_step, a_step)
        self._phase_b_curve.setData(x_step, b_step)
        self._phase_c_curve.setData(x_step, c_step)

        right_edge = max(self._visible_seconds, latest_sample_time)
        self._plot.setXRange(
            max(0.0, right_edge - self._visible_seconds),
            right_edge,
            padding=0,
        )

    @staticmethod
    def _as_step_series(
        timestamps: list[float], values: list[int]
    ) -> tuple[list[float], list[int]]:
        """Expand point data into post-transition horizontal step segments."""

        if not timestamps:
            return [], []

        x_step = [timestamps[0]]
        y_step = [values[0]]
        for index in range(1, len(timestamps)):
            x_step.extend((timestamps[index], timestamps[index]))
            y_step.extend((values[index - 1], values[index]))
        return x_step, y_step
