import csv
import logging

# Import necessary classes from keboola-component-base
from keboola.component.base import ComponentBase
from keboola.component.dao import TableDefinition  # For type hinting
from keboola.component.exceptions import UserException

# Import custom Configuration Pydantic model
from configuration import Configuration


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

        # Load and validate configuration parameters using Pydantic model
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
            # Log sensitive parameters only in debug mode and partially
            logging.debug(
                f"Xray Client ID (first 5 chars): {params.xray_client_id[:5]}..."
            )
            logging.debug(
                f"Xray Client Secret (first 5 chars): {params.xray_client_secret[:5]}..."
            )
            logging.info("-------------------------")

        except UserException as e:
            logging.error(f"Configuration error: {e}")
            raise  # Re-raise to fail job with exit code 1

        # Get input table definitions from Keboola Storage mapping
        logging.info("Getting input table definitions...")
        # This list is populated based on 'storage.input.tables' in config.json
        input_tables: list[TableDefinition] = self.get_input_tables_definitions()

        # Check if at least one input table is mapped (required for this component)
        if not input_tables:  # Equivalent to len(input_tables) == 0
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

        # Read data from the input table CSV file
        input_csv_path = input_table_def.full_path
        row_count = 0
        try:
            # Open and read the CSV file row by row using DictReader
            with open(input_csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                # Verify required JQL input column exists in CSV header
                if params.jql_input_column not in reader.fieldnames:
                    raise UserException(
                        f"Input table '{input_table_def.name}' is missing the required JQL column: '{params.jql_input_column}'. "
                        f"Available columns: {list(reader.fieldnames)}"
                    )

                logging.info(
                    f"Input CSV header read. Required JQL column '{params.jql_input_column}' found."
                )

                # Iterate through rows
                for row in reader:
                    row_count += 1
                    # Log JQL value sample for the first few rows (INFO level)
                    if row_count <= 3:
                        jql_value = row.get(
                            params.jql_input_column, ""
                        )  # Use .get for safety
                        logging.info(
                            f"Row {row_count}: JQL sample: '{jql_value[:80]}...'"
                        )

                    # Log the full row dictionary for the first few rows (DEBUG level)
                    # This will only appear in logs if debug mode is enabled in config
                    if row_count <= 3:
                        logging.debug(f"Row {row_count} full data: {row}")

        except FileNotFoundError:
            logging.error(f"Input CSV file not found: {input_csv_path}")
            raise UserException(
                "Input file not found. Check Input Mapping and source table."
            )
        except Exception as e:
            logging.error(f"Error reading input CSV: {e}")
            raise  # Re-raise unexpected errors

        # --- Next steps (API calls, processing, writing output) would go here ---

        logging.info("Component finished.")


# Main entrypoint: Initializes component and executes action (default 'run')
if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()  # Handles logging setup, config loading, and calling run()
        logging.info("Job completed successfully.")
    except UserException as exc:
        # Catch expected user/config errors and exit with status 1
        logging.error(f"User Error: {exc}")
        exit(1)
    except Exception:
        # Catch unexpected application errors and exit with status 2
        logging.exception("An unexpected application error occurred.")
        exit(2)
