# Coronado
Coronado offers a simple convention for the life cycle of a server and/or
command-line application. With Coronado, you can define your app's startup and
shutdown behavior and add plugins with life cycles of their own. A Coronado app
can be both a server and a command-line app, and plugins can add both server
features and argh-style commands of their own.

When a Coronado application starts, all plugins are started first, and when
it shuts down, all plugins are shut down last.

To create a Coronado app, create a file called `Config.py` and define a dict
called "config" inside.

Coronado Hello World app directory structure:
```
* HelloWorldApp/
    * Config.py
    * HelloWorld/
        * __init__.py
        * ...
```

HelloWorldApp/Config.py:
```
import HelloWorld

config = \
{
    'appName': 'Coronado Hello World',
    'appPackage': HelloWorld,
    'startEventLoop': True
}
```

HelloWorld/__init_\_.py:
```
def f():
    print('Hello world!')

def start(context):
    context['loop'].call_soon(f)
```
