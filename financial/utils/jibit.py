import dataclasses


@dataclasses.dataclass
class ErrorMessage:
    code: str
    message: str


def get_jibit_error_message(data: dict) -> ErrorMessage:
    if data.get('errors'):
        error = data['errors'][0]
        code = error['code']
        message = error.get('message', '')
        return ErrorMessage(
            code=code,
            message=message
        )

    elif 'error' in data:
        return ErrorMessage(
            code='unknown',
            message=data['error']
        )
    else:
        return ErrorMessage(
            code='unknown',
            message='unknown'
        )
