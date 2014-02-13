import string

def parseContentType(contentType):
    '''
    Parses an HTTP Content-Type header and returns a pair 
    (lowercase(type/subtype), uppercase(charset))
    '''
    if contentType is None:
        return None, None

    parts = contentType.split(';')
    type = string.lower(parts[0].strip())
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
    return type, string.upper(charset.strip())
