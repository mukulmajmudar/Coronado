#! ./bin/python
import sys
import argparse
import argh
import pdb
import traceback
import multiprocessing
from functools import partial
import signal
import os

sys.path.append(os.getcwd())

from config import config

# Get list of extension modules
keysBeforeImport = set(sys.modules.keys())

# Import all extensions
if os.path.exists('Extensions'):
    from Extensions import *

moduleNames = set(sys.modules.keys()) - keysBeforeImport

def loadExtensions():
    global moduleNames
    extensions = []
    for modName in moduleNames:
        mod = sys.modules[modName]
        config = getattr(mod, '_config', False)
        if not config:
            continue

        extensions.append(config)

    return extensions


def startInTestMode(fixture, *args, **kwargs):
    scaffold = None
    try:
        testsMod = __import__(config['testPkg'].__name__ + '.config')
        config = testsMod.config.config

        # Setup a testing scaffold
        scaffold = Coronado.Testing.Scaffold(config, config['appClass'],
                *args, **kwargs)
        scaffold.setup()
        app = scaffold.app

        # Load test fixture if any
        if fixture is not None:
            fixture = json.load(fixture)
            Coronado.Testing.installFixture(
                    app.context['database'], fixture)

        # Start listening for requests
        scaffold.app.startListening()

        # Start async event loop
        scaffold.app.startEventLoop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise argh.CommandError(traceback.format_exc())
    finally:
        if scaffold is not None:
            scaffold.destroy()

def onSigTerm(app, signum, frame):
    app.destroy()


def startApp(workerMode=False, *args, **kwargs):
    global config
    app = None
    try:
        app = config['appClass'](config, workerMode, *args, **kwargs)
        app.setup()

        # Install SIGTERM handler
        signal.signal(signal.SIGTERM, partial(onSigTerm, app))

        # Start listening for requests
        app.startListening()

        if workerMode:
            sys.stderr.write('Started worker\n')
        else:
            sys.stderr.write('Started web server\n')
        sys.stderr.flush()

        # Start async event loop
        app.startEventLoop()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise argh.CommandError(traceback.format_exc())
    finally:
        if app is not None:
            app.destroy()


def startWorkers(numWorkers, *args, **kwargs):
    args = tuple([True] + list(args))
    workers = []
    for i in xrange(numWorkers):
        p = multiprocessing.Process(target=startApp, args=args, kwargs=kwargs)
        p.start()
        workers.append(p)

    # Wait for workers to exit
    try:
        for p in workers:
            p.join()

    except KeyboardInterrupt:
        # Terminate all workers
        for p in workers:
            p.terminate()
            p.join()


def startComprehensive(numWorkers, *args, **kwargs):
    # Start web server
    p = multiprocessing.Process(target=startApp, args=args, kwargs=kwargs)
    p.start()

    # Start workers
    startWorkers(numWorkers, *args, **kwargs)

    p.join()
     


@argh.arg('-c', '--comprehensive', help='start webserver and workers')
@argh.arg('-s', '--server', help='start web server')
@argh.arg('-w', '--workers', help='start workers')
@argh.arg('-n', '--numWorkers', help='number of workers')
@argh.arg('-t', '--test', help='start web server in test mode')
@argh.arg('-f', '--fixture', help='fixture file for test mode')
@argh.arg('-d', '--daemon', help='daemon mode')
def start(comprehensive=True, server=False, workers=False, 
        numWorkers=multiprocessing.cpu_count(),
        test=False, fixture=None, daemon=False, *args, **kwargs):
    '''
    Start the application. By default, comprehensive mode is turned on.
    '''
    if daemon:
        yield 'Daemon mode is not available yet, starting in foreground...'

    if test:
        startInTestMode(fixture, *args, **kwargs)
    elif workers:
        sys.stderr.write('Starting workers...\n')
        sys.stderr.flush()
        startWorkers(numWorkers, *args, **kwargs)
    elif server:
        sys.stderr.write('Starting web server...\n')
        sys.stderr.flush()
        startApp(*args, **kwargs)
    elif comprehensive:
        sys.stderr.write('Starting web server and workers...\n')
        sys.stderr.flush()
        startComprehensive(numWorkers, *args, **kwargs)
    

def main():
    parser = argparse.ArgumentParser(description='Coronado Application')
    extensions = loadExtensions()

    # Add start command
    argh.add_commands(parser, [start])

    # Add extension commands
    for extension in extensions:
        kwargs = {}
        if extension.get('namespace'):
            kwargs = dict(title=extension['title'],
                    namespace=extension['name'])
        argh.add_commands(parser, extension['commands'], **kwargs)

    # Dispatch command
    argh.dispatch(parser)


if __name__ == '__main__':
    main()
