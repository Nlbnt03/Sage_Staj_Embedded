"""Background services used by the desktop application."""

from .serial_ports import SerialPortInfo, discover_serial_ports
from .serial_worker import SerialWorker

__all__ = ["SerialPortInfo", "SerialWorker", "discover_serial_ports"]
