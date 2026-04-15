import logging
from logging.config import dictConfig


_LOGGING_CONFIGURED = False


def setup_logging() -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
                }
            },
            'handlers': {
                'default': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'standard',
                    'level': 'INFO',
                }
            },
            'root': {'handlers': ['default'], 'level': 'INFO'},
        }
    )

    logging.getLogger(__name__).info('Logging initialized for V2 backend')
    _LOGGING_CONFIGURED = True
