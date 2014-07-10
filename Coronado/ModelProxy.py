import json

class ModelProxy(dict):
    uri = None
    httpClient = None
    singular = 'model'
    plural = 'models'

    def __init__(self, *args, **kwargs):
        # Save URI and HTTP client if given
        self.uri = kwargs.pop('uri', None)
        self.httpClient = kwargs.pop('httpClient', None)

        # Call parent
        super(ModelProxy, self).__init__(*args, **kwargs)


    def fetch(self):
        # Fetch and return
        fetchFuture = self.httpClient.fetch(
                request=self.uri,
                method='GET')

        def onFetch(fetchFuture):
            response = fetchFuture.result()
            modelAttrs = json.loads(response.body)

            # Merge in attributes
            self.update(modelAttrs)

            # TODO: Trigger event
            #self.trigger('fetched', modelProxy=self)

            return self;
