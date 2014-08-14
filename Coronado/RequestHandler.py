import os
from cStringIO import StringIO
import traceback
import json
from functools import wraps

import tornado.web
from .HttpUtil import parseContentType

class ReqHandlerCfgError(Exception):
    pass


class RequestHandler(tornado.web.RequestHandler):

    def initialize(self, **kwargs):
        # Initialize context with defaults
        self._context = RequestHandler._Context(
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
                raise ReqHandlerCfgError('errorEmailRecipient argument is ' +
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


    def options(self, *args, **kwargs):
        pass


    def prepare(self):
        super(RequestHandler, self).prepare()

        # Manage cross-origin access
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self._context['allowedCORSOrigins']:
            self.set_header('Access-Control-Allow-Origin', 
                    self.request.headers['Origin'])
            self.set_header('Access-Control-Allow-Methods', 
                    'GET, POST, PUT, DELETE, OPTIONS')
            self.set_header('Access-Control-Allow-Credentials', 'true')
            if 'Access-Control-Request-Headers' in self.request.headers:
                self.set_header('Access-Control-Allow-Headers', 
                    self.request.headers['Access-Control-Request-Headers'])

            if 'authTokenHeaderName' in self._context:
                self.set_header('Access-Control-Expose-Headers', 
                        self._context['authTokenHeaderName'])


    def write_error(self, status, **kwargs):
        # Allow cross-origin access to everyone
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self._context['allowedCORSOrigins']:
            self.set_header('Access-Control-Allow-Origin', 
                    self.request.headers['Origin'])
            self.set_header('Access-Control-Allow-Methods', 
                    'GET, POST, PUT, DELETE, OPTIONS')
            self.set_header('Access-Control-Allow-Credentials', 'true')
            if 'Access-Control-Request-Headers' in self.request.headers:
                self.set_header('Access-Control-Allow-Headers', 
                        self.request.headers['Access-Control-Request-Headers'])

            if 'authTokenHeaderName' in self._context:
                self.set_header('Access-Control-Expose-Headers', 
                        self._context['authTokenHeaderName'])


    def log_exception(self, typ, value, tb):
        # Call parent version
        super(RequestHandler, self).log_exception(typ, value, tb)

        # If not sending error emails, return
        if not self._context.get('sendEmailOnError'):
            return

        # Ignore if HTTPError < 500
        if isinstance(value, tornado.web.HTTPError) and value.status_code < 500:
            return

        # Get a string of the stack trace
        tbStringIO = StringIO()
        traceback.print_exception(typ, value, tb, None, tbStringIO)
        tbString = tbStringIO.getvalue()

        # Send email to the configured recipient
        self._worker.request(self._context['emailWorkTag'], 
        {
            'subject': self._context['errorEmailSubject'],
            'recipient': self._context['errorEmailRecipient'],
            'text': tbString
        })


    def _getJsonBody(self, charset='UTF-8'):
        contentType, reqCharset = parseContentType(
                self.request.headers.get('Content-Type'))
        if contentType != 'application/json' or reqCharset != charset:
            raise tornado.web.HTTPError(415)
        try:
            return json.loads(self.request.body)
        except ValueError as e:
            raise tornado.web.HTTPError(415)


    class _Context(dict):
        getNewDbConnection = None


    _context = None
    _ioloop = None
    _database = None
    _httpClient = None


def withJsonBody(attrName='jsonBody', charset='UTF-8'):

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            contentType, reqCharset = parseContentType(
                    self.request.headers.get('Content-Type'))
            if contentType != 'application/json' or reqCharset != charset:
                raise tornado.web.HTTPError(415)
            try:
                setattr(self, attrName, json.loads(self.request.body))
            except ValueError as e:
                raise tornado.web.HTTPError(415)
            else:
                func(self, *args, **kwargs)

        return wrapper

    return decorator
