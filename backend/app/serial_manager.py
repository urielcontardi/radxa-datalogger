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
                }
                for pid, info in sorted(self.ports.items())
            ]

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
            device = self.ports[port_id]["device"]
            try:
                if not os.path.exists(device):
                    with self._lock:
                        self.ports[port_id]["connected"] = False
                    time.sleep(2)
                    continue

                ser = serial.Serial(device, self.baud_rate, timeout=1)
                with self._lock:
                    self.ports[port_id]["connected"] = True

                ts = datetime.now().isoformat(timespec="milliseconds")
                self._notify(
                    port_id,
                    f"[{ts}] \x1b[92m--- Conectado em {device} ---\x1b[0m",
                )

                while self._running:
                    raw = ser.readline()
                    if raw:
                        # Tenta decodificar mas mantém os bytes de escape ANSI
                        try:
                            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        except Exception:
                            line = str(raw).rstrip("\r\n")
                        
                        ts = datetime.now().isoformat(timespec="milliseconds")
                        log_entry = f"[{ts}] {line}"

                        today = datetime.now().strftime("%Y-%m-%d")
                        log_file = port_log_dir / f"{today}.log"
                        with open(log_file, "a", encoding="utf-8") as f:
                            f.write(log_entry + "\n")
                            f.flush()

                        self._notify(port_id, log_entry)

            except serial.SerialException:
                with self._lock:
                    self.ports[port_id]["connected"] = False
                time.sleep(3)
            except Exception:
                with self._lock:
                    self.ports[port_id]["connected"] = False
                time.sleep(5)

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
