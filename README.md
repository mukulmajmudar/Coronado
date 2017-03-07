# Coronado
Coronado offers a simple convention for the life cycle of a server and/or
command-line application. With Coronado, you can define your app's startup and
shutdown behavior and add plugins with life cycles of their own. A Coronado app
can be both a server and a command-line app, and plugins can add both server
features and argh-style commands of their own.

When a Coronado application starts, all plugins are started first, and when
it shuts down, all plugins are shut down last.

Minimum Config.py:

```
config = \
{
    'appName': <name>,
    'appPackage': <package>,
    'startEventLoop': True
}
```
