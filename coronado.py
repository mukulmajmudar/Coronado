#! ./bin/python
import sys
import argparse
import traceback
import importlib.util
from functools import partial
import signal
import os
import logging

import argh

sys.path.append(os.getcwd())

import Coronado
from Coronado.Application import Application

logger = logging.getLogger(__name__)

config = None

# pylint: disable=all
def onSigTerm(app, signum, frame):
    logger.info('Caught signal %d, shutting down.', signum)
    app._destroy()


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
    Coronado.configureLogging(level=logLevel, format=logFormat)

    app = None
    try:
        app = Application(config)

        # Install SIGINT and SIGTERM handler
        signal.signal(signal.SIGINT, partial(onSigTerm, app))
        signal.signal(signal.SIGTERM, partial(onSigTerm, app))

        logger.info('Starting application')
        app._start(*args, **kwargs)

    except Exception:
        raise argh.CommandError(traceback.format_exc())
    finally:
        if app is not None:
            app._destroy()


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
        clPlugin.setup(config.copy())

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
