"""
Configuration module for the AI Newsletter Agent.
Loads and validates environment variables.
"""
import os
import logging
from dotenv import load_dotenv

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def get_env_var(var_name: str, required: bool = True) -> str:
    """Get an environment variable and optionally raise an error if missing."""
    value = os.getenv(var_name)
    if required and not value:
        logger.error(f"Missing required environment variable: {var_name}")
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value or ""

# Google / Gmail OAuth
GMAIL_CREDENTIALS_FILE = get_env_var("GMAIL_CREDENTIALS_FILE")

# Google Gemini API
GEMINI_API_KEY = get_env_var("GEMINI_API_KEY")

# Microsoft / SharePoint
MS_CLIENT_ID = get_env_var("MS_CLIENT_ID")
MS_TENANT_ID = get_env_var("MS_TENANT_ID")
SHAREPOINT_HOSTNAME = get_env_var("SHAREPOINT_HOSTNAME")
SHAREPOINT_SITE_PATH = get_env_var("SHAREPOINT_SITE_PATH")

# App Settings
GMAIL_LABEL = get_env_var("GMAIL_LABEL")
FLASK_SECRET_KEY = get_env_var("FLASK_SECRET_KEY")
