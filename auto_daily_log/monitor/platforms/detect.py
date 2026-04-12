import platform
from typing import Literal
from .base import PlatformAPI

PlatformType = Literal["macos", "windows", "linux"]

def get_current_platform() -> PlatformType:
    system = platform.system().lower()
    if system == "darwin": return "macos"
    elif system == "windows": return "windows"
    return "linux"

def get_platform_module() -> PlatformAPI:
    current = get_current_platform()
    if current == "macos":
        from .macos import MacOSAPI
        return MacOSAPI()
    elif current == "windows":
        from .windows import WindowsAPI
        return WindowsAPI()
    else:
        from .linux import LinuxAPI
        return LinuxAPI()
