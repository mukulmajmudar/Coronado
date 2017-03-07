class AppPlugin(object):
    def start(self, context):
        '''
        Start the plugin. Can be a coroutine.
        '''
        pass

    def destroy(self, context):
        '''
        Destroy the plugin. Can be a coroutine.
        '''
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
