import logging
import os
import sys
from importlib import util as importlib_util
from urllib.parse import quote

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

try:
    from pymongo.mongo_client import MongoClient
except ModuleNotFoundError as exc:
    logger.error("Failed to import pymongo.mongo_client: %s", exc)
    logger.info("Python executable: %s", sys.executable)
    logger.info("sys.path entries: %s", sys.path)
    logger.info("importlib.util.find_spec('pymongo') returned: %s", importlib_util.find_spec("pymongo"))
    raise

load_dotenv()
db_password = os.environ.get("MONGODB_PW")
encoded_pw = quote(db_password, safe='')

if db_password:
    # Use an f-string to safely insert the password into the URI
    uri = f"mongodb+srv://Vercel-Admin-property_listing:{encoded_pw}@cluster0.fznmnjx.mongodb.net/?appName=Cluster0"    
    # Create a new client and connect to the server
    client = MongoClient(uri)

    # Send a ping to confirm a successful connection
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)
else:
    print("Error: DB_PASSWORD environment variable not set. Cannot connect to MongoDB.")

def get_property_listing(client):
    db = client['property']
    collection = db['property-listing']
    documents = list(collection.find({}))
    return documents
