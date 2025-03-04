import os
from typing import List, Any
import logging
import pyodbc
from MSTokenManager import MSTokenManager
import struct
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.connection_string = os.getenv("AZURE_CONNECTION_STRING")
        self.ms_token_manager = MSTokenManager()
        if not self.connection_string:
            raise ValueError("The connection string has not been defined in the .env file.")

    def get_connection(self) -> pyodbc.Connection:
        logging.info("Connecting to MSSQL...")
        access_token = self.__get_token()
        conn = pyodbc.connect(self.connection_string, attrs_before = { 1256:access_token })
        logging.info("Connected to MSSQL.")
        return conn

    def __get_token(self):
        access_token = self.ms_token_manager.get_token()
        exptoken = b""
        for i in access_token:
            exptoken += bytes(i, encoding='utf-8')
            exptoken += bytes(1)
        tokenstruct = struct.pack("=i", len(exptoken)) + exptoken
        return tokenstruct

    def get_all_table_names(self) -> List[str]:
        """Retrieve all table names from the database."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
            cursor.execute(query)
            tables = [row[0] for row in cursor.fetchall()]
            return tables
        finally:
            cursor.close()
            conn.close()

    def get_schema(self) -> str:
        """Retrieve the schema for all tables dynamically."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Get all table names
            table_names = self.get_all_table_names()

            if not table_names:
                return "No tables found in the database."

            # Fetch schema for all tables
            query = f"""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME IN ({','.join(f"'{table}'" for table in table_names)})
            """

            cursor.execute(query)
            schema = cursor.fetchall()

            # Group schema details by table name
            schema_dict = {}
            for row in schema:
                table_name, column_name, data_type = row
                if table_name not in schema_dict:
                    schema_dict[table_name] = []
                schema_dict[table_name].append(f"{column_name} | {data_type}")

            # Format the schema output
            schema_output = "\n".join([f"Table: {table}\n" + "\n".join(columns) for table, columns in schema_dict.items()])
            return schema_output

        finally:
            cursor.close()
            conn.close()

    def execute_query(self, query: str) -> List[Any]:
        """Execute SQL query on the Azure SQL database and return results."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            return results
        finally:
            cursor.close()
            conn.close()

# Example usage
if __name__ == "__main__":
    data_manager = DatabaseManager()
    schema = data_manager.get_schema()
    print(schema)
