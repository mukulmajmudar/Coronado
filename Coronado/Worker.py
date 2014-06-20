import json
import traceback
import sys
from datetime import timedelta
from functools import partial
from uuid import uuid4

import tornado.web
from tornado import escape
from tornado.ioloop import IOLoop

from Concurrent import when

class ResponseTimeout(Exception):
    pass

class Worker(object):
    '''
    Abstract base class for workers.
    '''

    def __init__(self, handlers, type, ioloop=None):
        self._handlers = [tornado.web.URLSpec(*spec) for spec in handlers]
        self._type = type
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()


    def setup(self):
        raise NotImplementedError()
        

    def queue(self, key=None, message='null', contentType='application/json',
            contentEncoding='utf-8', expectResponse=False,
            correlationId=None, **kwargs):
        '''
        Queue a message on the worker.

        Keyword arguments:
        ------------------
        key: Work key that is mapped to the work handler. For responses from 
          workers, it is OK to omit this argument (default: None).
        message: Message to queue (default: 'null')
        contentType: Content type of the message (default: 'application/json')
        contentEncoding: Encoding of the message (default: 'utf-8')
        expectResponse: Whether to expect a response for this 
          message (default: False)
        correlationId: If this message is a response, pass the request's
          correlation ID here (default: None).
        '''
        queueFuture = tornado.concurrent.Future()

        # Convert dictionaries and lists to JSON if content type is JSON
        if (isinstance(message, dict) or isinstance(message, list)) \
                and contentType == 'application/json':
            message = json.dumps(message, encoding=contentEncoding)

        # If no correlation ID given and we are expecting a response, generate
        # a correlation ID (just a plain old ID for the "request")
        if correlationId is None and expectResponse:
            correlationId = uuid4()

        # Delegate actual queueing to subclass method
        queueResult = self._queue(
                key=key, 
                message=message, 
                contentType=contentType,
                contentEncoding=contentEncoding, 
                correlationId=correlationId, 
                **kwargs)

        self._ioloop.add_future(when(queueResult),
                partial(self._onQueued, queueFuture, 
                    expectResponse, correlationId))

        return queueFuture


    def start(self):
        '''
        Start consuming messages from the queue.
        '''
        raise NotImplementedError()


    def _queue(self, key, message, contentType, contentEncoding,
            correlationId, **kwargs):
        '''
        Implementation method for subclasses to perform queueing.
        '''
        raise NotImplementedError()


    def _onQueued(self, queueFuture, expectResponse, correlationId, implFuture):
        '''
        When queue operation is complete, store correlation ID for requests
        '''
        try:
            # Trap exceptions, if any
            implFuture.result()
        except Exception as e:
            queueFuture.set_exception(e)
        else:
            # If we are expecting an response and a correlation ID was 
            # returned, we store our future for some time
            if expectResponse:
                assert(correlationId is not None)
                Worker._queueFutures[correlationId] = queueFuture

                # If our future is still stored after a while, remove it and
                # set an error on it
                def removeFuture():
                    if correlationId in Worker._queueFutures:
                        queueFuture.set_exception(ResponseTimeout())
                        del Worker._queueFutures[correlationId]
                self._ioloop.add_timeout(
                        Worker._responseTimeout, removeFuture)


    def _onMessage(self, key, message, contentType, contentEncoding,
            correlationId):
        '''
        Callback for handling messages, called by subclasses.
        '''
        # If this is a worker, execute route with message's key
        if self._type == 'worker':
            self._execute(key, message, contentType, contentEncoding, 
                    correlationId)
        elif self._type == 'proxy' and key is None:
            # If proxy and key is None, this is a response
            self._resolveRequest(correlationId, 
                    message, contentType, contentEncoding)


    def _execute(self, key, message, contentType, 
            contentEncoding, correlationId):
        try:
            # Convert message to dictionary from JSON if content type is JSON
            if contentType == 'application/json':
                message = json.loads(message, encoding=contentEncoding)

            # Find handler that matches the key. This code is mostly copied from 
            # Tornado v3.2's URL spec matching in tornado.web.Application.
            handler = None
            args = []
            kwargs = {}
            for spec in self._handlers:
                match = spec.regex.match(key)
                if match:
                    handler = spec.handler_class(
                        WorkRequest(key, message, correlationId), **spec.kwargs)
                    if spec.regex.groups:
                        # None-safe wrapper around url_unescape to handle
                        # unmatched optional groups correctly
                        def unquote(s):
                            if s is None:
                                return s
                            return escape.url_unescape(s, encoding=None,
                                                       plus=False)
                        # Pass matched groups to the handler.  Since
                        # match.groups() includes both named and unnamed groups,
                        # we want to use either groups or groupdict but not both.
                        # Note that args are passed as bytes so the handler can
                        # decide what encoding to use.

                        if spec.regex.groupindex:
                            kwargs = dict(
                                (str(k), unquote(v))
                                for (k, v) in match.groupdict().items())
                        else:
                            args = [unquote(s) for s in match.groups()]
                    break

            handler(*args, **kwargs)
        except:
            sys.stderr.write(traceback.format_exc() + '\n')
            sys.stderr.flush()


    def _resolveRequest(self, correlationId, result, 
            contentType, contentEncoding):
        '''
        Resolve the request with the given correlation ID.

        This should be called by subclasses of type 'proxy' when
        they receive a message without a key and .
        '''
        try:
            queueFuture = Worker._queueFutures[correlationId]
        except KeyError:
            pass
        else:
            # Convert message to dictionary from JSON if content type is JSON
            if contentType == 'application/json':
                result = json.loads(result, encoding=contentEncoding)
            else:
                result = \
                {
                    'contentType': contentType,
                    'contentEncoding': contentEncoding,
                    'body': result
                }
            queueFuture.set_result(result)
            del Worker._queueFutures[correlationId]



    # Non-public instance attributes
    _handlers = None
    _type = None
    _ioloop = None

    # Non-public class attributes
    _queueFutures = {}
    _responseTimeout = timedelta(seconds=60)


