import logging
import time

import requests

XRAY_GRAPHQL_ENDPOINT = "https://xray.cloud.getxray.app/api/v2/graphql"
XRAY_AUTH_ENDPOINT = "https://xray.cloud.getxray.app/api/v2/authenticate"

# HTTP statuses treated as transient and retried.
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

# Up to 4 attempts total with linear backoff (15s, 30s, 45s) when the server
# does not send a Retry-After header. If it does, we honor that instead.
RETRY_ATTEMPTS = 4
RETRY_BASE_SLEEP_SECONDS = 15

# Small client-side throttle to stay below Xray Cloud's ~60 req/min limit,
# which avoids most 429s before the retry path is even needed.
REQUEST_THROTTLE_SECONDS = 0.5


class XrayApiClient:
    """
    Client for interacting with the Xray Cloud API.
    Handles authentication and GraphQL queries. Both use the same retry
    helper that handles transient failures (429, 5xx, connection errors).
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

    @staticmethod
    def _compute_retry_wait(response: requests.Response, attempt: int) -> int:
        """Prefer server's Retry-After header; fall back to linear backoff."""
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                pass
        return RETRY_BASE_SLEEP_SECONDS * (attempt + 1)

    def _post_with_retry(self, url: str, **kwargs) -> requests.Response:
        """
        POST with retry on transient errors (connection errors, 429, 5xx).
        Returns the final response — callers must still call raise_for_status()
        to handle non-retryable 4xx or an exhausted-retry 429/5xx.
        Raises RequestException only when no response was ever received
        (network error on every attempt).
        """
        last_exc = None
        response = None

        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = requests.post(url, timeout=60, **kwargs)
                if response.status_code not in RETRY_STATUS_CODES:
                    return response
                sleep_for = self._compute_retry_wait(response, attempt)
                last_exc = requests.HTTPError(
                    f"{response.status_code} {response.reason} for url: {url}",
                    response=response,
                )
            except requests.exceptions.RequestException as e:
                response = None
                last_exc = e
                sleep_for = RETRY_BASE_SLEEP_SECONDS * (attempt + 1)

            if attempt + 1 < RETRY_ATTEMPTS:
                logging.warning(
                    f"Request to {url} failed: {last_exc}. "
                    f"Retrying in {sleep_for}s ({attempt + 1}/{RETRY_ATTEMPTS})."
                )
                time.sleep(sleep_for)

        logging.error(
            f"Request to {url} failed after {RETRY_ATTEMPTS} attempts: {last_exc}"
        )
        if response is not None:
            return response
        raise last_exc

    def _authenticate(self):
        """Authenticate with the Xray Cloud API and store the Bearer token."""
        logging.info("Authenticating with Xray Cloud API...")

        auth_payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        response = self._post_with_retry(
            XRAY_AUTH_ENDPOINT,
            json=auth_payload,
            headers={"content-type": "application/json"},
        )
        response.raise_for_status()

        self._bearer_token = response.text.strip('"')
        logging.info("Xray Cloud API authentication successful.")

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
            requests.exceptions.RequestException: If the API request fails
                after all retries are exhausted.
            ValueError: If the API response is not valid JSON.
            Exception: If the API response indicates a GraphQL error.
        """

        if not self._bearer_token:
            self._authenticate()

        logging.debug(
            f"Executing GraphQL query - Project: '{project_id}', Folder: '{folder_path}', JQL: '{jql_query}'"
        )

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

        query_variables = {"projectId": project_id}

        if folder_path and folder_path.strip():
            query_variables["folder"] = {
                "path": folder_path,
                "includeDescendants": True,
            }

        if jql_query and jql_query.strip():
            query_variables["jql"] = jql_query

        request_payload = {"query": graphql_query, "variables": query_variables}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
        }

        time.sleep(REQUEST_THROTTLE_SECONDS)

        try:
            response = self._post_with_retry(
                XRAY_GRAPHQL_ENDPOINT,
                json=request_payload,
                headers=headers,
            )
            response.raise_for_status()

            api_response = response.json()

            if api_response.get("errors"):
                logging.error(
                    f"GraphQL query returned errors: {api_response['errors']}"
                )
                raise Exception(f"GraphQL query errors: {api_response['errors']}")

            data = api_response.get("data", {})
            tests_data = data.get("getTests", {})
            total = tests_data.get("total", 0)

            try:
                return int(total) if total is not None else 0
            except (ValueError, TypeError):
                logging.warning(
                    f"Invalid total value from GraphQL API: {total}, returning 0"
                )
                return 0

        except requests.exceptions.RequestException as e:
            logging.error(f"Xray GraphQL API request failed: {e}")
            raise
        except ValueError:
            logging.error(
                f"Failed to parse JSON response from Xray API. Response text: {response.text[:500]}..."
            )
            raise
