import logging

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class Configuration(BaseModel):
    debug: bool = False
    incremental: bool = False
    xray_client_id: str = Field(alias="#xray_client_id")
    xray_client_secret: str = Field(alias="#xray_client_secret")
    jql_input_column: str
    result_output_column: str

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Validation Error: {', '.join(error_messages)}")

        if self.debug:
            logging.debug("Component will run in Debug mode")
            logging.debug("Component will run in Debug mode")
