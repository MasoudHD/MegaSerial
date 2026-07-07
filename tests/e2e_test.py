"""End-to-end test: virtual serial pair + serial worker + sequence engine.

Starts a socat PTY pair, runs a tiny responder on one end, and drives a
response-triggered sequence on the other end via the real app components.
"""
import re
import subprocess
import sys
import threading
import time

import serial
from PyQt6.QtCore import QCoreApplication, QTimer

sys.path.insert(0, ".")
from MegaSerial import utils
from MegaSerial.serial_worker import SerialWorker, SerialConfig
from MegaSerial.sequence import Step, SequenceRunner, RxMonitor, ADVANCE_RESPONSE, ADVANCE_TIME


def start_socat():
    proc = subprocess.Popen(
        ["socat", "-d", "-d", "pty,raw,echo=0", "pty,raw,echo=0"],
        stderr=subprocess.PIPE, text=True,
    )
    devs = []
    start = time.time()
    while len(devs) < 2 and time.time() - start < 5:
        line = proc.stderr.readline()
        m = re.search(r"(/dev/pts/\d+)", line)
        if m:
            devs.append(m.group(1))
    if len(devs) < 2:
        proc.terminate()
        raise RuntimeError("Could not obtain PTY pair from socat")
    return proc, devs[0], devs[1]


def responder(dev, stop):
    """Reads on `dev`; replies PONG to PING, and ACK to CFG."""
    ser = serial.Serial(dev, 115200, timeout=0.1)
    buf = b""
    while not stop.is_set():
        buf += ser.read(64)
        if b"PING" in buf:
            ser.write(b"PONG\n")
            buf = b""
        elif b"CFG" in buf:
            time.sleep(0.05)
            ser.write(b"ACK\n")
            buf = b""
    ser.close()


def main():
    # 1. unit-check conversions
    assert utils.parse_hex("48 65 6C 6C 6F") == b"Hello"
    assert utils.parse_binary("01001000") == b"H"
    assert utils.parse_ascii("A\\r\\n") == b"A\r\n"
    assert utils.parse_hex("0x0A,0x0D") == b"\x0a\x0d"
    print("[ok] conversions")

    proc, dev_a, dev_b = start_socat()
    print(f"[ok] socat pair: {dev_a} <-> {dev_b}")

    app = QCoreApplication(sys.argv)
    rx = RxMonitor()
    stop = threading.Event()
    resp_thread = threading.Thread(target=responder, args=(dev_b, stop), daemon=True)
    resp_thread.start()

    worker = SerialWorker(SerialConfig(port=dev_a, baudrate=115200))
    received = []
    worker.data_received.connect(lambda d: (rx.feed(d), received.append(d)))
    worker.data_received.connect(lambda d: print(f"[rx] {d!r}"))

    results = {}

    def run_after_open():
        steps = [
            Step(name="Handshake", data="PING", fmt="ASCII", line_ending="LF (\\n)",
                 advance=ADVANCE_RESPONSE, expect="PONG", expect_fmt="ASCII", timeout_ms=1500),
            Step(name="Configure", data="CFG=1", fmt="ASCII", line_ending="LF (\\n)",
                 advance=ADVANCE_RESPONSE, expect="ACK", expect_fmt="ASCII", timeout_ms=1500),
            Step(name="Wait", data="NOP", fmt="ASCII", line_ending="LF (\\n)",
                 advance=ADVANCE_TIME, delay_ms=200),
        ]
        runner = SequenceRunner(steps, worker.write, rx)
        runner.step_result.connect(lambda i, s, d: results.setdefault(i, s))
        runner.log.connect(lambda m, k: print(f"[seq/{k}] {m}"))
        runner.finished_all.connect(lambda ok: results.update({"completed": ok}))
        runner.finished_all.connect(lambda ok: QTimer.singleShot(200, finish))
        run_after_open.runner = runner
        runner.start()

    def finish():
        stop.set()
        worker.stop()
        proc.terminate()
        app.quit()

    worker.opened.connect(lambda: QTimer.singleShot(100, run_after_open))
    worker.start()

    QTimer.singleShot(8000, finish)  # safety timeout
    app.exec()

    print("results:", results)
    assert results.get(0) == "matched", "handshake should match PONG"
    assert results.get(1) == "matched", "configure should match ACK"
    assert results.get(2) == "done", "timed step should complete"
    assert results.get("completed") is True, "sequence should complete normally"
    print("[ok] response-triggered sequence completed")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
