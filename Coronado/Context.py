class Context(dict):

    def __init__(self, *args, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self['flatten'] = {'public': [], 'non-public': []}


    def addFlattenedAttr(self, attrType, attribute):
        self['flatten'][attrType].append(attribute)


    def flattenOnto(self, obj):
        # Store public and non-public context attributes as self's attributes
        # for ease of access in request handlers
        try:
            for key in self['flatten']['public']:
                setattr(obj, key, self[key])
        except KeyError:
            pass
        try:
            for key in self['flatten']['non-public']:
                setattr(obj, '_' + key, self[key])
        except KeyError:
            pass
