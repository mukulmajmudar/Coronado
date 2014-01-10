from RPCError import RPCError

noError = RPCError(1, 'No error')
accountNotFound = RPCError(2, 'Account not found')
wrongPassword = RPCError(3, 'Wrong password')
accountPending = RPCError(4, 'Account pending')
true = RPCError(5, 'True')
false = RPCError(6, 'False')
