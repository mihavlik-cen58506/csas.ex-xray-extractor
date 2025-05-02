import logging

from keboola.component.exceptions import UserException
from pydantic import BaseModel, ValidationError


class Configuration(BaseModel):
    print_hello: bool
    debug: bool = False

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Validation Error: {', '.join(error_messages)}")

        if self.debug:
            logging.debug("Component will run in Debug mode")
            logging.debug("Component will run in Debug mode")
