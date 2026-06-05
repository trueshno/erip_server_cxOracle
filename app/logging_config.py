# -*- coding: utf-8 -*-
import logging
import structlog
from pathlib import Path

def setup_logging(level: str = "INFO"):
    log_path = Path(__file__).parent.parent / "logs"
    log_path.mkdir(exist_ok=True)
    log_file = log_path / "app.log"

    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        handlers=[
            logging.StreamHandler(),  # Вывод в консоль/терминал
            logging.FileHandler(log_file, encoding="utf-8")  # Вывод в файл
        ]
    )

    # Настройка structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            # Читаемый текст без цветов (идеально для IDE)
            structlog.dev.ConsoleRenderer(colors=False)
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )