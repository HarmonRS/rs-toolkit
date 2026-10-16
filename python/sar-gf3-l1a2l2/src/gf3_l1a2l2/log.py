from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def configure_logging(output_dir: Path, level: str = "INFO") -> logging.Logger:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("gf3_l1a2l2")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addHandler(console)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(log_dir / f"gf3_l1a2l2_{timestamp}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    return logger
