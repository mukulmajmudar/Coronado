import string

import tornado.concurrent

from .Concurrent import when, transform

class ValidationError(Exception):
    invalidResults = None

    def __init__(self, invalidResults):
        super(ValidationError, self).__init__()
        self.invalidResults = invalidResults


class Validator(object):
    _validatee = None
    _validationOrder = None

    def __init__(self, validatee, order, *args, **kwargs):
        self._validatee = validatee
        self._validationOrder = order

        super(Validator, self).__init__(*args, **kwargs)


    def validate(self):
        # Call all validation methods
        futures = [self._validateAttr(key) for key in self._validationOrder]

        def getValidationErrors(validationFuture):
            # Get list of futures from validations
            subFutures = validationFuture.result()

            # Filter to a map of invalid results
            invalidResults = dict()
            index = 0
            try:
                for subFuture in subFutures:
                    result = subFuture.result()
                    if result is not True:
                        invalidResults[self._validationOrder[index]] = result
                    index += 1
            except Exception as e:
                f = tornado.concurrent.Future()
                f.set_exception(e)
                return f
            else:
                if invalidResults:
                    f = tornado.concurrent.Future()
                    f.set_exception(ValidationError(invalidResults))
                    return f
                return None

        # When all validation methods are done, transform the list result
        # into a dictionary of invalid results
        return transform(when(*futures), getValidationErrors)


    def _validateAttr(self, key):
        # Build validator name
        validatorName = 'validate' + string.upper(key[0])
        if len(key) > 1:
            validatorName += key[1:]

        # Get validator
        validator = getattr(self, validatorName)

        # Get the value to validate
        value = getattr(self._validatee, key)

        try:
            # Make sure validator is callable
            if not callable(validator):
                raise ValidationError('NoValidator', key)

            # Call validator
            return validator(value)
        except Exception as e:
            if isinstance(e, ValidationError):
                e.key = key
            f = tornado.concurrent.Future()
            f.set_exception(e)
            return f
