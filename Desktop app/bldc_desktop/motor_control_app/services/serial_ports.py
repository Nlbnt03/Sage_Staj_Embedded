"""Serial-port discovery helpers with macOS NUCLEO prioritization."""

from __future__ import annotations

from dataclasses import dataclass

from serial.tools import list_ports


@dataclass(frozen=True, slots=True)
class SerialPortInfo:
    """Display data for one discovered serial port."""

    device: str
    description: str
    is_preferred: bool

    @property
    def display_name(self) -> str:
        """Return a concise label suitable for a combo box."""

        suffix = f" — {self.description}" if self.description else ""
        marker = "★ " if self.is_preferred else ""
        return f"{marker}{self.device}{suffix}"


def discover_serial_ports() -> list[SerialPortInfo]:
    """Discover ports and place ``/dev/cu.usbmodem*`` devices first."""

    discovered: list[SerialPortInfo] = []
    for port in list_ports.comports():
        device = port.device or ""
        description = "" if port.description in (None, "n/a") else port.description
        preferred = device.startswith("/dev/cu.usbmodem")
        discovered.append(
            SerialPortInfo(
                device=device,
                description=description,
                is_preferred=preferred,
            )
        )

    return sorted(
        discovered,
        key=lambda item: (not item.is_preferred, item.device.casefold()),
    )
