import logging
import os
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None


def _ensure_client() -> MongoClient:
    """Create (or reuse) a MongoDB client configured for the listings cluster."""

    global _client

    if _client is not None:
        return _client

    db_password = os.environ.get("MONGODB_PW")
    if not db_password:
        raise RuntimeError("MONGODB_PW environment variable not set. Cannot connect to MongoDB.")

    encoded_pw = quote(db_password, safe="")
    uri = (
        "mongodb+srv://Vercel-Admin-property_listing:"
        f"{encoded_pw}@cluster0.fznmnjx.mongodb.net/?appName=Cluster0"
    )

    client = MongoClient(uri, server_api=ServerApi("1"))

    try:
        client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - defensive logging branch
        raise ConnectionError("Unable to ping MongoDB deployment.") from exc

    logger.info("Successfully connected to MongoDB deployment.")
    _client = client
    return _client


def reset_client_for_tests() -> None:
    """Clear cached Mongo client (testing helper)."""

    global _client
    _client = None


def get_property_listing():
    client = _ensure_client()
    db = client["property"]
    collection = db["property-listing"]
    documents = list(collection.find({}))
    return documents
