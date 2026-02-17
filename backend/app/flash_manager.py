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

    def install_packs(self):
        """Install all .pack files in the pack directory to pyocd cache."""
        if not self.pack_dir.exists():
            return

        packs = sorted(self.pack_dir.glob("*.pack"))
        if not packs:
            return

        # Check if packs are already installed by listing targets
        # This is faster than reinstalling every time
        try:
            result = subprocess.run(["pyocd", "list", "--targets"], capture_output=True, text=True)
            installed_targets = result.stdout
        except Exception:
            installed_targets = ""

        for p in packs:
            try:
                # Simple heuristic: if pack name (e.g. EFR32FG28) is in installed targets, skip
                # This avoids re-parsing 18MB packs on every boot
                pack_family = p.stem.split('_')[2] if len(p.stem.split('_')) > 2 else p.stem
                if pack_family in installed_targets:
                    logger.info("Pack %s already installed, skipping.", p.name)
                    continue

                logger.info("Installing pack: %s", p.name)
                subprocess.run(["pyocd", "pack", "install", str(p)], check=True, capture_output=True)
            except Exception as e:
                logger.error("Failed to install pack %s: %s", p.name, e)


    def flash(
        self,
        port_id: str,
        hex_path: str,
        pack_path: Optional[str] = None,
        target: Optional[str] = None,
        frequency: Optional[str] = None,
    ) -> dict:
        """Flash a hex file to the device identified by port_id.

        Runs pyocd flash WITHOUT pausing serial reading.
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
        
        # If pack is installed, we don't need to pass it explicitly
        # But if the user uploaded a specific pack, use it
        use_pack = pack_path 
        
        # If no specific pack provided, check if we need to find one
        # Optimization: If we installed packs on startup, pyocd should find the target automatically
        # So we only pass --pack if explicitly requested or if auto-discovery fails
        if not use_pack:
            # Check if target is supported without pack
            # This is slow to check every time, so let's rely on installed packs
            pass

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
        
        # Only add --pack if explicitly provided (e.g. uploaded via API)
        # Otherwise rely on installed packs
        if use_pack:
            cmd.extend(["--pack", use_pack])

        cmd_str = " ".join(cmd)
        # logger.info("Pausing serial on %s for flash", port_id)
        # self.serial_manager.pause_port(port_id)

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
        # finally:
        #     logger.info("Resuming serial on %s", port_id)
        #     self.serial_manager.resume_port(port_id)
