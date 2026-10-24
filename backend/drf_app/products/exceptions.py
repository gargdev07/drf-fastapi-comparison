from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, ValidationError):
        def flatten(errors, prefix=()):
            result = []
            if isinstance(errors, dict):
                for key, value in errors.items():
                    result.extend(flatten(value, prefix + (key,)))
            elif isinstance(errors, (list, tuple)):
                for value in errors:
                    if isinstance(value, (dict, list, tuple)):
                        result.extend(flatten(value, prefix))
                    else:
                        result.append({"loc": list(prefix), "msg": str(value), "type": "value_error"})
            else:
                result.append({"loc": list(prefix), "msg": str(errors), "type": "value_error"})
            return result
        response.data = {"detail": flatten(exc.detail)}
        response.status_code = 422
    return response
