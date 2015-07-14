from .Application import Application
from .Config import Config
from .Exceptions import ConfigurationError

class DefaultConfig(Config):

    def __init__(self, keys):
        super(DefaultConfig, self).__init__(
        [
            'admin',
            'allowedWSOrigins',
            'appClass',
            'appName',
            'appPackage',
            'appRoot',
            'errorEmailRecipient',
            'errorEmailSubject',
            'emailWorkTag',
            'eventManager',
            'plugins',
            'sendEmail',
            'sendEmailOnError',
            'shutdownDelay',
            'smtp',
            'testPkg',
            'worker',
        ] + keys)


    def _getAdmin(self):
        return \
        {
            'name': self._getAdminName(),
            'email': self._getAdminEmail()
        }


    def _getAdminName(self):
        return None


    def _getAdminEmail(self):
        return None


    def _getAllowedWSOrigins(self):
        '''
        List of origins allowed to access this server using WebSocket protocol.
        '''
        return []


    def _getAppClass(self):
        return Application


    def _getAppName(self):
        '''
        A descriptive name for the application.
        '''
        return 'Coronado Application'


    def _getAppPackage(self):
        raise NotImplementedError()


    def _getAppRoot(self):
        '''
        Root directory of the Coronado application.
        '''
        raise NotImplementedError()


    def _getErrorEmailRecipient(self):
        return self['admin']['email']


    def _getErrorEmailSubject(self):
        return '[ERROR][%s] Server Error Occurred' % (self['appName'],)


    def _getEmailWorkTag(self):
        return 'sendEmail'


    def _getEventManager(self):
        return None


    def _getPlugins(self):
        return []


    def _getSendEmail(self):
        '''
        Return True to enable SMTP-based email sending.
        '''
        return False


    def _getSendEmailOnError(self):
        return self['sendEmail']


    def _getShutdownDelay(self):
        return 5.0


    def _getSmtp(self):
        '''
        SMTP parameters
        '''
        if self['sendEmail']:
            return \
            {
                'host': self._getSmtpHost(),
                'port': self._getSmtpPort(),
                'email': self._getSmtpEmail(),
                'password': self._getSmtpPassword()
            }
        else:
            return None


    def _getSmtpHost(self):
        raise NotImplementedError()


    def _getSmtpPort(self):
        raise NotImplementedError()


    def _getSmtpEmail(self):
        raise NotImplementedError()


    def _getSmtpPassword(self):
        raise NotImplementedError()


    def _getTestPkg(self):
        '''
        Package containing tests and test config.
        '''
        return None


    def _getWorker(self):
        return None


    def validate(self):
        if self['sendEmail']:
            if self['worker'] is None:
                raise ConfigurationError(
                        'A worker is required for sending emails')

        if self['sendEmailOnError']:
            if not self['sendEmail']:
                raise ConfigurationError(
                        'sendEmail is required to be set for sendEmailOnError')

            # Make sure errorEmailRecipient is given if sending emails on error
            if self['errorEmailRecipient'] is None:
                raise ConfigurationError(
                        'errorEmailRecipient is required for sendEmailOnError')