class WorkRequest(object):
    key = None
    message = None
    correlationId = None


    def __init__(self, key, message, correlationId):
        self.key = key
        self.message = message
        self.correlationId = correlationId


class WorkHandlerCfgError(Exception):
    pass


class WorkHandler(object):
    request = None


    def __init__(self, request, **kwargs):
        self.request = request

        # FIXME: The rest of this constructor is copied from 
        # Coronado RequestHandler's initialize() method. Find a way to
        # avoid code duplication

        # Initialize context with defaults
        self._context = WorkHandler._Context(
        {
            'allowedCORSOrigins': [],
            'sendEmailOnError': False,
            'errorEmailRecipient': None,
            'errorEmailSubject': '[ERROR] Server Error Occurred',
            'worker': None
        })

        # Update context with arguments
        self._context.update(kwargs)
        self._context.getNewDbConnection = kwargs.get('getNewDbConnection')

        # Validate context
        if self._context['sendEmailOnError']:
            if self._context['errorEmailRecipient'] is None:
                raise WorkHandlerCfgError('errorEmailRecipient argument is ' +
                    'required in order to send errors')

            if self._context['worker'] is None:
                raise WorkHandlerCfgError('A worker is required in order to ' +
                    'send error emails')

        self._ioloop = self._context['ioloop']
        self._database = self._context['database']
        self._httpClient = self._context['httpClient']

        # Store public and non-public context attributes as self's attributes 
        # for ease of access in request handlers
        try:
            for key in self._context['flatten']['public']:
                setattr(self, key, self._context[key])
        except KeyError:
            pass
        try:
            for key in self._context['flatten']['non-public']:
                setattr(self, '_' + key, self._context[key])
        except KeyError:
            pass


    def __call__(self):
        pass


    class _Context(dict):
        getNewDbConnection = None


    _context = None
