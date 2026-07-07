"""DriveScope launcher: starts the local server and opens the browser.
Robust: finds a free port, keeps the window open, and prints any startup error."""
import threading, webbrowser, sys, os, socket, traceback

HOST = "127.0.0.1"
PORTS = [8000, 8001, 8002, 8050, 8080]


def _free_port():
    for p in PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, p)) != 0:   # nothing listening -> free
                return p
    return PORTS[0]


def main():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)
    if base not in sys.path:
        sys.path.insert(0, base)
    try:
        import uvicorn
        from drivescope.api import app  # import early so errors surface here, not silently
        port = _free_port()
        url = f"http://{HOST}:{port}"
        print("=" * 60)
        print("  DriveScope is running.")
        print(f"  Open your browser at:  {url}")
        print("  (a browser window should open automatically)")
        print("  Keep THIS window open. Close it to stop the tool.")
        print("=" * 60)
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host=HOST, port=port, log_level="warning")
    except Exception:
        print("\n" + "!" * 60)
        print("  DriveScope failed to start. Details below:")
        print("!" * 60)
        traceback.print_exc()
        print("\nCopy the text above when asking for help.")
    finally:
        try:
            input("\nPress Enter to close this window…")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
