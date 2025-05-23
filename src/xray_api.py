import logging
import time
from typing import Optional  # Import Optional for type hinting

import requests

# Define the GraphQL endpoint for Xray Cloud
XRAY_GRAPHQL_ENDPOINT = "https://xray.cloud.getxray.app/api/v2/graphql"
# Define the authentication endpoint for Xray Cloud
XRAY_AUTH_ENDPOINT = "https://xray.cloud.getxray.app/api/v2/authenticate"

# Define HTTP status codes that might indicate a temporary issue (for retries)
RETRY_STATUS_CODES = [429, 503]


class XrayApiClient:
    """
    Client for interacting with the Xray Cloud API.
    Handles authentication and GraphQL queries.
    Now includes support for using a proxy server.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        proxy_address: Optional[str] = None,
        proxy_port: Optional[int] = None,
    ):
        """
        Initializes the Xray API client and authenticates to get a Bearer token.

        Args:
            client_id: The Xray Cloud Client ID.
            client_secret: The Xray Cloud Client Secret.
            proxy_address: Optional proxy server address.
            proxy_port: Optional proxy server port.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._bearer_token = None

        # Store proxy configuration
        self._proxy_address = proxy_address
        self._proxy_port = proxy_port
        self._proxies = self._build_proxy_dict()

        self._authenticate()

    def _build_proxy_dict(self) -> Optional[dict]:
        """
        Builds the dictionary format required by the 'requests' library for proxies.
        Returns None if no proxy configuration is provided.
        """
        if self._proxy_address and self._proxy_port:
            proxy_url = f"http://{self._proxy_address}:{self._proxy_port}"
            logging.info(f"Using proxy: {proxy_url}")
            # Configure proxies for both http and https
            return {
                "http": proxy_url,
                "https": proxy_url,
            }
        else:
            logging.info("No proxy configured.")
            return None

    def _authenticate(self):
        """
        Authenticates with the Xray Cloud API to obtain a Bearer token.
        Retries on specific temporary errors.
        Uses the configured proxy if available.
        """
        logging.info("Authenticating with Xray Cloud API...")

        # Prepare the authentication payload
        auth_payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        retries = 4
        for i in range(retries):
            sleep_time = 15 + i * 15

            try:
                response = requests.post(
                    XRAY_AUTH_ENDPOINT,
                    json=auth_payload,
                    headers={"content-type": "application/json"},
                    timeout=60,
                    proxies=self._proxies,
                )

                # Check for retryable status codes
                if response.status_code in RETRY_STATUS_CODES and i + 1 < retries:
                    logging.warning(
                        f"Authentication failed with status {response.status_code}. "
                        f"Retrying in {sleep_time} seconds ({i + 1}/{retries})."
                    )
                    time.sleep(sleep_time)
                    continue  # Go to the next retry attempt
                elif response.status_code != 200:
                    response.raise_for_status()

                # If status is 200, authentication was successful - Store the token, removing quotes
                self._bearer_token = response.text.strip('"')
                logging.info("Xray Cloud API authentication successful.")
                return

            except requests.exceptions.RequestException as e:
                if i + 1 < retries:
                    logging.warning(
                        f"Authentication request failed: {e}. "
                        f"Retrying in {sleep_time} seconds ({i + 1}/{retries})."
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    logging.error(
                        f"Authentication request failed after multiple retries: {e}"
                    )
                    raise  # Re-raise the exception if all retries fail

        # If the loop finishes without returning (shouldn't happen with proper error handling)
        if self._bearer_token is None:
            raise Exception(
                "Failed to obtain Xray Bearer token after multiple attempts."
            )

    def query_tests_by_folder_and_jql(
        self, project_id: str, folder_path: str, jql_query: str
    ) -> dict:
        """
        Executes a GraphQL query to get tests based on Project ID, Folder Path,
        and optionally JQL string.
        Uses the configured proxy if available.

        Args:
            project_id: The Xray/Jira Project ID.
            folder_path: The path to the folder in Xray.
            jql_query: The JQL query string (can be empty).

        Returns:
            A dictionary containing the parsed JSON response from the API.
        Raises:
            requests.exceptions.RequestException: If the API request fails.
            ValueError: If the API response is not valid JSON.
            Exception: If the API response indicates a GraphQL error.
        """

        if not self._bearer_token:
            # Re-authenticate if token is missing (shouldn't happen after __init__ but as a safeguard)
            self._authenticate()

        logging.debug(f"Executing GraphQL query for JQL: '{jql_query}'")

        # Define the GraphQL query string.
        graphql_query = """
            query GetTestsInFolderAndJQL(
                $projectId: String!,
                $folderPath: String!,
                $jql: String # JQL is optional
                # $includeDescendants: Boolean # Uncomment if you want to control this via a variable
            ) {
                getTests(
                    projectId: $projectId,
                    folder: {
                        path: $folderPath
                        # includeDescendants: true # Or use $includeDescendants variable here
                    },
                    jql: $jql, # Use the JQL variable
                    limit: 100, # Fixed limit, can be made a variable
                    start: 0    # Fixed start, can be made a variable
                ) {
                    total
                    start
                    limit
                    results {
                        issueId
                        testType {
                            name
                            kind
                        }
                        # Original fields + fields from Postman example if needed
                        # jira(fields: ["summary", "key", "status"])
                        # steps { id, action, result }
                    }
                }
            }
        """

        # Define the variables for the GraphQL query
        query_variables = {
            "projectId": project_id,
            "folderPath": folder_path,
            "jql": (
                jql_query if jql_query else None
            ),  # Pass JQL only if not empty, otherwise pass None
            # "includeDescendants": True # Value if $includeDescendants variable is used
        }

        # Prepare the request payload for GraphQL
        request_payload = {"query": graphql_query, "variables": query_variables}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
        }

        try:
            response = requests.post(
                XRAY_GRAPHQL_ENDPOINT,
                json=request_payload,
                headers=headers,
                timeout=60,
                proxies=self._proxies,  # Pass the proxies dictionary here
            )

            # Check for HTTP errors (like 401, 403, 404, 500 etc.)
            response.raise_for_status()

            api_response = response.json()

            if api_response.get("errors"):
                logging.error(
                    f"GraphQL query returned errors: {api_response['errors']}"
                )
                raise Exception(f"GraphQL query errors: {api_response['errors']}")

            # Return the data part of the response
            return api_response.get(
                "data", {}
            )  # Return the 'data' object or empty dict

        except requests.exceptions.RequestException as e:
            logging.error(f"Xray GraphQL API request failed: {e}")
            raise
        except ValueError:
            logging.error(
                f"Failed to parse JSON response from Xray API. Response text: {response.text[:500]}..."
            )
            raise
