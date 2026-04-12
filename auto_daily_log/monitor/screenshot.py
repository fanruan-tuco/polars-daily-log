import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from .platforms.detect import get_current_platform

def capture_screenshot(output_dir: Path) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = output_dir / filename
    platform = get_current_platform()
    try:
        if platform == "macos":
            subprocess.run(["screencapture", "-x", str(filepath)], timeout=10, capture_output=True)
        elif platform == "windows":
            ps_script = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$bmp = New-Object System.Drawing.Bitmap("
                f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,"
                f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height);"
                f"$g = [System.Drawing.Graphics]::FromImage($bmp);"
                f"$g.CopyFromScreen(0,0,0,0,$bmp.Size);"
                f'$bmp.Save("{filepath}")'
            )
            subprocess.run(["powershell", "-Command", ps_script], timeout=30, capture_output=True)
        else:
            for tool_cmd in [
                ["gnome-screenshot", "-f", str(filepath)],
                ["import", "-window", "root", str(filepath)],
                ["scrot", str(filepath)],
                ["maim", str(filepath)],
            ]:
                try:
                    subprocess.run(tool_cmd, timeout=10, capture_output=True)
                    if filepath.exists(): break
                except FileNotFoundError: continue
        return filepath if filepath.exists() else None
    except (subprocess.TimeoutExpired, Exception):
        return None
