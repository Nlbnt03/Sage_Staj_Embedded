"""Reusable phase and chart widgets for the monitoring dashboard."""

from __future__ import annotations

import math
import time
from collections import deque

import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygonF,
    QRadialGradient,
)
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
        self.setMinimumHeight(92)
        self.setMinimumWidth(78)

        title = QLabel(f"PHASE {phase_name}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #9da7b3; font-size: 11px; font-weight: 700;"
        )

        self._value_label = QLabel("—")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet("font-size: 26px; font-weight: 800;")

        self._description_label = QLabel("WAITING")
        self._description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description_label.setStyleSheet("font-size: 12px; font-weight: 700;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
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
            f"color: {color}; font-size: 26px; font-weight: 800;"
        )
        self._description_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
        )
        self.setStyleSheet(
            "QFrame#phaseCard {"
            "background-color: #161b22;"
            f"border: 2px solid {color};"
            "border-radius: 11px;"
            "}"
        )


class CommutationAnimation(QWidget):
    """Animate rotor position and stator phase currents through the six-step cycle."""

    # Six-step index -> illustrative rotor angle (degrees, 0 = up, clockwise).
    _STEP_ANGLES: dict[int, float] = {1: 30, 2: 90, 3: 150, 4: 210, 5: 270, 6: 330}
    # Stator coil positions, 120 degrees apart.
    _PHASE_ANGLES: dict[str, float] = {"A": 270, "B": 30, "C": 150}
    _STATE_COLORS = {
        1: QColor("#2ea043"),
        0: QColor("#8b949e"),
        -1: QColor("#da3633"),
        None: QColor("#3d444d"),
    }
    _VALUE_TEXT = {1: "+1", 0: "0", -1: "-1", None: "—"}
    FLASH_DURATION = 0.5

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the animation in its initial, disconnected state."""

        super().__init__(parent)
        self.setMinimumSize(168, 168)

        self._current_angle = 30.0
        self._target_angle = 30.0
        self._phase_states: dict[str, int | None] = {"A": None, "B": None, "C": None}
        self._flash_started: dict[str, float] = {}
        self._step_text = "WAITING"
        self._invalid = False
        self._blink_on = True

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)
        self._spin_timer.timeout.connect(self._advance_rotation)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(400)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(30)
        self._flash_timer.timeout.connect(self._tick_flash)

    def set_step(
        self,
        step: int,
        phase_a: int | None,
        phase_b: int | None,
        phase_c: int | None,
        *,
        valid: bool = True,
    ) -> None:
        """Update the rotor target angle and stator colors from one sample."""

        new_states = {"A": phase_a, "B": phase_b, "C": phase_c}
        now = time.monotonic()
        for name, value in new_states.items():
            previous = self._phase_states.get(name)
            if value is not None and value != previous:
                self._flash_started[name] = now
        if self._flash_started and not self._flash_timer.isActive():
            self._flash_timer.start()

        self._phase_states = new_states
        self._invalid = not valid

        if valid and step in self._STEP_ANGLES:
            self._step_text = f"STEP {step}"
            self._target_angle = self._STEP_ANGLES[step]
            if not self._spin_timer.isActive():
                self._spin_timer.start()
        elif not valid:
            self._step_text = "INVALID"

        if self._invalid and not self._blink_timer.isActive():
            self._blink_timer.start()
        elif not self._invalid:
            self._blink_timer.stop()
            self._blink_on = True

        self.update()

    def _tick_flash(self) -> None:
        """Repaint while any phase's change-flash is fading, then stop."""

        now = time.monotonic()
        if all(
            now - started > self.FLASH_DURATION
            for started in self._flash_started.values()
        ):
            self._flash_timer.stop()
        self.update()

    def _flash_progress(self, name: str) -> float:
        """Return 1.0 right after a phase's value changes, fading to 0.0."""

        started = self._flash_started.get(name)
        if started is None:
            return 0.0
        elapsed = time.monotonic() - started
        if elapsed >= self.FLASH_DURATION:
            return 0.0
        return 1.0 - (elapsed / self.FLASH_DURATION)

    def _advance_rotation(self) -> None:
        """Ease the rotor toward its target angle along the shortest path."""

        diff = self._angle_diff(self._target_angle, self._current_angle)
        if abs(diff) < 0.75:
            self._current_angle = self._target_angle % 360
            self._spin_timer.stop()
        else:
            self._current_angle = (self._current_angle + diff * 0.22) % 360
        self.update()

    def _toggle_blink(self) -> None:
        self._blink_on = not self._blink_on
        self.update()

    @staticmethod
    def _angle_diff(target: float, current: float) -> float:
        """Return the signed shortest angular distance from current to target."""

        return (target - current + 180) % 360 - 180

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override signature
        """Paint the stator housing, tick ring, phase coils, and rotor magnet."""

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 40
        radius = max(side, 40) / 2
        painter.translate(self.width() / 2, self.height() / 2)

        active_step = None if self._invalid else self._step_text

        for step, angle in self._STEP_ANGLES.items():
            self._draw_tick(painter, angle, radius, active=(f"STEP {step}" == active_step))

        housing_color = "#da3633" if (self._invalid and self._blink_on) else "#3d444d"
        housing_gradient = QRadialGradient(QPointF(-radius * 0.3, -radius * 0.3), radius * 1.4)
        housing_gradient.setColorAt(0.0, QColor("#161d27"))
        housing_gradient.setColorAt(1.0, QColor("#090c11"))
        housing_pen = QPen(QColor(housing_color))
        housing_pen.setWidth(2)
        painter.setPen(housing_pen)
        painter.setBrush(QBrush(housing_gradient))
        painter.drawEllipse(QPointF(0, 0), radius * 0.78, radius * 0.78)

        for name, angle in self._PHASE_ANGLES.items():
            state = self._phase_states.get(name)
            color = self._STATE_COLORS.get(state, self._STATE_COLORS[None])
            self._draw_coil(painter, angle, radius, name, color, state)

        painter.save()
        painter.rotate(self._current_angle)
        self._draw_rotor(painter, radius)
        painter.restore()

        hub_gradient = QRadialGradient(QPointF(-3, -3), 13)
        hub_gradient.setColorAt(0.0, QColor("#525b68"))
        hub_gradient.setColorAt(1.0, QColor("#181d24"))
        painter.setPen(QPen(QColor("#0d1117"), 1.2))
        painter.setBrush(QBrush(hub_gradient))
        painter.drawEllipse(QPointF(0, 0), 9, 9)

        self._draw_step_badge(painter, radius)

    def _draw_tick(
        self, painter: QPainter, angle: float, radius: float, *, active: bool
    ) -> None:
        """Draw one of the six step-position ticks around the housing ring."""

        rad = math.radians(angle)
        sin_a, cos_a = math.sin(rad), math.cos(rad)
        outer = QPointF(radius * 1.0 * sin_a, -radius * 1.0 * cos_a)
        inner = QPointF(radius * 0.86 * sin_a, -radius * 0.86 * cos_a)
        pen = QPen(QColor("#58a6ff" if active else "#2a3038"))
        pen.setWidth(3 if active else 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(inner, outer)

    def _draw_coil(
        self,
        painter: QPainter,
        angle: float,
        radius: float,
        name: str,
        color: QColor,
        state: int | None,
    ) -> None:
        """Draw one stator winding as a colored radial coil with a glowing bobbin."""

        rad = math.radians(angle)
        sin_a, cos_a = math.sin(rad), math.cos(rad)
        outer = QPointF(radius * 0.74 * sin_a, -radius * 0.74 * cos_a)
        inner = QPointF(radius * 0.46 * sin_a, -radius * 0.46 * cos_a)
        bobbin = QPointF(radius * 0.60 * sin_a, -radius * 0.60 * cos_a)

        if state in (1, -1):
            glow = QRadialGradient(bobbin, 18)
            glow_color = QColor(color)
            glow_color.setAlpha(120)
            glow.setColorAt(0.0, glow_color)
            fade_color = QColor(color)
            fade_color.setAlpha(0)
            glow.setColorAt(1.0, fade_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(bobbin, 18, 18)

        pen = QPen(color)
        pen.setWidth(6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(inner, outer)

        painter.setPen(QPen(QColor("#e6edf3"), 1.4))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(bobbin, 7, 7)

        flash = self._flash_progress(name)
        if flash > 0.0:
            ring_pen = QPen(QColor(255, 255, 255, int(220 * flash)))
            ring_pen.setWidth(2)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(bobbin, 8 + (1.0 - flash) * 15, 8 + (1.0 - flash) * 15)

        painter.setPen(QPen(QColor("#9da7b3")))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        label_point = QPointF(radius * 1.1 * sin_a, -radius * 1.1 * cos_a)
        painter.drawText(
            QRectF(label_point.x() - 13, label_point.y() - 9, 26, 14),
            Qt.AlignmentFlag.AlignCenter,
            name,
        )

        value_font = QFont()
        value_font.setPointSize(8)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QPen(color if state is not None else QColor("#6e7681")))
        painter.drawText(
            QRectF(label_point.x() - 15, label_point.y() + 5, 30, 14),
            Qt.AlignmentFlag.AlignCenter,
            self._VALUE_TEXT.get(state, "—"),
        )

    def _draw_rotor(self, painter: QPainter, radius: float) -> None:
        """Draw the two-pole rotor magnet bar at the current rotation angle."""

        half_len = radius * 0.22
        width = max(9.0, radius * 0.16)

        north_rect = QRectF(-width / 2, -half_len, width, half_len)
        south_rect = QRectF(-width / 2, 0, width, half_len)

        painter.setPen(QPen(QColor("#0d1117"), 1.4))
        painter.setBrush(QBrush(QColor("#e5484d")))
        painter.drawRoundedRect(north_rect, 4, 4)
        painter.setBrush(QBrush(QColor("#4098e7")))
        painter.drawRoundedRect(south_rect, 4, 4)

        font = QFont()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#f7f9fb")))
        painter.drawText(north_rect, Qt.AlignmentFlag.AlignCenter, "N")
        painter.drawText(south_rect, Qt.AlignmentFlag.AlignCenter, "S")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#f7f9fb")))
        tip = QPolygonF(
            [
                QPointF(-6, -half_len),
                QPointF(6, -half_len),
                QPointF(0, -half_len - 9),
            ]
        )
        painter.drawPolygon(tip)

    def _draw_step_badge(self, painter: QPainter, radius: float) -> None:
        """Draw the current step/invalid label as a pill badge below the rotor."""

        text = self._step_text
        invalid = self._invalid
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        pill_width = metrics.horizontalAdvance(text) + 22
        pill_rect = QRectF(-pill_width / 2, radius * 0.9 - 12, pill_width, 22)

        painter.setPen(QPen(QColor("#da3633" if invalid else "#3d444d")))
        painter.setBrush(QBrush(QColor("#3a1414" if invalid else "#1b2129")))
        painter.drawRoundedRect(pill_rect, 11, 11)

        painter.setPen(QPen(QColor("#ff7b72" if invalid else "#e6edf3")))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, text)


class HallPanel(QFrame):
    """Show raw Hall bits, direction, RPM, and code validity."""

    _DIRECTION_DETAILS = {
        "FWD": ("FWD ▲", "#3fb950"),
        "REV": ("REV ▼", "#f0a020"),
        "UNKNOWN": ("UNKNOWN", "#8b949e"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the Hall status card in its initial waiting state."""

        super().__init__(parent)
        self.setObjectName("hallPanel")
        self.setMinimumHeight(118)

        title = QLabel("HALL SENSOR")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #9da7b3; font-size: 12px; font-weight: 700;"
        )

        self._raw_label = QLabel("A=— B=— C=—")
        self._raw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._raw_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #e6edf3;"
        )

        self._rpm_label = QLabel("— RPM")
        self._rpm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rpm_label.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #58a6ff;"
        )

        self._direction_label = QLabel("UNKNOWN")
        self._direction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._direction_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #8b949e;"
        )

        self._valid_label = QLabel("WAITING")
        self._valid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._valid_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #8b949e;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(2)
        layout.addWidget(title)
        layout.addWidget(self._raw_label)
        layout.addWidget(self._rpm_label)
        layout.addWidget(self._direction_label)
        layout.addWidget(self._valid_label)

        self._apply_border("#484f58")

    def set_sample(self, raw: str, rpm: int, direction: str, valid: bool) -> None:
        """Apply one validated Hall telemetry sample."""

        bits_text = "  ".join(
            f"{name}={bit}" for name, bit in zip("ABC", raw)
        )
        self._raw_label.setText(bits_text)
        self._rpm_label.setText(f"{rpm} RPM")

        text, color = self._DIRECTION_DETAILS.get(
            direction, self._DIRECTION_DETAILS["UNKNOWN"]
        )
        self._direction_label.setText(text)
        self._direction_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {color};"
        )

        if valid:
            self._valid_label.setText("HALL OK")
            border_color = "#2ea043"
        else:
            self._valid_label.setText("INVALID HALL CODE")
            border_color = "#da3633"
        self._valid_label.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {border_color};"
        )
        self._apply_border(border_color)

    def _apply_border(self, color: str) -> None:
        """Recolor the card border to match the latest sample's status."""

        self.setStyleSheet(
            "QFrame#hallPanel {"
            "background-color: #161b22;"
            f"border: 2px solid {color};"
            "border-radius: 11px;"
            "}"
        )


class _RollingThreeSignalChart(QWidget):
    """Render three bounded digital signals with shared chart behavior."""

    HISTORY_SECONDS = 60.0
    DEFAULT_SCALE_SECONDS = 10.0
    SCALE_OPTIONS = (1, 2, 5, 10, 30, 60)
    MAX_SAMPLES = 6000

    def __init__(
        self,
        *,
        title: str,
        y_label: str,
        y_ticks: list[tuple[int, str]] | None,
        y_range: tuple[float, float] | None,
        curve_names: tuple[str | None, str | None, str | None],
        parent: QWidget | None = None,
    ) -> None:
        """Create a styled plot, controls, and a throttled repaint timer."""

        super().__init__(parent)
        self.setMinimumHeight(190)
        self._origin = time.monotonic()
        self._visible_seconds = self.DEFAULT_SCALE_SECONDS
        self._samples: deque[tuple[float, int, int, int]] = deque(
            maxlen=self.MAX_SAMPLES
        )

        axis = pg.AxisItem(orientation="left")
        if y_ticks is not None:
            axis.setTicks([y_ticks])
        self._plot = pg.PlotWidget(axisItems={"left": axis})
        self._plot.setBackground("#0b0f14")
        self._plot.showGrid(x=True, y=True, alpha=0.18)
        self._plot.setMouseEnabled(x=False, y=False)
        if y_range is None:
            self._plot.enableAutoRange(axis="y")
        else:
            self._plot.setYRange(*y_range, padding=0)
        self._plot.setXRange(0, self._visible_seconds, padding=0)
        self._plot.setLabel("bottom", "Elapsed time", units="s")
        self._plot.setLabel("left", y_label)
        self._plot.addLegend(offset=(12, 8), brush="#161b22", pen="#30363d")

        curves: list[pg.PlotDataItem] = []
        for name, color in zip(curve_names, ("#3fb950", "#f0a020", "#58a6ff")):
            if name is None:
                curves.append(pg.PlotDataItem())
            else:
                curves.append(
                    self._plot.plot(name=name, pen=pg.mkPen(color, width=2))
                )
        self._signal_a_curve, self._signal_b_curve, self._signal_c_curve = curves

        clear_button = QPushButton("Clear Chart")
        clear_button.clicked.connect(self.clear)

        header = QHBoxLayout()
        self._title_label = QLabel(title)
        self._title_label.setObjectName("sectionLabel")
        scale_label = QLabel("Time scale")
        scale_label.setObjectName("sectionLabel")
        self.scale_combo = QComboBox()
        self.scale_combo.setToolTip(
            "Choose a shorter window to spread out dense telemetry transitions."
        )
        for seconds in self.SCALE_OPTIONS:
            self.scale_combo.addItem(f"{seconds} s", float(seconds))
        self.scale_combo.setCurrentIndex(
            self.scale_combo.findData(self.DEFAULT_SCALE_SECONDS)
        )
        self.scale_combo.currentIndexChanged.connect(self._change_time_scale)

        header.addWidget(self._title_label)
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

    def _append_values(self, value_a: int, value_b: int, value_c: int) -> None:
        """Append three signal values with one monotonic timestamp."""

        elapsed = time.monotonic() - self._origin
        self._samples.append((elapsed, value_a, value_b, value_c))

    def clear(self) -> None:
        """Clear samples and restart the elapsed-time axis."""

        self._samples.clear()
        self._origin = time.monotonic()
        self._signal_a_curve.clear()
        self._signal_b_curve.clear()
        self._signal_c_curve.clear()
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
        signal_a = [sample[1] for sample in self._samples]
        signal_b = [sample[2] for sample in self._samples]
        signal_c = [sample[3] for sample in self._samples]

        x_step, a_step = self._as_step_series(timestamps, signal_a)
        _, b_step = self._as_step_series(timestamps, signal_b)
        _, c_step = self._as_step_series(timestamps, signal_c)

        self._signal_a_curve.setData(x_step, a_step)
        self._signal_b_curve.setData(x_step, b_step)
        self._signal_c_curve.setData(x_step, c_step)

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


class PhaseChart(_RollingThreeSignalChart):
    """Render a bounded, rolling 60-second three-phase step chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the phase-state chart."""

        super().__init__(
            title="REAL-TIME PHASE HISTORY",
            y_label="Phase state",
            y_ticks=[(-1, "-1  LOW"), (0, "0  FLOAT"), (1, "+1  HIGH")],
            y_range=(-1.25, 1.25),
            curve_names=("Phase A", "Phase B", "Phase C"),
            parent=parent,
        )

    def append_sample(self, phase_a: int, phase_b: int, phase_c: int) -> None:
        """Append one three-phase commutation sample."""

        self._append_values(phase_a, phase_b, phase_c)


class HallChart(_RollingThreeSignalChart):
    """Render the validated Hall commutation step as one rolling signal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a regular Hall-step history chart."""

        super().__init__(
            title="REAL-TIME HALL HISTORY",
            y_label="Hall step",
            y_ticks=[
                (0, "INVALID"),
                (1, "STEP 1"),
                (2, "STEP 2"),
                (3, "STEP 3"),
                (4, "STEP 4"),
                (5, "STEP 5"),
                (6, "STEP 6"),
            ],
            y_range=(-0.25, 6.25),
            curve_names=("Hall step", None, None),
            parent=parent,
        )

    def append_sample(self, step: int) -> None:
        """Append one validated Hall commutation step, including invalid zero."""

        if not 0 <= step <= 6:
            return
        self._append_values(step, step, step)


class EncoderChart(_RollingThreeSignalChart):
    """Provide a rolling encoder-count plot ready for STM telemetry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the encoder history chart with automatic vertical scaling."""

        super().__init__(
            title="REAL-TIME ENCODER HISTORY · WAITING FOR STM DATA",
            y_label="Encoder count",
            y_ticks=None,
            y_range=None,
            curve_names=("Encoder", None, None),
            parent=parent,
        )

    def append_sample(self, encoder_count: int) -> None:
        """Append an encoder count when the STM protocol exposes one."""

        self._title_label.setText("REAL-TIME ENCODER HISTORY")
        self._append_values(encoder_count, encoder_count, encoder_count)
