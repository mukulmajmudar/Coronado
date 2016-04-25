class AppPlugin(object):
    def start(self, application, context):
        pass

    def destroy(self, application, context):
        pass

    def getId(self):
        '''
        Get ID of the plugin.
        '''
        raise NotImplementedError()


class CommandLinePlugin(object):

    def getConfig(self):
        return {}

    def setup(self, context):
        pass
