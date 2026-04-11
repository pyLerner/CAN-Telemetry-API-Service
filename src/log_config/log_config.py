import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(log_file: str | Path) -> logging.Logger:
    """Create logger with rotating file handler."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("can-telemetry")
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        fh = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(fh)
    return logger
