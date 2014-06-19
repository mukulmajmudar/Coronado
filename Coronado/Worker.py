import json
import traceback
import sys

import tornado.web
from tornado import escape


class Worker(object):
    '''
    Abstract base class for workers.
    '''

    def __init__(self, handlers):
        self._handlers = [tornado.web.URLSpec(*spec) for spec in handlers]


    def setup(self):
        raise NotImplementedError()
        

    def queue(self, key, message, contentType, contentEncoding):
        '''
        Queue a message on the worker.
        '''
        raise NotImplementedError()


    def start(self):
        '''
        Start consuming messages from the queue.
        '''
        raise NotImplementedError()


    def _execute(self, key, message, contentType, contentEncoding):
        try:
            # Convert message to dictionary from JSON if content type is JSON
            if isinstance(message, str) and contentType == 'application/json':
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
                            WorkRequest(key, message), **spec.kwargs)
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

    _handlers = None


class WorkRequest(object):
    key = None
    message = None


    def __init__(self, key, message):
        self.key = key
        self.message = message


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
                raise ReqHandlerCfgError('A worker is required in order to ' +
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
