import os
import logging
import structlog
from logging.handlers import RotatingFileHandler

def setup_logging(level="INFO"):
    os.makedirs("logs", exist_ok=True)

    main_handler = RotatingFileHandler(
        "logs/app.log", 
        maxBytes=10 * 1024 * 1024,  # 10 МБ
        backupCount=5, 
        encoding="utf-8"
    )
    
    audit_handler = RotatingFileHandler(
        "logs/audit.log", 
        maxBytes=10 * 1024 * 1024,  # 10 МБ
        backupCount=5, 
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    main_handler.setFormatter(formatter)
    audit_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[main_handler])
    
    audit_std_logger = logging.getLogger("audit")
    audit_std_logger.setLevel(level)
    audit_std_logger.addHandler(audit_handler)
    audit_std_logger.propagate = False 

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if level == "INFO" else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )