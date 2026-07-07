"""Serial port I/O running on a background thread.

``SerialWorker`` is a ``QThread`` subclass that owns the ``serial.Serial``
object. Its ``run()`` method is the read loop and emits ``data_received`` for
every chunk. When the loop ends (stop requested, error, or unplug) ``run()``
simply returns, so the thread finishes cleanly with no leftover event loop.
Writes are guarded by a lock so the GUI and sequence threads can both call
``write`` safely.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class SerialConfig:
    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"          # N, E, O, M, S
    stopbits: float = 1        # 1, 1.5, 2
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    auto_reconnect: bool = True
    reconnect_timeout: float = 0.0   # 0 = retry until Disconnect is pressed
    port_hwid: str = ""              # USB/Bluetooth id to follow re-enumeration

    def to_kwargs(self, port: str | None = None) -> dict:
        bytesize_map = {5: serial.FIVEBITS, 6: serial.SIXBITS,
                        7: serial.SEVENBITS, 8: serial.EIGHTBITS}
        parity_map = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                      "O": serial.PARITY_ODD, "M": serial.PARITY_MARK,
                      "S": serial.PARITY_SPACE}
        stopbits_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE,
                        2: serial.STOPBITS_TWO}
        kwargs = dict(
            port=port or self.port,
            baudrate=int(self.baudrate),
            bytesize=bytesize_map.get(self.bytesize, serial.EIGHTBITS),
            parity=parity_map.get(self.parity, serial.PARITY_NONE),
            stopbits=stopbits_map.get(self.stopbits, serial.STOPBITS_ONE),
            xonxoff=self.xonxoff,
            rtscts=self.rtscts,
            dsrdtr=self.dsrdtr,
            timeout=0.05,
        )
        # Take exclusive (TIOCEXCL) access on POSIX so ModemManager or other
        # programs cannot open the same port and cause "multiple access"
        # read errors on cellular modems and USB-serial adapters.
        if os.name == "posix":
            kwargs["exclusive"] = True
        return kwargs


def port_hwid(port: str) -> str:
    """Return the stable hardware id for a port name, if known."""
    target = port.upper()
    for info in list_ports.comports():
        if info.device.upper() == target:
            return info.hwid or ""
    return ""


def _port_listed(port: str) -> bool:
    """Return whether ``port`` currently appears in the OS port list."""
    if port.upper().startswith("COM"):
        target = port.upper()
        return any(info.device.upper() == target for info in list_ports.comports())
    return os.path.exists(port)


def available_ports() -> list[tuple[str, str]]:
    """Return ``(device, description)`` for every serial port found."""
    ports = []
    for p in list_ports.comports():
        desc = p.description if p.description and p.description != "n/a" else p.device
        ports.append((p.device, desc))
    ports.sort(key=lambda t: t[0])
    return ports


class SerialWorker(QThread):
    data_received = pyqtSignal(bytes)
    error = pyqtSignal(str)
    warning = pyqtSignal(str)
    opened = pyqtSignal()
    closed = pyqtSignal()

    # Consecutive transient read hiccups tolerated before treating the link as
    # lost (~ this * 50ms of empty "readiness but no data" reads).
    _MAX_TRANSIENT = 40
    _PORT_CHECK_INTERVAL = 20    # read loops between port-presence checks

    def __init__(self, config: SerialConfig):
        super().__init__()
        self._config = config
        self._serial: serial.Serial | None = None
        self._running = False
        self._write_lock = threading.Lock()
        self._open_error = ""

    # -- lifecycle ---------------------------------------------------------
    def _resolve_port(self) -> str:
        """Pick the port to open: current name, or the same device on a new COM."""
        if _port_listed(self._config.port):
            return self._config.port
        if self._config.port_hwid:
            for info in list_ports.comports():
                if info.hwid == self._config.port_hwid:
                    return info.device
        return self._config.port

    def _try_open(self) -> bool:
        port = self._resolve_port()
        try:
            with self._write_lock:
                self._serial = serial.Serial(**self._config.to_kwargs(port))
            self._open_error = ""
            if port != self._config.port:
                self.warning.emit(
                    f"Device re-enumerated as {port} (was {self._config.port}).")
                self._config.port = port
            return True
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            self._open_error = str(exc)
            return False

    def set_auto_reconnect(self, enabled: bool) -> None:
        self._config.auto_reconnect = enabled
        self._config.reconnect_timeout = 0.0 if enabled else 30.0

    def run(self) -> None:
        if not self._try_open():
            hint = ""
            if "busy" in self._open_error.lower():
                hint = " (another program may be using it — e.g. ModemManager)"
            self.error.emit(f"Could not open {self._config.port}: {self._open_error}{hint}")
            self.closed.emit()
            return
        self._running = True
        self.opened.emit()

        while self._running:
            outcome = self._read_loop()          # "stop" or "lost"
            if outcome == "stop" or not self._running:
                break
            if not self._config.auto_reconnect:
                self.error.emit("Connection lost; closing port.")
                break
            if not self._reconnect():
                break

        self._close_serial()
        self.closed.emit()

    def _read_loop(self) -> str:
        """Read until stopped ("stop") or the connection is lost ("lost")."""
        transient = 0
        port_checks = 0
        while self._running:
            port_checks += 1
            if port_checks >= self._PORT_CHECK_INTERVAL:
                port_checks = 0
                if not _port_listed(self._config.port):
                    self._close_serial()
                    self.warning.emit("Connection lost (device unplugged).")
                    return "lost"

            try:
                if self._serial is None or not self._serial.is_open:
                    self.warning.emit("Connection lost.")
                    return "lost"

                waiting = self._serial.in_waiting
                chunk = self._serial.read(waiting if waiting else 1)
                if chunk:
                    transient = 0
                    self.data_received.emit(bytes(chunk))
            except serial.SerialException as exc:
                if not self._running:
                    return "stop"
                msg = str(exc)
                # "readiness but no data" with the node still present is usually a
                # transient USB hiccup — retry a few times before giving up.
                if "returned no data" in msg and _port_listed(self._config.port):
                    transient += 1
                    if transient == 1:
                        self.warning.emit("Read hiccup, recovering…")
                    try:
                        self._serial.reset_input_buffer()
                    except Exception:  # noqa: BLE001
                        pass
                    if transient > self._MAX_TRANSIENT:
                        self._close_serial()
                        self.warning.emit("Connection lost.")
                        return "lost"
                    self.msleep(50)
                    continue
                # Any other serial error (e.g. EIO after a device reset): the fd
                # is dead, so the port must be reopened.
                self._close_serial()
                self.warning.emit(f"Connection lost: {exc}")
                return "lost"
            except OSError as exc:
                if not self._running:
                    return "stop"
                self._close_serial()
                self.warning.emit(f"Connection lost: {exc}")
                return "lost"
            except Exception as exc:  # noqa: BLE001
                if not self._running:
                    return "stop"
                self._close_serial()
                self.warning.emit(f"Connection lost: {exc}")
                return "lost"
        return "stop"

    def _reconnect(self) -> bool:
        """Try to reopen the port until it succeeds, times out, or stop is requested."""
        self.warning.emit(f"Reconnecting to {self._config.port}…")
        deadline = None
        if self._config.reconnect_timeout > 0:
            deadline = time.monotonic() + self._config.reconnect_timeout
        while self._running and (deadline is None or time.monotonic() < deadline):
            if not self._config.auto_reconnect:
                return False
            self.msleep(300)
            if self._try_open():
                self.warning.emit(f"Reconnected to {self._config.port}.")
                self.opened.emit()
                return True
        if self._running:
            if deadline is None:
                return False
            self.error.emit(
                f"Could not reconnect to {self._config.port} within "
                f"{int(self._config.reconnect_timeout)}s; closing.")
        return False

    def stop(self) -> None:
        """Ask the read loop to end and block until the thread finishes."""
        self._running = False
        if self.isRunning():
            self.wait(2000)

    def _close_serial(self) -> None:
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:  # noqa: BLE001
                pass
        self._serial = None

    # -- I/O ---------------------------------------------------------------
    def write(self, data: bytes) -> bool:
        with self._write_lock:
            if self._serial is None or not self._serial.is_open:
                return False
            try:
                self._serial.write(data)
                self._serial.flush()
                return True
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"Write error: {exc}")
                return False

    @property
    def port_name(self) -> str:
        return self._config.port

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def set_dtr(self, value: bool) -> None:
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.dtr = value
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"DTR error: {exc}")

    def set_rts(self, value: bool) -> None:
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.rts = value
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"RTS error: {exc}")
