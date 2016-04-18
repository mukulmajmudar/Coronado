class AppPlugin(object):
    def start(self, application, context):
        pass

    def destroy(self, application, context):
        pass


class CommandLinePlugin(object):

    def getConfig(self):
        return {}

    def setup(self, context):
        pass