from cStringIO import StringIO
import traceback
import json
from functools import wraps

import tornado.web
from .HttpUtil import parseContentType
from .Context import Context

class ReqHandlerCfgError(Exception):
    pass


class RequestHandler(tornado.web.RequestHandler):
    context = None
    ioloop = None
    database = None
    httpClient = None

    def initialize(self, **kwargs):
        # Initialize context with defaults
        self.context = self._context = Context(
        {
            'allowedCORSOrigins': [],
            'sendEmailOnError': False,
            'errorEmailRecipient': None,
            'errorEmailSubject': '[ERROR] Server Error Occurred',
            'worker': None
        })

        # Update context with arguments
        self.context.update(kwargs)

        # Validate context
        if self._context['sendEmailOnError']:
            if self._context['errorEmailRecipient'] is None:
                raise ReqHandlerCfgError('errorEmailRecipient argument is ' +
                    'required in order to send errors')

            if self._context['worker'] is None:
                raise ReqHandlerCfgError('A worker is required in order to ' +
                    'send error emails')

        self.context.flattenOnto(self)


    def options(self, *args, **kwargs):
        pass


    def setCORSHeaders(self):
        # Manage cross-origin access
        allowedCORSOrigins = self.context['allowedCORSOrigins']
        if 'Origin' in self.request.headers \
                and (allowedCORSOrigins == 'any'
                        or self.request.headers['Origin'] in
                        self.context['allowedCORSOrigins']):
            self.set_header('Access-Control-Allow-Origin',
                    self.request.headers['Origin'])
            self.set_header('Access-Control-Allow-Methods',
                    'GET, POST, PUT, DELETE, OPTIONS')
            self.set_header('Access-Control-Allow-Credentials', 'true')
            if 'Access-Control-Request-Headers' in self.request.headers:
                self.set_header('Access-Control-Allow-Headers',
                    self.request.headers['Access-Control-Request-Headers'])

            if 'authTokenHeaderName' in self.context:
                self.set_header('Access-Control-Expose-Headers',
                        self.context['authTokenHeaderName'])


    def prepare(self):
        super(RequestHandler, self).prepare()
        self.setCORSHeaders()


    def write_error(self, status, **kwargs):    # pylint: disable=unused-argument
        self.setCORSHeaders()


    def log_exception(self, typ, value, tb):
        # Call parent version
        super(RequestHandler, self).log_exception(typ, value, tb)

        # If not sending error emails, return
        if not self.context.get('sendEmailOnError'):
            return

        # Ignore if HTTPError < 500
        if isinstance(value, tornado.web.HTTPError) and value.status_code < 500:
            return

        # Get a string of the stack trace
        tbStringIO = StringIO()
        traceback.print_exception(typ, value, tb, None, tbStringIO)
        tbString = tbStringIO.getvalue()

        # Send email to the configured recipient
        self._worker.request(self.context['emailWorkTag'],
        {
            'subject': self.context['errorEmailSubject'],
            'recipient': self.context['errorEmailRecipient'],
            'text': tbString
        })


    def data_received(self, chunk):
        pass


    def _getJsonBody(self, charset='UTF-8'):
        contentType, reqCharset = parseContentType(
                self.request.headers.get('Content-Type'))
        if contentType != 'application/json' or reqCharset != charset:
            raise tornado.web.HTTPError(415)
        try:
            return json.loads(self.request.body)
        except ValueError:
            raise tornado.web.HTTPError(415)


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
            except ValueError:
                raise tornado.web.HTTPError(415)
            else:
                func(self, *args, **kwargs)

        return wrapper

    return decorator


def finish(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            func(*args, **kwargs)
        finally:
            if not self._finished:
                self.finish()

    return wrapper
