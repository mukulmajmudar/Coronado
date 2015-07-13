class Config(dict):

    def __init__(self, keys):
        for key in keys:
            self[key] = getattr(self, '_get' + key[0].upper() + key[1:])()

        super(Config, self).__init__()
        self.validate()

    def validate(self):
        pass
