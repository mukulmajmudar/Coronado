import logging
from functools import wraps
import argh

def configureLogging(level, **kwargs):
    if isinstance(level, str):
        level = getattr(logging, level.upper(), None)
        if not isinstance(level, int):
            raise ValueError('Invalid log level: %s' % level)

    logging.basicConfig(level=level, **kwargs)


def withDefaultLogging(func):
    '''
    Modifies a function to add argh-style logging arguments.

    Default log level is "warning" and default log format is:
    %(levelname)s:%(name)s (at %(asctime)s): %(message)s
    '''

    @argh.arg('-l', '--logLevel',
            help='one of "debug", "info", "warning", "error", and "critical"')
    @argh.arg('--logFormat',
            help='Python-like log format (see Python docs for details)')
    @wraps(func)
    def wrapper(*args, **kwargs):
        logLevel = kwargs.pop('logLevel', 'warning')
        logFormat = kwargs.pop('logFormat',
                '%(levelname)s:%(name)s (at %(asctime)s): %(message)s')

        configureLogging(level=logLevel, format=logFormat)
        func(*args, **kwargs)

    return wrapper
