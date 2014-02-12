import functools

import tornado.concurrent
from tornado.ioloop import IOLoop

def when(*args, **kwargs):
    '''
    A JQuery-like "when" function to gather futures and deal with maybe-futures.
    '''
    # If ioloop not given, use the current one
    ioloop = kwargs.get('ioloop', IOLoop.current())

    future = tornado.concurrent.Future()
    numDone = [0]
    numFutures = len(args)
    result = [None] * numFutures

    def onFutureDone(index, f):
        result[index] = f
        numDone[0] += 1
        if numDone[0] == numFutures:
            if numFutures > 1:
                future.set_result(result)
            else:
                tornado.concurrent.chain_future(f, future)

    index = 0
    for maybeFuture in args:
        if isinstance(maybeFuture, tornado.concurrent.Future):
            ioloop.add_future(maybeFuture, 
                    functools.partial(onFutureDone, index))
        else:
            # Make a future with the result set to the argument
            f = tornado.concurrent.Future()
            f.set_result(maybeFuture)
            onFutureDone(index, f)
        index += 1

    return future


def transform(future, callback, ioloop=None):
    '''
    A future transformer. Similar to JQuery's "deferred.then()".
    '''
    if ioloop is None:
        ioloop = IOLoop.current()
    newFuture = tornado.concurrent.Future()

    def onFutureDone(future):
        nextFuture = when(callback(future))
        tornado.concurrent.chain_future(nextFuture, newFuture)

    ioloop.add_future(future, onFutureDone)
    return newFuture
