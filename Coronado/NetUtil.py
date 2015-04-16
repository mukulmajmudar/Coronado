from functools import wraps
import logging
import time

from tornado.ioloop import IOLoop
import tornado.concurrent

from .Concurrent import when

logger = logging.getLogger(__name__)

class Timeout(Exception):
    pass


def exponentialBackoff(firstRetryDelay=1, maxDelay=32):
    '''
    Asynchronous exponential backoff implementation.
    '''

    def decorator(func):
        retryDelaySecs = [firstRetryDelay]
        totalDelay = [0]
        ioloop = [None]

        def retry(*args, **kwargs):
            retryFuture = tornado.concurrent.Future()

            # If max delay has been reached, time out
            if totalDelay[0] >= maxDelay:
                logger.info('Maximum delay of %.2f has been exceeded.',
                        maxDelay)
                raise Timeout()

            # Override by minimum delay from argument, if any
            minDelay = kwargs.get('minDelay', retryDelaySecs[0])
            if minDelay is None:
                minDelay = retryDelaySecs[0]
            retryDelaySecs[0] = min(minDelay, retryDelaySecs[0])

            # maxDelay is the ceiling
            nextTotalDelay = totalDelay[0] + retryDelaySecs[0]
            if  nextTotalDelay > maxDelay:
                retryDelaySecs[0] -= nextTotalDelay - maxDelay
                logger.info('retryDelaySecs clamped to %.2f', retryDelaySecs[0])

            def _retry():
                '''
                Call wrapper function and chain result future.
                '''

                def onResult(resultFuture):
                    tornado.concurrent.chain_future(resultFuture, retryFuture)

                logger.info('Retrying...')
                ioloop[0].add_future(when(wrapper(*args, **kwargs)),
                        onResult)

                # Add to total delay
                totalDelay[0] += retryDelaySecs[0]

                logger.info('Total delay so far: %.2f seconds', totalDelay[0])

                # Exponentially increase delay time
                retryDelaySecs[0] = retryDelaySecs[0] * 2


            # Retry after calculated delay
            logger.info('Will retry after %.2f seconds.', retryDelaySecs[0])
            ioloop[0].add_timeout(time.time() + retryDelaySecs[0], _retry)

            return retryFuture


        @wraps(func)
        def wrapper(*args, **kwargs):
            # Add retry as an argument to the decoratee
            args = list(args)
            args.append(retry)
            ioloop[0] = kwargs.get('ioloop', IOLoop.current())
            return func(*args, **kwargs)

        return wrapper

    return decorator
