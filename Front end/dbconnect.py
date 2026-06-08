import os
import struct
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from azure.identity import ClientSecretCredential, DefaultAzureCredential

SQL_COPT_SS_ACCESS_TOKEN = 1256
_ENGINE = None


def _get_credential():
    tenant = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant and client_id and secret:
        return ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=secret)
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _get_raw_conn():
    cred = _get_credential()
    token = cred.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack("<I", len(token_bytes)) + token_bytes

    driver = os.getenv("DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_IDMP_DATABASE")

    if not server or not database:
        raise ValueError("DB_SERVER and DB_IDMP_DATABASE must be set.")

    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            "mssql+pyodbc://",
            creator=_get_raw_conn,
            poolclass=NullPool,
            pool_pre_ping=True,
            future=True,
        )
    return _ENGINE