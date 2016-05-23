import logging
import time
import collections
import functools

import tornado.ioloop

from .Concurrent import when

logger = logging.getLogger(__name__)

class Application(object):
    '''
    Coronado Application base class.

    Enables easier testability.
    See testing pattern recommended by Bret Taylor (creator of Tornado) at:
    https://groups.google.com/d/msg/python-tornado/hnz7JmXqEKk/S2zkl6L9ctEJ
    '''

    config = None
    context = None
    started = False

    def __init__(self, config):
        self.config = config
        self._destroyed = False


    # pylint: disable=unused-argument
    def _start(self, *args, **kwargs):
        context = kwargs.pop('context', {})

        # Initialize context to be a copy of the configuration
        self.context = self.config.copy()

        # Override with arguments, if any
        self.context.update(context)
        self.context.update(kwargs)

        # Assign default IOLoop instance
        if 'ioloop' not in self.context:
            self.context['ioloop'] = tornado.ioloop.IOLoop.instance()

        # Add empty "shortcutAttrs" if not there already
        if 'shortcutAttrs' not in self.context:
            self.context['shortcutAttrs'] = []

        # Start app plugins
        self.context['appPlugins'] = collections.OrderedDict()
        for plugin in self.context['plugins']:
            appPluginClass = getattr(plugin, 'AppPlugin', False)
            if not appPluginClass:
                continue
            appPlugin = appPluginClass()
            appPlugin.start(self, self.context)
            self.context['appPlugins'][appPlugin.getId()] = appPlugin

        # Add ioloop as a shortcut
        self.context['shortcutAttrs'].append('ioloop')

        # Call app-specific start()
        startFn = getattr(self.context['appPackage'], 'start', False)
        if startFn:
            self.context['ioloop'].run_sync(
                    functools.partial(startFn, self.context))

        self.started = True

        # Start event loop
        if self.context['startEventLoop']:
            self.context['ioloop'].start()


    def _destroy(self):
        # If already destroyed, do nothing
        if not self.started or self._destroyed:
            return

        # Call app-specific destroy()
        destroyFn = getattr(self.context['appPackage'], 'destroy', False)
        if destroyFn:
            destroyFn()

        # Destroy app plugins
        pluginFutures = []
        for appPlugin in reversed(self.context['appPlugins'].values()):
            pluginFutures.append(appPlugin.destroy(self, self.context))

        def onPluginsDestroyed(futuresFuture):
            futures = futuresFuture.result()
            if isinstance(futures, list):
                for f in futures:
                    f.result()

            # Stop event loop after a delay
            delaySeconds = self.context['shutdownDelay']

            def stop():
                self.context['ioloop'].stop()
                self._destroyed = True
                logger.info('Event loop has been shut down.')

            logger.info('Event loop will be shut down in %d seconds',
                    delaySeconds)
            self.context['ioloop'].add_timeout(time.time() + delaySeconds, stop)

        self.context['ioloop'].add_future(when(*pluginFutures),
                onPluginsDestroyed)


    _destroyed = None
