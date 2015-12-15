
def parseContentType(contentType):
    '''
    Parses an HTTP Content-Type header and returns a pair
    (lowercase(type/subtype), uppercase(charset))
    '''
    if contentType is None:
        return None, None

    parts = contentType.split(';')
    ctype = parts[0].strip().lower()
    charset = None
    if len(parts) == 1:
        charset = 'ISO-8859-1'
    else:
        attributes = parts[1]
        pos = attributes.find('charset=')
        if pos == -1:
            charset = 'ISO-8859-1'
        else:
            charset = attributes[pos + len('charset='):]
    return ctype, charset.strip().upper()
