import json
import traceback
import sys
from datetime import timedelta
from functools import partial
from uuid import uuid4
import logging

import tornado.web
from tornado import escape
from tornado.ioloop import IOLoop

from Concurrent import when

# Logger for this module
logger = logging.getLogger(__name__)

class RequestError(Exception):
    pass


class ResponseTimeout(RequestError):
    pass


class WorkerInterface(object):

    def setup(self):
        raise NotImplementedError()


    def start(self):
        raise NotImplementedError()


    def stop(self):
        raise NotImplementedError()


class WorkerProxy(WorkerInterface):

    def __init__(self, ioloop=None):
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()


    def request(self, tag, body, contentType='application/json',
            contentEncoding='utf-8', expectResponse=False, 
            timeout=timedelta(seconds=60), **kwargs):
        '''
        Send a request to a worker.

        Keyword arguments:
        ------------------
        tag: Work tag that is mapped to the desired work handler.
        body: Request body
        contentType: Content type of the body (default: 'application/json')
        contentEncoding: Encoding of the body (default: 'utf-8')
        expectResponse: Whether to expect a response for this 
          request (default: False)
        timeout: Timeout for the request (default: 60 seconds)
        '''

        logger.info('Sending request with tag %s to worker', tag)

        requestFuture = tornado.concurrent.Future()

        # Convert dictionaries and lists to JSON if content type is JSON
        if (isinstance(body, dict) or isinstance(body, list)) \
                and contentType == 'application/json':
            body = json.dumps(body, encoding=contentEncoding)

        # If we are expecting a response, generate a request ID 
        requestId = expectResponse and uuid4().hex or None

        # Delegate actual sending to subclass
        requestResult = self._request(
                id=requestId,
                tag=tag, 
                body=body, 
                contentType=contentType,
                contentEncoding=contentEncoding, 
                **kwargs)

        self._ioloop.add_future(when(requestResult),
                partial(self._onRequestSent, requestFuture, 
                    expectResponse, requestId, timeout))

        return requestFuture


    def _request(self, id, tag, body, contentType, contentEncoding,
            **kwargs):
        '''
        Implementation method for subclasses to send work requests.
        '''
        raise NotImplementedError()


    def _onRequestSent(self, requestFuture, expectResponse, requestId, 
            timeout, implFuture):
        '''
        When request is sent, store request ID, if set
        '''
        try:
            # Trap exceptions, if any
            implFuture.result()
        except Exception as e:
            requestFuture.set_exception(e)
        else:
            logger.info('Worker request sent')
            # If we are expecting a response, we store our future for some time
            if expectResponse:
                assert(requestId is not None)
                WorkerProxy._requestFutures[requestId] = requestFuture

                # If our future is still stored after a while, remove it and
                # set an error on it
                # TODO: Remove timeout on successful response
                def removeFuture():
                    if requestId in WorkerProxy._requestFutures:
                        logger.info('Worker request timed out')
                        requestFuture.set_exception(ResponseTimeout())
                        del WorkerProxy._requestFutures[requestId]
                self._ioloop.add_timeout(timeout, removeFuture)
            else:
                # Not expecting a response and the request has been sent, so
                # resolve the request future
                requestFuture.set_result(None)


    def _onResponse(self, requestId, body, contentType, contentEncoding):
        '''
        Resolve the request with the given ID.

        This should be called by subclasses when they receive a response.
        '''
        logger.info('Response received for request %s (partial): %s', 
                requestId, body[0:100])
        try:
            requestFuture = WorkerProxy._requestFutures[requestId]
        except KeyError:
            logger.info('No known request with ID %s (maybe timed out)',
                    requestId)
        else:
            # Convert body to dictionary from JSON if content type is JSON
            if contentType == 'application/json':
                response = json.loads(body, encoding=contentEncoding)

                # Set exception if error returned
                if isinstance(response, dict):
                    error = response.get('error')
                    if error:
                        requestFuture.set_exception(RequestError(error))
                    else:
                        # No error, so set result
                        requestFuture.set_result(response)
                else:
                    requestFuture.set_result(response)
            else:
                response = \
                {
                    'contentType': contentType,
                    'contentEncoding': contentEncoding,
                    'body': body
                }
                requestFuture.set_result(response)
            del WorkerProxy._requestFutures[requestId]


    # Non-public instance attributes
    _ioloop = None


    # Non-public class attributes
    _requestFutures = {}


