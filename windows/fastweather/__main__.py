"""Application entry point: `python -m fastweather` (and via the shim)."""

import argparse
import os

import wx

from .app import MainFrame
from .paths import user_data_dir


def _hold_app_mutex():
    """Hold a named mutex so the installer (AppMutex=WeatherFastRunning) can
    detect a running instance and wait for it to close during an update."""
    try:
        import ctypes
        from ctypes import wintypes
        create = ctypes.windll.kernel32.CreateMutexW
        # HANDLE is pointer-sized: without restype, ctypes returned a 32-bit
        # int, truncating the handle on 64-bit Windows (#115).
        create.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        create.restype = wintypes.HANDLE
        return create(None, False, "WeatherFastRunning")
    except Exception:
        return None


def main():
    app = wx.App()
    app._weatherfast_mutex = _hold_app_mutex()  # kept alive for the process

    parser = argparse.ArgumentParser(prog="WeatherFast", description="WeatherFast")
    parser.add_argument("--reset", action="store_true",
                        help="Reset (delete) the saved city data file")
    parser.add_argument("-c", "--config",
                        help="Path to a specific city data JSON file to use")
    args = parser.parse_args()

    app.SetAppName("WeatherFast")
    data_dir = user_data_dir()  # single source of truth (with legacy migration)

    city_file = args.config if args.config else os.path.join(data_dir, "city.json")

    if args.reset:
        if os.path.exists(city_file):
            try:
                os.remove(city_file)
                print(f"Reset complete: Removed {city_file}")
            except Exception as e:
                print(f"Error resetting data: {e}")
        else:
            print(f"No data file found at {city_file} to reset.")

    MainFrame(city_file).Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
