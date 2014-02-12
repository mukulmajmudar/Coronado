import os

import tornado.web

class ReqHandlerCfgError(Exception):
    pass


class RequestHandler(tornado.web.RequestHandler):

    def initialize(self, **kwargs):
        # Initialize context with defaults
        self._context = \
        {
            'allowedCORSOrigins': [],
            'sendEmailOnError': False,
            'errorEmailRecipient': None,
            'errorEmailSubject': '[ERROR] Server Error Occurred',
            'errorEmailer': None,
            'errorTemplatesDir': None
        }

        # Update context with arguments
        self._context.update(kwargs)

        # Validate context
        if self._context['sendEmailOnError']:
            if self._context['errorEmailRecipient'] is None:
                raise ReqHandlerCfgError('errorEmailRecipient argument is ' +
                    'required in order to send errors')

            if self._context['errorEmailer'] is None \
                    or not callable(self._context['errorEmailer']):
                raise ReqHandlerCfgError('errorEmailer argument is ' +
                    'required in order to send errors.')

            if self._context['errorTemplatesDir'] is None:
                raise ReqHandlerCfgError('errorTemplatesDir argument is ' +
                    'required in order to send errors.')

        self._ioloop = self._context['ioloop']
        self._database = self._context['database']
        self._httpClient = self._context['httpClient']


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

            self.set_header('Access-Control-Expose-Headers', 'Auth-Token')


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

            self.set_header('Access-Control-Expose-Headers', 'Auth-Token')


    def send_error(self, status=500, **kwargs):
        if status >= 500 and self._context['sendEmailOnError']:
            # Send error email
            self._context['errorEmailer'](
                    subject='[ERROR] CureCompanion Server Error Occurred',
                    recipient=self._context['errorEmailRecipient'],
                    htmlFile=os.path.join(self._context['errorTemplatesDir'],
                        'errorEmail.html'),
                    textFile=os.path.join(self._context['errorTemplatesDir'],
                        'errorEmail.txt'),
                    templateArgs=dict(status=status))

        # Call super method
        super(RequestHandler, self).send_error(status, **kwargs)


    _context = None
    _ioloop = None
    _database = None
    _httpClient = None
