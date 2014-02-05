import os

import tornado.web

class ReqHandlerCfgError(Exception):
    pass


class RequestHandler(tornado.web.RequestHandler):
    context = None

    def initialize(self, **kwargs):
        # Initialize context with defaults
        self.context = \
        {
            'allowedCORSOrigins': [],
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
            if self.context['errorEmailRecipient'] is None:
                raise ReqHandlerCfgError('errorEmailRecipient argument is ' +
                    'required in order to send errors')

            if self.context['errorEmailer'] is None \
                    or not callable(self.context['errorEmailer']):
                raise ReqHandlerCfgError('errorEmailer argument is ' +
                    'required in order to send errors.')

            if self.context['errorTemplateDir'] is None:
                raise ReqHandlerCfgError('errorTemplateDir argument is ' +
                    'required in order to send errors.')

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
                in self.context['allowedCORSOrigins']:
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
                in self.context['allowedCORSOrigins']:
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
            self.context['errorEmailer'](
                    subject='[ERROR] CureCompanion Server Error Occurred',
                    recipient=self.context['errorEmailRecipient'],
                    htmlFile=os.path.join(self.context['errorTemplateDir'],
                        'errorEmail.html'),
                    textFile=os.path.join(self.context['errorTemplateDir'],
                        'errorEmail.txt'),
                    templateArgs=dict(status=status))

        # Call super method
        super(RequestHandler, self).send_error(status, **kwargs)


    _ioloop = None
    _database = None
    _httpClient = None
