import json

from Coronado.Concurrent import transform
from tornado.ioloop import IOLoop

class CollectionProxy(object):
    uri = None
    httpClient = None
    modelProxyClass = None
    ioloop = None

    def __init__(self, **kwargs):
        self.uri = kwargs.get('uri')
        self.httpClient = kwargs.get('httpClient')
        self.modelProxyClass = kwargs.get('modelProxyClass')
        self.ioloop = kwargs.get('ioloop', IOLoop.current())
        self._cache = {}


    def add(self, modelProxy, uri=None, method='POST', headers=None):
        '''
        Add a model to the collection.
        '''
        if uri is None:
            uri = self.uri
        if headers is None:
            headers = {'Content-Type': 'application/json; charset=UTF-8'}

        responseFuture = self.httpClient.fetch(
                request=uri,
                method=method,
                headers=headers,
                body=json.dumps(modelProxy))

        def onAdded(responseFuture):
            response = responseFuture.result()

            modelAttrs = json.loads(response.body)

            # Update with return value
            modelProxy.update(modelAttrs)

            # Add URI and http client
            modelProxy.uri = self.uri + '/' + modelProxy['id'];
            modelProxy.httpClient = self.httpClient;

            # Cache
            '''
            self._cache[self.uri + '/' + modelProxy['id']] \
                = json.dumps(modelProxy)
            '''

            # TODO: Trigger "added" event
            '''
            args = {}
            args[self.modelProxyClass.singular] = modelProxy;
            self.trigger('added', **args);
            '''

            return modelProxy

        return transform(responseFuture, onAdded, ioloop=self.ioloop)


    def get(self, id, fetch=False, method='GET', headers=None, body=None):
        if headers is None:
            headers = {}

        id = str(id)
        #entry = self._cache.get(self.uri + '/' + id);
        entry = None
        if entry:
            modelProxy = self._makeModelProxy(json.loads(entry))
            modelProxy.uri = self.uri + '/' + id;
            return modelProxy

        modelProxy = self._makeModelProxy(dict(id=id))

        uri = self.uri;
        #cache = self._cache;

        # TODO: listen for "fetched" event on the model and update cached
        # value
        '''
        def onFetched():
            // Update cache value
            cache[uri + '/' + modelProxy.id]
                = JSON.stringify(modelProxy);

        modelProxy.on('fetched', onFetched)
        '''

        return fetch and modelProxy.fetch(method, headers, body) or modelProxy


    def getMany(self, ids, responseKey=None, method='POST', headers=None):
        if headers is None:
            headers = {}

        # If ids is empty, return empty
        if len(ids) == 0:
            return []

        # Default response key is the model's plural
        if responseKey is None:
            responseKey = self.modelProxyClass.plural

        # Make request for many models
        responseFuture = self.httpClient.fetch(
                request=self.uri + '.getMany',
                method='POST',
                headers={'Content-Type': 'application/json; charset=UTF-8'},
                body=json.dumps(ids))

        def onResponse(responseFuture):
            response = responseFuture.result()
            jsonResponse = json.loads(response.body)
            return [self._makeModelProxy(attrs) 
                    for attrs in jsonResponse[responseKey]]

        return transform(responseFuture, onResponse, ioloop=self.ioloop)


    def _makeModelProxy(self, attrs):
        if attrs is None:
            return None

        attrs.update(uri=self.uri + '/' + attrs['id'],
                httpClient=self.httpClient)

        return self.modelProxyClass(**attrs)


    _cache = None
