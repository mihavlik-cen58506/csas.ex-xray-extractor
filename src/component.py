import csv
import json
import logging

import requests
from keboola.component.base import ComponentBase
from keboola.component.dao import TableDefinition
from keboola.component.exceptions import UserException

from configuration import Configuration
from xray_api import XrayApiClient


class Component(ComponentBase):
    """Keboola extractor that queries Xray Cloud GraphQL API for test counts.

    Reads input CSV rows, calls Xray API for each row where
    AUTE_DATA_AUTOMATICALLY='Y' and IS_VALID='Y', writes test counts
    into two output columns.
    """

    def __init__(self):
        super().__init__()

    def _should_process_row(self, row, row_count):
        """Return True if row has both AUTE_DATA_AUTOMATICALLY='Y' and IS_VALID='Y'."""
        auto_flag = row.get("AUTE_DATA_AUTOMATICALLY", "").strip().upper()
        valid_flag = row.get("IS_VALID", "").strip().upper()
        if auto_flag != "Y" or valid_flag != "Y":
            logging.debug(
                f"Row {row_count}: skipping "
                f"(AUTE_DATA_AUTOMATICALLY='{auto_flag}', IS_VALID='{valid_flag}')"
            )
            return False
        return True

    def _process_column_pair(self, row, input_col, xray_client, row_num, error_rows):
        """Parse JSON params from input_col and query Xray API for test count.

        Returns test count (int) on success, None on error.
        Errors are logged and appended to error_rows for summary.
        """
        input_data = row.get(input_col, "").strip()
        key_value = row.get("KEY", "N/A")
        name_value = row.get("NAME", "N/A")
        row_id = f"Row {row_num} (KEY: '{key_value}', NAME: '{name_value}')"

        if not input_data:
            error_msg = (
                f"{row_id}: Input column '{input_col}' is empty "
                f"but AUTE_DATA_AUTOMATICALLY is set to 'Y'."
            )
            logging.warning(error_msg)
            error_rows.append(error_msg)
            return None

        # Expected format: ["project_id", "folder_path", "jql_query"]
        try:
            params_array = json.loads(input_data)
            if not isinstance(params_array, list) or len(params_array) != 3:
                raise ValueError("Input must be JSON array with exactly 3 elements")

            project_id, folder_path, jql_query = params_array
            if not project_id or not project_id.strip():
                raise ValueError("Project ID is required and cannot be empty")

            project_id = project_id.strip()
            folder_path = folder_path.strip() if folder_path else None
            jql_query = jql_query.strip() if jql_query else None

            logging.debug(
                f"Row {row_num}: Parsed '{input_col}' - "
                f"Project: '{project_id}', Folder: '{folder_path}', JQL: '{jql_query}'"
            )

        except (json.JSONDecodeError, ValueError) as parse_exc:
            error_msg = (
                f"{row_id}: Failed to parse input data "
                f"in '{input_col}' '{input_data}': {parse_exc}"
            )
            logging.warning(error_msg)
            error_rows.append(error_msg)
            return None

        try:
            total_count = xray_client.query_tests_by_dynamic_params(
                project_id=project_id, folder_path=folder_path, jql_query=jql_query
            )
            logging.debug(
                f"Row {row_num}: API success for '{input_col}' - {total_count} tests found"
            )
            return total_count
        except (requests.RequestException, ValueError):
            logging.exception(
                f"Row {row_num}: Error calling Xray API for '{input_col}' - Project ID "
                f"'{project_id}', Folder Path '{folder_path}', JQL '{jql_query}'"
            )
            return None

    def run(self):
        """Main execution: load config -> auth -> read CSV -> call API -> write output."""
        # Load and validate configuration
        try:
            params = Configuration(**self.configuration.parameters)
        except UserException:
            raise

        if params.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug("Debug mode enabled.")

        logging.info(
            f"Config: input_cols=[{params.total_tests_source_column_input}, "
            f"{params.automated_tests_source_column_input}], "
            f"output_cols=[{params.total_tests_number_column_output}, "
            f"{params.automated_tests_number_column_output}], "
            f"debug={params.debug}, incremental={params.incremental}"
        )

        # Initialize Xray API client
        try:
            xray_client = XrayApiClient(
                client_id=params.xray_client_id,
                client_secret=params.xray_client_secret
            )
            logging.info("Xray API client authenticated.")
        except requests.RequestException as e:
            raise UserException(f"API Authentication/Initialization Error: {e}")

        # Get input table
        input_tables: list[TableDefinition] = self.get_input_tables_definitions()
        if not input_tables:
            raise UserException(
                "No input tables found. Please map exactly one input table."
            )
        input_table_def = input_tables[0]

        # Read data, call API, and prepare output
        input_csv_path = input_table_def.full_path
        processed_rows = []
        row_count = 0
        error_rows = []

        try:
            with open(input_csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                if params.total_tests_source_column_input not in reader.fieldnames:
                    raise UserException(
                        f"Input table '{input_table_def.name}' is missing the required "
                        f"input column: '{params.total_tests_source_column_input}'. "
                        f"Available columns: {list(reader.fieldnames)}"
                    )

                if params.automated_tests_source_column_input not in reader.fieldnames:
                    raise UserException(
                        f"Input table '{input_table_def.name}' is missing the required "
                        f"input column: '{params.automated_tests_source_column_input}'. "
                        f"Available columns: {list(reader.fieldnames)}"
                    )

                # Append output columns if not already present in input
                output_fieldnames = list(reader.fieldnames)
                for col in [
                    params.total_tests_number_column_output,
                    params.automated_tests_number_column_output,
                ]:
                    if col not in output_fieldnames:
                        output_fieldnames.append(col)

                # Process each row: skip invalid, query API for valid ones
                for row in reader:
                    row_count += 1

                    if not self._should_process_row(row, row_count):
                        processed_rows.append(row)
                        continue

                    row[params.total_tests_number_column_output] = (
                        self._process_column_pair(
                            row,
                            params.total_tests_source_column_input,
                            xray_client,
                            row_count,
                            error_rows,
                        )
                    )

                    row[params.automated_tests_number_column_output] = (
                        self._process_column_pair(
                            row,
                            params.automated_tests_source_column_input,
                            xray_client,
                            row_count,
                            error_rows,
                        )
                    )

                    processed_rows.append(row)

                logging.info(
                    f"Finished processing {row_count} rows. "
                    f"Collected {len(processed_rows)} rows for output."
                )

                if error_rows:
                    logging.warning(
                        f"PROCESSING SUMMARY: {len(error_rows)} problematic rows:\n"
                        + "\n".join([f"  - {error}" for error in error_rows])
                    )

        except FileNotFoundError:
            raise UserException(
                "Input file not found. Check Input Mapping and source table."
            )

        # Write output table
        output_tables_config = self.configuration.tables_output_mapping
        if not output_tables_config:
            raise UserException(
                "No output tables defined. Please map at least one output table."
            )

        first_output_config = output_tables_config[0]

        output_table_def = self.create_out_table_definition(
            name=first_output_config.source,
            schema=output_fieldnames,
            destination=first_output_config.destination,
            primary_key=getattr(first_output_config, "primary_key", None),
            has_header=True,
        )

        if params.incremental:
            if not output_table_def.primary_key:
                raise UserException(
                    "Incremental loading requested but no primary key "
                    "is defined in the output table mapping."
                )
            output_table_def.incremental = True

        try:
            with open(
                output_table_def.full_path, mode="w", encoding="utf-8", newline=""
            ) as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=output_fieldnames)
                writer.writeheader()
                writer.writerows(processed_rows)

            self.write_manifest(output_table_def)
            logging.info(
                f"Output written: {len(processed_rows)} rows to {output_table_def.name}"
            )
        except OSError as e:
            raise UserException(f"Error writing output data: {e}")


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
        logging.info("Job completed successfully.")
    except UserException as exc:
        logging.error(f"User Error: {exc}")
        exit(1)
    except Exception:
        logging.exception("An unexpected application error occurred")
        exit(2)
