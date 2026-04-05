import os
import struct
import pyodbc
from datetime import datetime, timezone, timedelta
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from mssql.base import DatabaseWrapper as MSSQLDatabaseWrapper

SQL_COPT_SS_ACCESS_TOKEN = 1256


def _get_credential():
    tenant = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant and client_id and secret:
        print(">>> Using ClientSecretCredential for Entra auth")
        return ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=secret)

    print(">>> Using DefaultAzureCredential for Entra auth")
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _access_token_struct() -> bytes:
    cred = _get_credential()
    token = cred.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    return struct.pack("<I", len(token_bytes)) + token_bytes


class DatabaseWrapper(MSSQLDatabaseWrapper):
    """
    Django DB backend using Entra access token.
    We bypass mssql-django's connection-string builder and connect via pyodbc directly.
    """

    def get_new_connection(self, conn_params):
        settings_dict = self.settings_dict

        driver = (settings_dict.get("OPTIONS") or {}).get("driver") or os.getenv("DRIVER", "ODBC Driver 18 for SQL Server")
        server = settings_dict.get("HOST") or os.getenv("DB_SERVER")
        database = settings_dict.get("NAME") or os.getenv("DB_IDMP_DATABASE")
        extra_params = (settings_dict.get("OPTIONS") or {}).get("extra_params", "Connection Timeout=30;")

        if not server or not database:
            raise ValueError("DB_SERVER/HOST and DB_IDMP_DATABASE/NAME must be set.")

        # Ensure secure defaults
        if "Encrypt=" not in extra_params:
            extra_params += ";Encrypt=yes"
        if "TrustServerCertificate=" not in extra_params:
            extra_params += ";TrustServerCertificate=no"

        conn_str = (
            f"Driver={{{driver}}};"
            f"Server={server};"
            f"Database={database};"
            f"{extra_params};"
        )

        tok = _access_token_struct()
        print(">>> Using Entra token auth for Django DB connection")
        conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: tok})

        # datetimeoffset (ODBC type -155) is not handled by mssql-django.
        # Convert it to a Python datetime with UTC offset.
        def _handle_datetimeoffset(dto_value):
            # dto_value is a bytes object: YYYY-MM-DD HH:MM:SS.fffffff +HH:MM
            tup = struct.unpack("<6hI2h", dto_value)
            dt = datetime(tup[0], tup[1], tup[2], tup[3], tup[4], tup[5],
                          tup[6] // 1000,
                          tzinfo=timezone(timedelta(hours=tup[7], minutes=tup[8])))
            return dt

        conn.add_output_converter(-155, _handle_datetimeoffset)
        return conn