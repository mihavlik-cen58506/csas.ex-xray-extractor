import logging
import time

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
    """

    def __init__(self, client_id: str, client_secret: str):
        """
        Initializes the Xray API client and authenticates to get a Bearer token.

        Args:
            client_id: The Xray Cloud Client ID.
            client_secret: The Xray Cloud Client Secret.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._bearer_token = None
        self._authenticate()

    def _authenticate(self):
        """
        Authenticates with the Xray Cloud API to obtain a Bearer token.
        Retries on specific temporary errors.
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

    def query_tests_by_dynamic_params(
        self, project_id: str, folder_path: str = None, jql_query: str = None
    ) -> int:
        """
        Executes a GraphQL query to get tests based on dynamic parameters.

        Args:
            project_id: The Xray/Jira Project ID (required).
            folder_path: The path to the folder in Xray (optional).
            jql_query: The JQL query string (optional).

        Returns:
            The total count of tests matching the criteria.
        Raises:
            requests.exceptions.RequestException: If the API request fails.
            ValueError: If the API response is not valid JSON.
            Exception: If the API response indicates a GraphQL error.
        """

        if not self._bearer_token:
            self._authenticate()

        logging.debug(
            f"Executing GraphQL query - Project: '{project_id}', Folder: '{folder_path}', JQL: '{jql_query}'"
        )

        # Define the GraphQL query string.
        graphql_query = """
            query GetTestsDynamic(
                $projectId: String!,
                $folder: FolderSearchInput,
                $jql: String
            ) {
                getTests(
                    projectId: $projectId,
                    folder: $folder,
                    jql: $jql,
                    limit: 100
                ) {
                    total
                }
            }
        """

        # Build variables dynamically
        query_variables = {"projectId": project_id}

        if folder_path and folder_path.strip():
            query_variables["folder"] = {
                "path": folder_path,
                "includeDescendants": True,
            }

        if jql_query and jql_query.strip():
            query_variables["jql"] = jql_query

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
            )

            # Check for HTTP errors (like 401, 403, 404, 500 etc.)
            response.raise_for_status()

            api_response = response.json()

            if api_response.get("errors"):
                logging.error(
                    f"GraphQL query returned errors: {api_response['errors']}"
                )
                raise Exception(f"GraphQL query errors: {api_response['errors']}")

            # Extract and return only the total count
            data = api_response.get("data", {})
            tests_data = data.get("getTests", {})
            total = tests_data.get("total", 0)
            
            # Ensure it's an integer
            try:
                return int(total) if total is not None else 0
            except (ValueError, TypeError):
                logging.warning(f"Invalid total value from GraphQL API: {total}, returning 0")
                return 0

        except requests.exceptions.RequestException as e:
            logging.error(f"Xray GraphQL API request failed: {e}")
            raise
        except ValueError:
            logging.error(
                f"Failed to parse JSON response from Xray API. Response text: {response.text[:500]}..."
            )
            raise
