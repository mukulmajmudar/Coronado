import json

from tornado.ioloop import IOLoop

from .Concurrent import transform

class ModelProxy(dict):
    uri = None
    httpClient = None
    ioloop = None
    singular = 'model'
    plural = 'models'

    def __init__(self, *args, **kwargs):
        # Save URI and HTTP client if given
        self.uri = kwargs.pop('uri', None)
        self.httpClient = kwargs.pop('httpClient', None)
        self.ioloop = kwargs.pop('ioloop', IOLoop.current())

        # Call parent
        super(ModelProxy, self).__init__(*args, **kwargs)


    def fetch(self, uri=None, method='GET', headers=None, body=None):
        if headers is None:
            headers = {}

        if uri is None:
            uri = self.uri

        # Fetch and return
        fetchFuture = self.httpClient.fetch(
                request=uri, method=method, headers=headers, body=body)

        def onFetch(fetchFuture):
            response = fetchFuture.result()
            modelAttrs = json.loads(response.body)

            # Merge in attributes
            self.update(modelAttrs)

            # TODO: Trigger event
            #self.trigger('fetched', modelProxy=self)

            return self

        return transform(fetchFuture, onFetch, ioloop=self.ioloop)
