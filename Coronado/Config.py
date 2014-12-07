from .Application import Application

class Config(dict):

    def __init__(self, keys):
        keys = \
        [
            'appName',
            'appRoot',
            'appPackage',
            'appClass',
            'testPkg',
            'port',
            'uri',
            'mysql',
            'smtp',
            'admin',
            'apiVersions',
            'sendEmailOnError',
            'errorEmailRecipient',
            'errorEmailSubject',
            'allowedCORSOrigins',
            'worker',
            'emailWorkTag',
            'eventManager'
        ] + keys
        for key in keys:
            self[key] = getattr(self, '_get' + key[0].upper() + key[1:])()


    def _getAppName(self):
        '''
        A descriptive name for the application.
        '''
        return 'Coronado Application'


    def _getAppRoot(self):
        '''
        Root directory of the Coronado application.
        '''
        raise NotImplementedError()


    def _getAppPackage(self):
        raise NotImplementedError()


    def _getAppClass(self):
        return Application


    def _getTestPkg(self):
        '''
        Package containing tests and test config.
        '''
        return None


    def _getPort(self):
        '''
        Port on which to listen for requests.
        '''
        raise NotImplementedError()


    def _getUri(self):
        '''
        URI of this application.
        '''
        return 'http://127.0.0.1:%d' % (self['port'],)


    def _getMysql(self):
        '''
        MySQL parameters
        '''
        return \
        {
            'host': self._getMysqlHost(),
            'user': self._getMysqlUser(),
            'password': self._getMysqlPassword(),
            'dbName': self._getMysqlDbName(),
            'schemaFilePath': self._getMySchemaFilePath()
        }


    def _getMysqlHost(self):
        raise NotImplementedError()


    def _getMysqlUser(self):
        raise NotImplementedError()


    def _getMysqlPassword(self):
        raise NotImplementedError()


    def _getMysqlDbName(self):
        raise NotImplementedError()

    def _getMySchemaFilePath(self):
        raise NotImplementedError()

    def _getSmtp(self):
        '''
        SMTP parameters
        '''
        return \
        {
            'host': self._getSmtpHost(),
            'port': self._getSmtpPort(),
            'email': self._getSmtpEmail(),
            'password': self._getSmtpPassword()
        }


    def _getSmtpHost(self):
        raise NotImplementedError()


    def _getSmtpPort(self):
        raise NotImplementedError()


    def _getSmtpEmail(self):
        raise NotImplementedError()


    def _getSmtpPassword(self):
        raise NotImplementedError()


    def _getAdmin(self):
        return \
        {
            'name': self._getAdminName(),
            'email': self._getAdminEmail()
        }


    def _getAdminName(self):
        raise NotImplementedError()


    def _getAdminEmail(self):
        raise NotImplementedError()


    def _getApiVersions(self):
        return ['1']


    def _getSendEmailOnError(self):
        return True


    def _getErrorEmailRecipient(self):
        return self['admin']['email']


    def _getErrorEmailSubject(self):
        return '[ERROR][%s] Server Error Occurred' % (self['appName'],)


    def _getAllowedCORSOrigins(self):
        '''
        List of origins allowed to access this server
        '''
        return []


    def _getWorker(self):
        return None


    def _getEmailWorkTag(self):
        return '/sendEmail'


    def _getEventManager(self):
        return None
