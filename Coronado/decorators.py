from functools import wraps
from RPCError import RPCError
import json

def rpc(wrappedMethod):
    @wraps(wrappedMethod)
    def wrapper(self, *args, **kwargs):
        try:
            self.set_header('Content-Type', 'application/json')
            wrappedMethod(self, *args, **kwargs)

        except RPCError as e:
            # Set status as 200 and return error code and message in body
            self.set_status(200)
            self.write(json.dumps(
            {
                'error' : \
                {
                    'code' : e.code,
                    'message' : e.message
                }
            }))

            # Send back the response to the client
            self.finish()

    return wrapper
