class DeviceProxy(object):
    '''
    Interface for a device proxy, useful for implementing the device proxy
    pattern for push notifications.

    Device Proxy Pattern
    --------------------
    The device proxy pattern is a server-side pattern for implementing push
    notifications. A device proxy listens for events on an event manager
    and acts as a multiplexing proxy for devices, pushing out notifications to
    devices. Since each type of device (Android/iOS/web) has different push
    notification methods, there should be a device proxy for each platform.
    '''

    def setup(self, context):
        pass

    def start(self, context):
        pass

    def destroy(self, context):
        pass
