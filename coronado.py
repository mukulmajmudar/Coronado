#! ./bin/python
import sys
import argparse
import argh
import traceback
import multiprocessing
from functools import partial
import signal
import os
import json
import logging

sys.path.append(os.getcwd())

from Config import config
import Coronado

logger = logging.getLogger(__name__)

def startInTestMode(fixture, comprehensive, server, workers, numWorkers, 
        *args, **kwargs):
    global config
    scaffold = None
    try:
        testsMod = __import__(config['testPkg'].__name__ + '.TestConfig')
        config = testsMod.TestConfig.config

        def startTestApp(fixture, stdinFileNo=None):
            if stdinFileNo is not None:
                sys.stdin = os.fdopen(stdinFileNo)

            # Setup a testing scaffold
            scaffold = Coronado.Testing.Scaffold(config, config['appClass'],
                    *args, **kwargs)
            scaffold.setup()
            app = scaffold.app

            # Load test fixture if any
            if fixture is not None:
                fixture = json.load(open(fixture))
                Coronado.Testing.installFixture(
                        app.context['database'], fixture)

            # Install SIGTERM handler
            signal.signal(signal.SIGTERM, partial(onSigTerm, scaffold))

            # Start listening for requests
            scaffold.app.startListening()

            logger.info('Started web server')

            # Start async event loop
            scaffold.app.startEventLoop()

        if workers:
            logger.info('Starting workers...')

            # Setup a testing scaffold
            scaffold = Coronado.Testing.Scaffold(config, config['appClass'],
                    *args, **kwargs)
            scaffold.setup()
            app = scaffold.app

            # Load test fixture if any
            if fixture is not None:
                fixture = json.load(open(fixture))
                Coronado.Testing.installFixture(
                        app.context['database'], fixture)

            startWorkers(numWorkers, *args, **kwargs)
        elif server:
            logger.info('Starting web server...')
            startTestApp(fixture)
        elif comprehensive:
            logger.info('Starting web server and workers...')

            # Start web server
            p = multiprocessing.Process(target=startTestApp, 
                    args=(fixture, sys.stdin.fileno()))
            p.start()

            # Start workers
            startWorkers(numWorkers, *args, **kwargs)

            p.join()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise argh.CommandError(traceback.format_exc())
    finally:
        if scaffold is not None:
            scaffold.destroy()

def onSigTerm(app, signum, frame):
    logger.info('Caught signal %d, shutting down.', signum)
    app.destroy()


def startApp(workerMode=False, *args, **kwargs):
    global config
    app = None
    try:
        app = config['appClass'](config, workerMode, *args, **kwargs)
        app.prepare()

        # Install SIGINT and SIGTERM handler
        signal.signal(signal.SIGINT, partial(onSigTerm, app))
        signal.signal(signal.SIGTERM, partial(onSigTerm, app))

        # Start listening for requests
        app.startListening()

        logger.info(workerMode and 'Started worker' or 'Started web server')

        # Start async event loop
        app.startEventLoop()

    except Exception as e:
        raise argh.CommandError(traceback.format_exc())
    finally:
        if app is not None:
            app.destroy()


def onSigForChildren(processes, signum, frame):
    logger.info('Caught signal %d, shutting down all children.', signum)
    for p in processes:
        p.terminate()


def startWorkers(numWorkers, *args, **kwargs):
    args = tuple([True] + list(args))
    processes = []
    if numWorkers == 1 and 'serverProcess' not in kwargs:
        # This is just a single-worker run - run in this thread to allow
        # debugging
        startApp(*args, **kwargs)
    else:
        if 'serverProcess' in kwargs:
            processes.append(kwargs.pop('serverProcess'))

        for i in range(numWorkers):
            p = multiprocessing.Process(
                    target=startApp, args=args, kwargs=kwargs)
            p.start()
            processes.append(p)

        # Install SIGTERM handler that terminates all child processes
        signal.signal(signal.SIGINT, partial(onSigForChildren, processes))
        signal.signal(signal.SIGTERM, partial(onSigForChildren, processes))

        # Wait for children to exit
        for p in processes:
            p.join()


def startComprehensive(numWorkers, *args, **kwargs):
    # Start web server
    p = multiprocessing.Process(target=startApp, args=args, kwargs=kwargs)
    p.start()

    # Start workers
    kwargs['serverProcess'] = p
    startWorkers(numWorkers, *args, **kwargs)



@argh.arg('-c', '--comprehensive', help='start webserver and workers')
@argh.arg('-s', '--server', help='start web server only')
@argh.arg('-w', '--workers', help='start workers only')
@argh.arg('-n', '--numWorkers', help='number of workers')
@argh.arg('-t', '--test', help='start web server in test mode')
@argh.arg('-f', '--fixture', help='fixture file for test mode')
@argh.arg('-d', '--daemon', help='daemon mode')
@argh.arg('-l', '--logLevel', 
        help='one of "debug", "info", "warning", "error", and "critical"')
@argh.arg('--logFormat', 
        help='Python-like log format (see Python docs for details)')
def start(comprehensive=True, server=False, workers=False, 
        numWorkers=multiprocessing.cpu_count(),
        test=False, fixture=None, daemon=False, 
        logLevel='warning', 
        logFormat='%(levelname)s:%(name)s (at %(asctime)s): %(message)s',
        *args, **kwargs):
    '''
    Start the application. By default, comprehensive mode is turned on.
    '''
    if daemon:
        yield 'Daemon mode is not available yet, starting in foreground...'

    Coronado.configureLogging(level=logLevel, format=logFormat)

    if test:
        startInTestMode(fixture, comprehensive, server, workers, numWorkers, 
                *args, **kwargs)
    elif workers:
        logger.info('Starting workers...')
        startWorkers(numWorkers, *args, **kwargs)
    elif server:
        logger.info('Starting web server...')
        startApp(*args, **kwargs)
    elif comprehensive:
        logger.info('Starting web server and workers...')
        startComprehensive(numWorkers, *args, **kwargs)
    

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
    main()
