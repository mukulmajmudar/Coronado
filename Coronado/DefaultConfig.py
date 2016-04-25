from .Config import Config

class DefaultConfig(Config):

    def __init__(self, keys):
        super(DefaultConfig, self).__init__(
        [
            'appName',
            'appPackage',
            'appRoot',
            'plugins',
            'shutdownDelay',
            'testPkg'
        ] + keys)


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


    def _getPlugins(self):
        return []


    def _getShutdownDelay(self):
        return 5.0


    def _getTestPkg(self):
        '''
        Package containing tests and test config.
        '''
        return None
