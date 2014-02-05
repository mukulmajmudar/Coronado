from twisted.internet import defer
import string

class ValidationError(Exception):
    key = None
    error = None

    def __init__(self, error, key=None):
        super(ValidationError, self).__init__(error)
        self.error = error
        self.key = key


class Validator(object):
    _validatee = None
    _validationOrder = None

    def __init__(self, validatee, order, *args, **kwargs):
        self._validatee = validatee
        self._validationOrder = order

        super(Validator, self).__init__(*args, **kwargs)


    def validate(self):

        # If there is an error while validating any property,
        # pass on that error to the next registered errback
        def onAnyError(failure):
            failure.trap(defer.FirstError)
            raise failure.value.subFailure.value
        return defer.gatherResults(
                map(self._validateAttr, self._validationOrder), 
                consumeErrors=True).addErrback(onAnyError)


    def _validateAttr(self, key):
        # Build validator name
        validatorName = 'validate' + string.upper(key[0])
        if len(key) > 1:
            validatorName += key[1:]

        # Get validator
        validator = getattr(self, validatorName)

        # Get the value to validate
        value = getattr(self._validatee, key)

        if not callable(validator):
            raise ValidationError('NoValidator', key)

        def onValidationFailed(failure):
            failure.trap(ValidationError)
            failure.value.key = key
            raise failure.value

        # Call validator
        return defer.maybeDeferred(validator, value).addErrback(
                onValidationFailed)
