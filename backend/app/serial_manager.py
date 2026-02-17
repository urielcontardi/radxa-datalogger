import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import serial
import serial.tools.list_ports


class SerialManager:
    """Discovers DAP serial devices, reads data, and writes daily log files."""

    DAP_VID = 0x0D28

    def __init__(self, log_dir: str, baud_rate: int = 115200):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.baud_rate = baud_rate
        self.ports: dict[str, dict] = {}
        self.subscribers: dict[str, list[Callable]] = {}
        self._running = False
        self._lock = threading.Lock()
        self._pause_flags: dict[str, bool] = {}
        self._pause_ack: dict[str, threading.Event] = {}

    @staticmethod
    def _sanitize_id(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", value)

    def discover_dap_ports(self) -> list:
        result = []
        for p in serial.tools.list_ports.comports():
            is_dap = False
            if p.vid == self.DAP_VID:
                is_dap = True
            desc = f"{p.description or ''} {p.product or ''}".upper()
            if "DAP" in desc:
                is_dap = True
            if is_dap:
                result.append(p)
        return sorted(result, key=lambda x: x.device)

    def get_ports_info(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": pid,
                    "device": info["device"],
                    "name": info["name"],
                    "connected": info.get("connected", False),
                    "serial_number": info.get("serial_number", ""),
                    "flashing": self._pause_flags.get(pid, False),
                }
                for pid, info in sorted(self.ports.items())
            ]

    def pause_port(self, port_id: str):
        """Pause serial reading so pyocd can access the probe. Blocks until released."""
        self._pause_ack[port_id] = threading.Event()
        with self._lock:
            self._pause_flags[port_id] = True
        self._pause_ack[port_id].wait(timeout=10)

    def resume_port(self, port_id: str):
        """Resume serial reading after flash."""
        with self._lock:
            self._pause_flags[port_id] = False

    def subscribe(self, port_id: str, callback: Callable):
        with self._lock:
            self.subscribers.setdefault(port_id, []).append(callback)

    def unsubscribe(self, port_id: str, callback: Callable):
        with self._lock:
            if port_id in self.subscribers:
                try:
                    self.subscribers[port_id].remove(callback)
                except ValueError:
                    pass

    def _notify(self, port_id: str, line: str):
        with self._lock:
            callbacks = list(self.subscribers.get(port_id, []))
        for cb in callbacks:
            try:
                cb(line)
            except Exception:
                pass

    def _read_serial(self, port_id: str):
        port_log_dir = self.log_dir / port_id
        port_log_dir.mkdir(parents=True, exist_ok=True)

        while self._running:
            # Handle pause (e.g. during firmware flash)
            with self._lock:
                paused = self._pause_flags.get(port_id, False)
            if paused:
                with self._lock:
                    self.ports[port_id]["connected"] = False
                ack = self._pause_ack.get(port_id)
                if ack:
                    ack.set()
                ts = datetime.now().isoformat(timespec="milliseconds")
                self._notify(
                    port_id,
                    f"[{ts}] \x1b[93m--- Serial pausada (flash em andamento) ---\x1b[0m",
                )
                while self._running:
                    with self._lock:
                        if not self._pause_flags.get(port_id, False):
                            break
                    time.sleep(0.2)
                ts = datetime.now().isoformat(timespec="milliseconds")
                self._notify(
                    port_id,
                    f"[{ts}] \x1b[92m--- Serial retomada ---\x1b[0m",
                )
                continue

            device = self.ports[port_id]["device"]
            ser = None
            log_fh = None
            try:
                if not os.path.exists(device):
                    with self._lock:
                        self.ports[port_id]["connected"] = False
                    time.sleep(2)
                    continue

                ser = serial.Serial(device, self.baud_rate, timeout=0.05)
                with self._lock:
                    self.ports[port_id]["connected"] = True

                ts = datetime.now().isoformat(timespec="milliseconds")
                self._notify(
                    port_id,
                    f"[{ts}] \x1b[92m--- Conectado em {device} ---\x1b[0m",
                )

                buf = bytearray()
                current_date = ""
                last_flush = time.monotonic()

                while self._running:
                    # Break if paused (flash request)
                    with self._lock:
                        if self._pause_flags.get(port_id, False):
                            break

                    # Read all available bytes at once (bulk read)
                    waiting = ser.in_waiting
                    if waiting > 0:
                        buf.extend(ser.read(waiting))
                    else:
                        byte = ser.read(1)
                        if byte:
                            buf.extend(byte)

                    # Process all complete lines in the buffer
                    entries_to_notify = []
                    while b"\n" in buf:
                        idx = buf.index(b"\n")
                        raw_line = bytes(buf[:idx])
                        del buf[:idx + 1]

                        line = raw_line.decode("latin-1").rstrip("\r")
                        if not line:
                            continue

                        ts = datetime.now().isoformat(timespec="milliseconds")
                        log_entry = f"[{ts}] {line}"

                        # Rotate log file daily
                        today = datetime.now().strftime("%Y-%m-%d")
                        if today != current_date:
                            if log_fh:
                                log_fh.flush()
                                log_fh.close()
                            log_file = port_log_dir / f"{today}.log"
                            log_fh = open(log_file, "a", encoding="utf-8")
                            current_date = today

                        log_fh.write(log_entry + "\n")
                        entries_to_notify.append(log_entry)

                    # Flush to disk periodically (every 0.5s) instead of per-line
                    now = time.monotonic()
                    if log_fh and (now - last_flush) >= 0.5:
                        log_fh.flush()
                        last_flush = now

                    # Notify subscribers AFTER all I/O is done
                    for entry in entries_to_notify:
                        self._notify(port_id, entry)

            except serial.SerialException:
                with self._lock:
                    self.ports[port_id]["connected"] = False
                time.sleep(3)
            except Exception:
                with self._lock:
                    self.ports[port_id]["connected"] = False
                time.sleep(5)
            finally:
                if log_fh:
                    try:
                        log_fh.flush()
                        log_fh.close()
                    except Exception:
                        pass
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass

    def _discover_and_start(self):
        dap_ports = self.discover_dap_ports()
        for p in dap_ports:
            port_id = self._sanitize_id(
                p.serial_number if p.serial_number else p.device.split("/")[-1]
            )

            with self._lock:
                if port_id in self.ports:
                    self.ports[port_id]["device"] = p.device
                    continue

                self.ports[port_id] = {
                    "device": p.device,
                    "name": p.description or p.product or f"DAP ({p.device})",
                    "serial_number": p.serial_number or "",
                    "connected": False,
                }

            t = threading.Thread(
                target=self._read_serial, args=(port_id,), daemon=True
            )
            t.start()

    def _discovery_loop(self):
        while self._running:
            try:
                self._discover_and_start()
            except Exception:
                pass
            time.sleep(10)

    def start(self):
        self._running = True
        self._discover_and_start()
        threading.Thread(target=self._discovery_loop, daemon=True).start()

    def stop(self):
        self._running = False
