import logging
from typing import Optional

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class Configuration(BaseModel):
    debug: bool = False
    incremental: bool = False
    xray_client_id: str = Field(alias="#xray_client_id")
    xray_client_secret: str = Field(alias="#xray_client_secret")
    jql_input_column: str = Field()
    result_output_column: str = Field()
    project_id: str = Field()
    folder_path: str = Field()

    # Optional fields for proxy configuration, will get defaults from configSchema.json
    proxy_address: Optional[str] = Field(
        default=None, description="Optional proxy server address"
    )
    proxy_port: Optional[int] = Field(
        default=None, description="Optional proxy server port"
    )

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Validation Error: {', '.join(error_messages)}")

        if self.debug:
            logging.debug("Component will run in Debug mode")

        # --- Mandatory Proxy Check ---
        if not self.proxy_address or not self.proxy_port:
            raise UserException(
                "Proxy server configuration is mandatory. "
                "Please provide both 'proxy_address' and 'proxy_port' in the component configuration."
            )
        # --- End Mandatory Proxy Check ---

        if self.proxy_address:
            logging.info(f"Proxy Address: {self.proxy_address}")
            logging.info(f"Proxy Port: {self.proxy_port}")
        else:
            # This log should ideally not be reached if the mandatory check works
            logging.info(
                "No proxy configured in parameters (this should not happen if mandatory check is enabled)."
            )
