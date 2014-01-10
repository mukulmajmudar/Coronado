class RPCError(Exception):
    code = None
    message = None

    def __init__(self, code, msg):
        self.code = code
        self.message = msg
