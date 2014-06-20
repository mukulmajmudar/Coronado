import logging

def configureLogging(level, **kwargs):
    if isinstance(level, str):
        level = getattr(logging, level.upper(), None)
        if not isinstance(level, int):
            raise ValueError('Invalid log level: %s' % level)

    logging.basicConfig(level=level, **kwargs)
