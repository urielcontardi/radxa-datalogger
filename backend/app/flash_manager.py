import logging
import os
import re
import subprocess
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
        """Find a .pack file that matches the target name."""
        if not self.pack_dir.exists():
            return None
        
        packs = list(self.pack_dir.glob("*.pack"))
        if not packs:
            return None

        # Try to find a pack that contains part of the target name (e.g. "FG28")
        # Extract family part, e.g., EFR32FG28 from EFR32FG28B322...
        match = re.search(r'EFR32[A-Z]{2}\d{2}', target, re.IGNORECASE)
        if match:
            family = match.group(0).upper()
            for p in packs:
                if family in p.name.upper():
                    return str(p)
        
        # Fallback to first pack if no match
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
        pack_path: Optional[str] = None,
        target: Optional[str] = None,
        frequency: Optional[str] = None,
    ) -> dict:
        """Flash a hex file to the device identified by port_id.

        Pauses serial reading, runs pyocd flash, then resumes serial.
        Returns dict with success, output, error, command.
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
        use_pack = pack_path or self._find_pack(use_target)

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
        logger.info("Pausing serial on %s for flash", port_id)
        self.serial_manager.pause_port(port_id)

        try:
            logger.info("Running: %s", cmd_str)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "command": cmd_str,
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
        finally:
            logger.info("Resuming serial on %s", port_id)
            self.serial_manager.resume_port(port_id)
