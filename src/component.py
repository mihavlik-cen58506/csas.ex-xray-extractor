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
        super().__init__()

    def run(self):
        """
        Main execution method.
        """
        logging.info("Component starting.")

        # Load and validate configuration parameters
        try:
            logging.info("Loading and validating configuration parameters...")
            params = Configuration(**self.configuration.parameters)
            logging.info("Configuration parameters loaded and validated.")

            if params.debug:
                logging.getLogger().setLevel(logging.DEBUG)
                logging.debug("Debug mode enabled.")

            logging.info("--- Loaded Parameters ---")
            logging.info(f"Debug: {params.debug}")
            logging.info(f"Incremental: {params.incremental}")
            logging.info(f"JQL Input Column: {params.jql_input_column}")
            logging.info(f"Result Output Column: {params.result_output_column}")
            logging.info(f"Project ID: {params.project_id}")
            logging.info(f"Folder Path: {params.folder_path}")
            logging.debug(
                f"Xray Client ID (last 5 chars): ...{params.xray_client_id[-5:]}"
            )
            logging.debug(
                f"Xray Client Secret (last 5 chars): ...{params.xray_client_secret[-5:]}"
            )
            logging.info("-------------------------")

        except UserException as e:
            logging.error(f"Configuration error: {e}")
            raise
        except Exception as e:
            logging.error(
                f"An unexpected error occurred during configuration loading: {e}"
            )
            raise UserException(f"Unexpected error during configuration: {e}")

        #
        # Initialize Xray API client
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
                "No input tables found. Please map exactly one input table."
            )

        if len(input_tables) > 1:
            logging.warning(
                f"More than one input table mapped ({len(input_tables)}). "
                "Processing the first one."
            )

        input_table_def = input_tables[0]
        logging.info(
            f"Processing input table: {input_table_def.name} "
            f"(file: {input_table_def.full_path})"
        )

        # ####### Read data, call API, and prepare output #######
        input_csv_path = input_table_def.full_path
        processed_rows = []
        row_count = 0

        try:
            with open(input_csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                if params.jql_input_column not in reader.fieldnames:
                    raise UserException(
                        f"Input table '{input_table_def.name}' is missing the required "
                        f"JQL column: '{params.jql_input_column}'. Available columns: "
                        f"{list(reader.fieldnames)}"
                    )

                logging.info(
                    "Input CSV header read. "
                    f"Required JQL column '{params.jql_input_column}' found."
                )

                output_fieldnames = list(reader.fieldnames)
                if params.result_output_column not in output_fieldnames:
                    output_fieldnames.append(params.result_output_column)
                else:
                    logging.warning(
                        f"Output column name '{params.result_output_column}' already "
                        "exists in input. It will be overwritten."
                    )

                logging.info("Processing rows and calling Xray API...")
                for row in reader:
                    row_count += 1
                    logging.debug(f"Processing row {row_count}.")

                    jql_query = row.get(params.jql_input_column, "").strip()

                    if not jql_query:
                        logging.debug(
                            f"Row {row_count}: JQL column '{params.jql_input_column}' "
                            "is empty. Querying using only Project ID and Folder Path."
                        )
                    else:
                        logging.debug(f"Row {row_count}: JQL query: '{jql_query}'")

                    # ####### Call Xray API #######
                    try:
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
                        row[params.result_output_column] = f"API_ERROR: {api_exc}"
                        logging.warning(
                            f"Row {row_count}: API call failed. "
                            "Storing error message in result column."
                        )

                    processed_rows.append(row)

                logging.info(
                    f"Finished processing {row_count} rows. "
                    f"Collected {len(processed_rows)} rows for output."
                )

        except FileNotFoundError:
            logging.error(f"Input CSV file not found: {input_csv_path}")
            raise UserException(
                "Input file not found. Check Input Mapping and source table."
            )
        except Exception as e:
            logging.error(f"Error reading or processing input CSV: {e}")
            raise UserException(f"Error processing input data or calling API: {e}")

        # ####### Write Output Table #######
        # Get output table definition using create_out_table_definition
        logging.info("Creating output table definition...")

        output_tables_config = self.configuration.tables_output_mapping
        if not output_tables_config:
            raise UserException(
                "No output tables defined. Please map at least one output table."
            )
        if len(output_tables_config) > 1:
            logging.warning(
                f"More than one output table defined ({len(output_tables_config)}). "
                "Using the first one for output."
            )

        first_output_table_config = output_tables_config[0]

        try:
            output_table_source_name = first_output_table_config.source
            output_table_destination_name = first_output_table_config.destination
            primary_key_config = getattr(first_output_table_config, "primary_key", None)

        except AttributeError as e:
            raise UserException(
                f"Failed to access output mapping attributes (e.g., .destination, .primary_key): {e}. "
                "Ensure the output mapping is correctly defined and the library version is compatible."
            )

        try:
            # Create the TableDefinition object
            output_table_def = self.create_out_table_definition(
                name=output_table_source_name,
                schema=output_fieldnames,
                destination=output_table_destination_name,
                primary_key=primary_key_config,
            )

            if params.incremental:
                if not output_table_def.primary_key:
                    raise UserException(
                        "Incremental loading requested but no primary key "
                        "is defined in the output table mapping."
                    )
                output_table_def.incremental = True
                logging.debug("Incremental loading enabled for output manifest.")

            logging.info(
                f"Writing output to table: {output_table_def.name} "
                f"(file: {output_table_def.full_path})"
            )

            # 2. Write the processed data to the output CSV file
            output_csv_path = output_table_def.full_path
            logging.info(
                f"Writing {len(processed_rows)} rows to output CSV file: "
                f"{output_csv_path}"
            )

            with open(
                output_csv_path, mode="wt", encoding="utf-8", newline=""
            ) as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=output_fieldnames)

                writer.writeheader()
                writer.writerows(processed_rows)

            logging.info("Output CSV file written successfully.")

            # 3. Write the manifest file for the output table
            logging.info(
                "Writing manifest file for output table: "
                f"{output_table_def.full_path}.manifest"
            )
            self.write_manifest(output_table_def)
            logging.info("Manifest file written successfully.")

        except Exception as e:
            logging.error(
                f"Error creating output table definition, "
                f"writing CSV or manifest: {e}"
            )
            raise UserException(f"Error writing output data: {e}")

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
