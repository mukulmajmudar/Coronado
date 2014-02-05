class RPCError(Exception):
    code = None
    message = None

    def __init__(self, code, msg):
        super(RPCError, self).__init__(msg)
        self.code = code
        self.message = msg
