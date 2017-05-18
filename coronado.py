#! ./bin/python
import sys
import time
import argparse
import traceback
import importlib.util
import collections
from functools import partial
import signal
import os
import logging
import asyncio

import argh

sys.path.append(os.getcwd())

logger = logging.getLogger(__name__)

config = None

def onSigTerm(context, signum, frame):
    logger.info('Caught signal %d, shutting down.', signum)
    if context['loop'].is_running():
        context['loop'].stop()


@argh.arg('-l', '--logLevel',
        help='one of "debug", "info", "warning", "error", and "critical"')
@argh.arg('--logFormat',
        help='Python-like log format (see Python docs for details)')
def start(logLevel='warning',
        logFormat='%(levelname)s:%(name)s (at %(asctime)s): %(message)s',
        *args, **kwargs):
    '''
    Start the application.
    '''
    logging.basicConfig(level=getattr(logging, logLevel.upper(),
        logging.NOTSET), format=logFormat)

    try:
        logger.info('Starting up...')

        context = kwargs.pop('context', {})

        # Initialize context to be a copy of the configuration
        context = config.copy()

        # Install SIGINT and SIGTERM handler
        signal.signal(signal.SIGINT, partial(onSigTerm, context))
        signal.signal(signal.SIGTERM, partial(onSigTerm, context))

        # Override with arguments, if any
        context.update(context)
        context.update(kwargs)

        # Add empty "shortcutAttrs" if not there already
        if 'shortcutAttrs' not in context:
            context['shortcutAttrs'] = []

        # Get event loop
        context['loop'] = loop = asyncio.get_event_loop()

        # Start app plugins
        context['appPlugins'] = collections.OrderedDict()
        for plugin in context['plugins']:
            appPluginClass = getattr(plugin, 'AppPlugin', False)
            if not appPluginClass:
                continue
            appPlugin = appPluginClass()
            startResult = appPlugin.start(context)
            if startResult:
                loop.run_until_complete(asyncio.ensure_future(startResult))
            context['appPlugins'][appPlugin.getId()] = appPlugin

        # Call app-specific start() if any
        startFn = getattr(context['appPackage'], 'start', False)
        if startFn:
            result = startFn(context)
            if result is not None:
                loop.run_until_complete(result)

        # Start event loop
        if context['startEventLoop']:
            loop.call_soon(
                    lambda: logger.info('Started event loop'))
            loop.run_forever()
    except Exception:
        raise argh.CommandError(traceback.format_exc())
    finally:
        destroy(context)
        logger.info('Shutdown complete.')


def destroy(context):
    '''
    Destroy the application.
    '''
    loop = context['loop']

    # Call app-specific destroy()
    destroyFn = getattr(context['appPackage'], 'destroy', False)
    if destroyFn:
        result = destroyFn()
        if result is not None:
            loop.run_until_complete(result)

    # Destroy app plugins
    pluginDestroyCoros = []
    for appPlugin in reversed(context['appPlugins'].values()):
        destroyResult = appPlugin.destroy(context)
        if destroyResult:
            pluginDestroyCoros.append(destroyResult)

    # Wait till all plugins are destroyed
    if pluginDestroyCoros:
        loop.run_until_complete(asyncio.wait(pluginDestroyCoros))

    loop.close()


def main():
    parser = argparse.ArgumentParser(description=config['appName'])

    # Add start command
    argh.add_commands(parser, [start])

    # Add commands from plugins
    for plugin in config['plugins']:
        clPluginClass = getattr(plugin, 'CommandLinePlugin', False)
        if not clPluginClass:
            continue

        # Create the command line plugin
        clPlugin = clPluginClass()

        context = config.copy()

        # Get event loop
        context['loop'] = asyncio.get_event_loop()

        # Add empty "shortcutAttrs" if not there already
        if 'shortcutAttrs' not in context:
            context['shortcutAttrs'] = []

        clPlugin.setup(context)

        clPluginConfig = clPlugin.getConfig()

        kwargs = {}
        if clPluginConfig.get('namespace'):
            kwargs = dict(title=clPluginConfig['title'],
                    namespace=clPluginConfig['name'])
        argh.add_commands(parser, clPluginConfig['commands'], **kwargs)

    # Dispatch command
    argh.dispatch(parser)


if __name__ == '__main__':
    configFilePath = None
    if len(sys.argv) > 1:
        configFilePath = sys.argv[1]
        if configFilePath.endswith('.py'):
            del sys.argv[1]

    # Default config file is called "Config.py"
    if configFilePath is None or not configFilePath.endswith('.py'):
        configFilePath = 'Config.py'

    # Import config file
    if not os.path.exists(configFilePath):
        sys.stderr.write('Config file ' + configFilePath + ' does not exist.\n')
        sys.exit(1)
    spec = importlib.util.spec_from_file_location('module.name', configFilePath)
    configMod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configMod)
    config = configMod.config

    main()
