import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FlashManager:
    """Manages firmware flashing to DAP targets via pyocd."""

    def __init__(
        self,
        serial_manager,
        pack_dir: str = "/app/packs",
        target: str = "EFR32FG28B322F1024IM48",
        frequency: str = "20M",
    ):
        self.serial_manager = serial_manager
        self.pack_dir = Path(pack_dir)
        self.pack_dir.mkdir(parents=True, exist_ok=True)
        self.target = target
        self.frequency = frequency

    def _find_pack(self, target: str) -> Optional[str]:
        """Find a .pack file that matches the target family name.

        E.g. target='EFR32FG28B322F1024IM48' -> finds pack with 'EFR32FG28' in name.
        """
        if not self.pack_dir.exists():
            return None

        packs = list(self.pack_dir.glob("*.pack"))
        if not packs:
            return None

        match = re.search(r"EFR32[A-Z]{2}\d{2}", target, re.IGNORECASE)
        if match:
            family = match.group(0).upper()
            for p in packs:
                if family in p.name.upper():
                    return str(p)

        return str(sorted(packs)[0])

    def list_packs(self) -> list[str]:
        """List available .pack files."""
        if self.pack_dir.exists():
            return [f.name for f in sorted(self.pack_dir.glob("*.pack"))]
        return []

    def flash(
        self,
        port_id: str,
        hex_path: str,
        target: Optional[str] = None,
        frequency: Optional[str] = None,
    ) -> dict:
        """Flash a hex file to the device identified by port_id.

        Automatically finds the correct .pack file based on the target name.
        Does NOT pause serial reading (DAPLink debug and CDC serial are independent USB interfaces).
        """
        with self.serial_manager._lock:
            port_info = self.serial_manager.ports.get(port_id)

        if not port_info:
            return {
                "success": False,
                "output": "",
                "error": f"Porta '{port_id}' nao encontrada",
            }

        serial_number = port_info.get("serial_number", "")
        if not serial_number:
            return {
                "success": False,
                "output": "",
                "error": f"Sem serial number para '{port_id}'. "
                "Nao e possivel identificar o probe.",
            }

        use_target = target or self.target
        use_freq = frequency or self.frequency

        steps: list[str] = []

        t0 = time.monotonic()
        use_pack = self._find_pack(use_target)
        t_pack = time.monotonic() - t0
        steps.append(f"Busca pack: {t_pack:.3f}s -> {Path(use_pack).name if use_pack else 'nenhum'}")

        cmd = [
            "pyocd",
            "flash",
            hex_path,
            "-t",
            use_target,
            "-u",
            serial_number,
            "-f",
            use_freq,
        ]
        if use_pack:
            cmd.extend(["--pack", use_pack])

        cmd_str = " ".join(cmd)

        try:
            logger.info("Running: %s", cmd_str)
            t1 = time.monotonic()
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180
            )
            t_pyocd = time.monotonic() - t1
            steps.append(f"Execucao pyocd: {t_pyocd:.2f}s")
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "command": cmd_str,
                "steps": steps,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Flash timeout (180s)",
                "command": cmd_str,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "output": "",
                "error": "pyocd nao encontrado. Verifique a instalacao.",
                "command": cmd_str,
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "command": cmd_str,
            }
