import logging
import sys

logger = logging.getLogger("stt-service")

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