class Worker(WorkerInterface):
    '''
    Abstract base class for workers.
    '''

    def __init__(self, handlers, type, ioloop=None):
        self._handlers = [tornado.web.URLSpec(*spec) for spec in handlers]
        self._type = type
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()


    def respond(self, requestId, replyTo, body, contentType, contentEncoding):
        raise NotImplementedError()


    def _onRequest(self, id, tag, body, contentType, contentEncoding, replyTo):
        '''
        Callback for handling messages, called by subclasses.
        '''
        logger.info('Request received for tag %s (may be partial): %s', 
                tag, body[0:50])
        logger.debug('Request ID: %s', id)
        logger.debug('Request body (may be partial): %s', body[0:1000])
        try:
            # Convert body to dictionary from JSON if content type is JSON
            if contentType == 'application/json':
                body = json.loads(body, encoding=contentEncoding)

            # Find handler for the given work tag
            handler, args, kwargs = self._findHandler(
                    id, tag, body, contentType, contentEncoding)
            if handler is None:
                raise RequestError('No handler found for tag %s' % (tag,))

            # Call the work handler
            result = handler(*args, **kwargs)

        except Exception as e:
            trace = traceback.format_exc()
            logging.error(trace)

            # If response expected, return an error response
            if id is not None:
                self.respond(id, replyTo, json.dumps({'error': str(e)}), 
                        'application/json', 'utf-8')
        else:
            # If no request ID, don't do anything
            if id is None:
                return

            # Respond when the worker operation is complete
            self._ioloop.add_future(when(result), 
                    partial(self._respond, id, replyTo))


    def _findHandler(self, id, tag, body, contentType, contentEncoding):
        # Find handler that matches the given tag. This code is mostly copied 
        # from Tornado v3.2's URL spec matching in tornado.web.Application.
        handler = None
        args = []
        kwargs = {}
        for spec in self._handlers:
            match = spec.regex.match(tag)
            if match:
                handler = spec.handler_class(
                    WorkRequest(id, tag, body, contentType, 
                        contentEncoding), **spec.kwargs)
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

        return handler, args, kwargs


    def _respond(self, requestId, replyTo, resultFuture):
        try:
            result = resultFuture.result()
        except Exception as e:
            trace = traceback.format_exc()
            logging.error(trace)

            self.respond(requestId, replyTo, json.dumps(dict(error=str(e))),
                    'application/json', 'utf-8')
        else:
            # Respond with the worker's result
            if result is None or isinstance(result, dict) \
                    or isinstance(result, list):
                result = json.dumps(result, encoding='utf-8')
                contentType = 'application/json'
                contentEncoding = 'utf-8'
            elif isinstance(result, tuple):
                result, contentType, contentEncoding = result
            else:
                # Other return values not supported
                logging.warning('Result value of type %s not supported', 
                        str(type(result)))
                self.respond(requestId, replyTo, json.dumps(
                    dict(error='Worker error: unsupported result type')),
                    'application/json', 'utf-8')
                return

            self.respond(requestId, replyTo, result, contentType, 
                    contentEncoding)


    # Non-public instance attributes
    _handlers = None
    _type = None
    _ioloop = None


class WorkRequest(object):
    # Public instance attributes
    id = None
    tag = None
    body = None
    contentType = None
    contentEncoding = None


    def __init__(self, id, tag, body, contentType, contentEncoding):
        self.id = id
        self.tag = tag
        self.body = body
        self.contentType = contentType
        self.contentEncoding = contentEncoding


class WorkHandlerCfgError(Exception):
    pass


class WorkHandler(object):
    # Public instance attributes
    request = None
    ioloop = None
    database = None
    httpClient = None


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

        self.ioloop = self._ioloop = self._context['ioloop']
        self.database = self._database = self._context['database']
        self.httpClient = self._httpClient = self._context['httpClient']

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
        '''
        Execution method for the worker. 
        
        Implement this with your own domain logic. Any return value from
        this method will be sent back to the requestor, but only if it is 
        expecting a response. If the operation this method performs is 
        asynchronous, return a future.
        '''
        raise NotImplementedError()


    class _Context(dict):
        getNewDbConnection = None


    # Non-public instance attributes
    _context = None
