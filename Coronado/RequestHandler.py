import tornado.web
import json

class ReqHandlerCfgError(Exception):
    pass


class RequestHandler(tornado.web.RequestHandler):
    context = None

    def initialize(self, **kwargs):
        # Initialize context with defaults
        self.context = \
        {
            'allowedCORSDomains': [],
            'sendEmailOnError': False,
            'errorEmailRecipient': None,
            'errorEmailSubject': '[ERROR] Server Error Occurred',
            'errorEmailer': None,
            'errorTemplateDir': None
        }

        # Update context with arguments
        self.context.update(kwargs)

        # Validate context
        if self.context['sendEmailOnError']:
            if self.context['emailRecipient'] is None:
                raise ReqHandlerCfgError(
                    'emailRecipient argument is required in order to send errors')

            if self.context['emailer'] is None:
                raise ReqHandlerCfgError(
                    'emailer argument is required in order to send errors.')

            if self.context['templateDir'] is None:
                raise ReqHandlerCfgError(
                    'templateDir argument is required in order to send errors.')

        self._ioloop = self.context['ioloop']
        self._database = self.context['database']
        self._httpClient = self.context['httpClient']


    def options(self, *args, **kwargs):
        pass


    def prepare(self):
        super(RequestHandler, self).prepare()

        # Manage cross-origin access
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self.context['allowedCORSDomains']:
            self.set_header('Access-Control-Allow-Origin', 
                    self.request.headers['Origin'])
            self.set_header('Access-Control-Allow-Methods', 
                    'GET, POST, PUT, DELETE, OPTIONS')
            self.set_header('Access-Control-Allow-Credentials', 'true')
            if 'Access-Control-Request-Headers' in self.request.headers:
                self.set_header('Access-Control-Allow-Headers', 
                    self.request.headers['Access-Control-Request-Headers'])

            self.set_header('Access-Control-Expose-Headers', 'Auth-Token')


    def write_error(self, status, **kwargs):
        # Allow cross-origin access to everyone
        if 'Origin' in self.request.headers \
                and self.request.headers['Origin'] \
                in self.context['allowedCORSDomains']:
            self.set_header('Access-Control-Allow-Origin', 
                    self.request.headers['Origin'])
            self.set_header('Access-Control-Allow-Methods', 
                    'GET, POST, PUT, DELETE, OPTIONS')
            self.set_header('Access-Control-Allow-Credentials', 'true')
            if 'Access-Control-Request-Headers' in self.request.headers:
                self.set_header('Access-Control-Allow-Headers', 
                        self.request.headers['Access-Control-Request-Headers'])

            self.set_header('Access-Control-Expose-Headers', 'Auth-Token')


    def send_error(self, status=500, **kwargs):
        if status >= 500 and self.context['sendEmailOnError']:
            # Send error email
            self.context['emailer'](
                    subject='[ERROR] CureCompanion Server Error Occurred',
                    recipient=self.context['emailRecipient'],
                    htmlFile=os.path.join(self.context['templateDir'],
                        'errorEmail.html'),
                    textFile=os.path.join(self.context['templateDir'],
                        'errorEmail.txt'),
                    templateArgs=dict(status=status))

        # Call super method
        super(RequestHandler, self).send_error(status, **kwargs)


    _ioloop = None
    _database = None
    _httpClient = None
