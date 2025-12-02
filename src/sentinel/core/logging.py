import logging
import sys
import structlog

def setup_logging() -> None:
    """
    Configures the logging for the application using structlog to produce JSON formatted logs.
    """
    
    # Common processors for all logs (timestamp, level, etc)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.JSONRenderer(), # Transforma o log em JSON
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO
    )