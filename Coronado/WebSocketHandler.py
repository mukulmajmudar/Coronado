from cStringIO import StringIO
import traceback

import tornado.websocket

from .RequestHandler import RequestHandler, ReqHandlerCfgError

# pylint: disable=abstract-method
class WebSocketHandler(tornado.websocket.WebSocketHandler):
    context = None
    ioloop = None
    database = None
    httpClient = None

    def __init__(self, *args, **kwargs):
        super(WebSocketHandler, self).__init__(*args)

        # Initialize context with defaults
        self.context = RequestHandler._Context(
        {
            'allowedWSOrigins': [],
            'sendEmailOnError': False,
            'errorEmailRecipient': None,
            'errorEmailSubject': '[ERROR] Server Error Occurred',
            'worker': None
        })

        # Update context with arguments
        self.context.update(kwargs)
        self.context.getNewDbConnection = kwargs.get('getNewDbConnection')

        # Validate context
        if self.context['sendEmailOnError']:
            if self.context['errorEmailRecipient'] is None:
                raise ReqHandlerCfgError('errorEmailRecipient argument is ' +
                    'required in order to send errors')

            if self.context['worker'] is None:
                raise ReqHandlerCfgError('A worker is required in order to ' +
                    'send error emails')

        self.ioloop = self.context['ioloop']
        self.database = self.context['database']
        self.httpClient = self.context['httpClient']

        # Store public and non-public context attributes as self's attributes
        # for ease of access in request handlers
        try:
            for key in self.context['flatten']['public']:
                setattr(self, key, self.context[key])
        except KeyError:
            pass
        try:
            for key in self.context['flatten']['non-public']:
                setattr(self, '_' + key, self.context[key])
        except KeyError:
            pass


    def check_origin(self, origin):
        return origin in self.context['allowedWSOrigins']


    def options(self, *args, **kwargs):
        pass


    def prepare(self):
        super(WebSocketHandler, self).prepare()

        # Manage cross-origin access
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self.context['allowedCORSOrigins']:
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


    def write_error(self, status, **kwargs):    # pylint: disable=unused-argument
        # Allow cross-origin access to everyone
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self.context['allowedCORSOrigins']:
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


    def log_exception(self, typ, value, tb):
        # Call parent version
        super(WebSocketHandler, self).log_exception(typ, value, tb)

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
