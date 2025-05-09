import csv
import json
import logging

# Import necessary classes from keboola-component-base
from keboola.component.base import ComponentBase
from keboola.component.dao import TableDefinition  # For type hinting
from keboola.component.exceptions import UserException

from configuration import Configuration
from xray_api import XrayApiClient


class Component(ComponentBase):
    """
    Keboola Component logic.
    Handles configuration loading, input reading, and main execution flow.
    """

    def __init__(self):
        # Initialize base component interface
        super().__init__()

    def run(self):
        """
        Main execution method.
        Loads config, reads input table, logs data info.
        """
        logging.info("Component starting.")

        # Load and validate configuration parameters
        try:
            logging.info("Loading and validating configuration parameters...")
            params = Configuration(**self.configuration.parameters)
            logging.info("Configuration parameters loaded and validated.")

            # Set debug logging level if enabled in config
            if params.debug:
                logging.getLogger().setLevel(logging.DEBUG)
                logging.debug("Debug mode enabled.")

            # Log all loaded parameters (sensitive ones at DEBUG level)
            logging.info("--- Loaded Parameters ---")
            logging.info(f"Debug: {params.debug}")
            logging.info(f"Incremental: {params.incremental}")
            logging.info(f"JQL Input Column: {params.jql_input_column}")
            logging.info(f"Result Output Column: {params.result_output_column}")
            logging.info(f"Project ID: {params.project_id}")
            logging.info(f"Folder Path: {params.folder_path}")
            # Log sensitive parameters only in debug mode and partially
            logging.debug(
                f"Xray Client ID (last 5 chars): ...{params.xray_client_id[-5:]}"
            )
            logging.debug(
                f"Xray Client Secret (last 5 chars): ...{params.xray_client_secret[-5:]}"
            )
            logging.info("-------------------------")

        except UserException as e:
            logging.error(f"Configuration error: {e}")
            raise  # Re-raise to fail job with exit code 1

        #
        # Create an instance of our XrayApiClient, passing credentials from config.
        try:
            logging.info("Initializing Xray API client and authenticating...")
            xray_client = XrayApiClient(
                client_id=params.xray_client_id, client_secret=params.xray_client_secret
            )
            logging.info("Xray API client initialized and authenticated.")
        except Exception as e:
            logging.error(f"Failed to initialize or authenticate Xray API client: {e}")
            raise UserException(f"API Authentication/Initialization Error: {e}")

        #
        # ####### Get Input Table Definitions #######
        logging.info("Getting input table definitions...")
        input_tables: list[TableDefinition] = self.get_input_tables_definitions()

        if not input_tables:
            raise UserException(
                "No input tables found. Please map at least one input table."
            )

        if len(input_tables) > 1:
            logging.warning(
                f"More than one input table mapped ({len(input_tables)}). Processing the first one."
            )

        # Get the definition of the first input table
        input_table_def = input_tables[0]
        logging.info(
            f"Processing input table: {input_table_def.name} (file: {input_table_def.full_path})"
        )

        # ####### Read data, call API, and prepare output #######
        input_csv_path = input_table_def.full_path
        processed_rows = []  # List to store rows after adding API results
        row_count = 0

        try:
            with open(input_csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                # Verify required JQL input column exists in CSV header
                if params.jql_input_column not in reader.fieldnames:
                    raise UserException(
                        f"Input table '{input_table_def.name}' is missing the required "
                        f"JQL column: '{params.jql_input_column}'. Available columns: "
                        f"{list(reader.fieldnames)}"
                    )

                logging.info(
                    f"Input CSV header read. Required JQL column '{params.jql_input_column}' found."
                )

                # Prepare fieldnames for the output CSV.
                # Start with original columns and add the new result column.
                output_fieldnames = list(reader.fieldnames)
                # Add the new output column name if it's not already present
                if params.result_output_column not in output_fieldnames:
                    output_fieldnames.append(params.result_output_column)
                else:
                    logging.warning(
                        f"Output column name '{params.result_output_column}' already "
                        "exists in input. It will be overwritten."
                    )

                # Iterate through rows, call API, and collect results
                logging.info("Processing rows and calling Xray API...")
                for row in reader:
                    row_count += 1
                    logging.debug(f"Processing row {row_count}.")

                    # Get the JQL query from the specified column
                    jql_query = row.get(
                        params.jql_input_column, ""
                    ).strip()  # Get value and remove leading/trailing whitespace

                    # Skip row if JQL column is empty
                    if not jql_query:
                        logging.warning(
                            f"Row {row_count}: JQL column '{params.jql_input_column}' "
                            "is empty. Querying using only Project ID and Folder Path."
                        )
                        # Add an empty value for the result column and keep the row
                        row[params.result_output_column] = ""
                        processed_rows.append(row)
                        continue  # Move to the next row

                    logging.debug(f"Row {row_count}: JQL query: '{jql_query}'")

                    # ####### Call Xray API for the JQL query #######
                    try:
                        # Call the query_tests_by_jql method of our XrayApiClient
                        api_result = xray_client.query_tests_by_folder_and_jql(
                            project_id=params.project_id,
                            folder_path=params.folder_path,
                            jql_query=jql_query,
                        )
                        logging.debug(
                            f"Row {row_count}: API call successful. Result data structure: "
                            f"{list(api_result.keys()) if api_result else 'Empty'}"
                        )

                        # ####### Process API Result and Add to Row #######
                        result_json_string = json.dumps(api_result)

                        # Add the result to the current row dictionary under the specified output column name
                        row[params.result_output_column] = result_json_string
                        logging.debug(
                            f"Row {row_count}: Added API result to column "
                            f"'{params.result_output_column}'."
                        )

                    except Exception as api_exc:
                        logging.error(
                            f"Row {row_count}: Error calling Xray API for Project ID "
                            f"'{params.project_id}', Folder Path '{params.folder_path}', "
                            f"JQL '{jql_query}': {api_exc}"
                        )
                        # API errors per row:
                        row[params.result_output_column] = (
                            f"API_ERROR: {api_exc}"  # Store error message
                        )
                        logging.warning(
                            f"Row {row_count}: API call failed. Storing error message in result column."
                        )

                    # Add the modified row to our list of processed rows
                    processed_rows.append(row)

                logging.info(
                    f"Finished processing {row_count} rows. Collected {len(processed_rows)} rows for output."
                )

        except FileNotFoundError:
            logging.error(f"Input CSV file not found: {input_csv_path}")
            raise UserException(
                "Input file not found. Check Input Mapping and source table."
            )
        except Exception as e:
            logging.error(f"Error reading or processing input CSV: {e}")
            raise  # Re-raise unexpected errors

        # ####### Write Output Table #######
        output_tables = self.get_output_tables_definitions()
        if not output_tables:
            raise UserException(
                "No output tables defined. Please map at least one output table."
            )
        if len(output_tables) > 1:
            logging.warning(
                f"More than one output table defined ({len(output_tables)}). Writing to the first one."
            )

        output_table_def = output_tables[0]
        logging.info(
            f"Writing output to table: {output_table_def.name} (file: {output_table_def.full_path})"
        )

        # 1. Set the output table definition
        output_table_def.columns = output_fieldnames

        # 2. Write the processed data to the output CSV file
        output_csv_path = output_table_def.full_path
        logging.info(
            f"Writing {len(processed_rows)} rows to output CSV file: {output_csv_path}"
        )

        try:
            with open(
                output_csv_path, mode="wt", encoding="utf-8", newline=""
            ) as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=output_fieldnames)

                # Write the header row
                writer.writeheader()

                # Write the data rows
                writer.writerows(processed_rows)

            logging.info("Output CSV file written successfully.")

            # 3. Write the manifest file for the output table
            logging.info(
                f"Writing manifest file for output table: {output_table_def.full_path}.manifest"
            )
            self.write_manifest(output_table_def)
            logging.info("Manifest file written successfully.")

        except Exception as e:
            logging.error(f"Error writing output CSV or manifest: {e}")
            raise  # Re-raise the exception

        logging.info("Component finished.")


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
        logging.info("Job completed successfully.")
    except UserException as exc:
        logging.error(f"User Error: {exc}")
        exit(1)
    except Exception as e:
        logging.exception(f"An unexpected application error occurred: {e}")
        exit(2)
