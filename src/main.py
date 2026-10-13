import os
import signal
import sys
import threading
import time

import app_info
import utils.config as config
import utils.status as status
import utils.web as web
from core.scanner import Busy, Scanner
from core.store import Store
from utils.logger import logger


def problems():
    return [config.load_error] if config.load_error else []


def main():
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    scanner = Scanner(Store(os.path.join(config.config_dir, f"{app_info.SLUG}.db")))
    logger.log("STARTUP", f"Starting {app_info.NAME} web UI")
    threading.Thread(target=web.serve, args=(scanner,), daemon=True).start()
    if not config.libraries:
        logger.log("STARTUP", "No library folders set up yet. Add them in Settings > General")
    logger.log("STARTUP", f"{app_info.NAME} is running. Open the web UI on port {config.web_port}")

    last = scanner.results().get("scanned_at") or 0
    # A first scan a few minutes after starting, then on the schedule
    next_scan = max(time.time() + 180, last + config.scan_interval_hours * 3600)
    while True:
        status.heartbeat(problems())
        if time.time() >= next_scan and config.libraries:
            try:
                scanner.background(scanner.scan)
            except Busy:
                pass
            next_scan = time.time() + config.scan_interval_hours * 3600
        if not scanner.lock.locked():
            with scanner.lock:
                scanner.purge()
        time.sleep(60)


def handle_sigint(signum, frame):
    sys.exit(0)


if __name__ == "__main__":
    logger.info(f"{app_info.NAME} version {app_info.VERSION} starting")
    main()
