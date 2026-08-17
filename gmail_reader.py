"""
Module for authenticating with Gmail and fetching newsletters.
"""
import os
import logging
import base64
from datetime import datetime
from dataclasses import dataclass
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

import config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

@dataclass
class EmailContent:
    id: str
    subject: str
    sender: str
    date: str
    body_text: str
    body_html: str

def get_gmail_service() -> Resource:
    """
    Authenticate and return the Gmail service object.
    Uses InstalledAppFlow to authenticate the user and caches the token.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing Gmail token...")
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed ({e}). Re-authenticating...")
                if os.path.exists('token.json'):
                    os.remove('token.json')
                creds = None

        if not creds:
            logger.info("Starting new OAuth flow for Gmail...")
            flow = InstalledAppFlow.from_client_secrets_file(config.GMAIL_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def get_label_id(service: Resource, label_name: str) -> tuple[str, str]:
    """Get the internal label ID and matched name for a given label name."""
    try:
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        clean_target = label_name.lower().replace('-', ' ').replace('_', ' ').strip()
        for label in labels:
            clean_name = label['name'].lower().replace('-', ' ').replace('_', ' ').strip()
            if clean_name == clean_target or label['name'].lower() == label_name.lower():
                return label['id'], label['name']
        logger.warning(f"Label '{label_name}' not found.")
        return None, None
    except Exception as e:
        logger.error(f"Error fetching labels: {e}")
        return None, None

def fetch_todays_newsletters(service: Resource, label_name: str) -> list[EmailContent]:
    """
    Fetch newsletters from Gmail that match the given label.
    """
    label_id, matched_name = get_label_id(service, label_name)
    if not label_id:
        logger.warning(f"Could not find matching label for '{label_name}'")
        return []
    
    logger.info(f"Querying Gmail using Label ID: {label_id} ({matched_name})")
    
    emails = []
    try:
        # Query using labelIds parameter directly to avoid search syntax issue with spaces/dashes
        results = service.users().messages().list(userId='me', labelIds=[label_id], maxResults=20).execute()
        messages = results.get('messages', [])
        
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
            sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
            date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
            
            payload = msg_data.get('payload', {})
            body_text, body_html = _extract_body(payload)
            
            clean_text = _clean_html(body_html) if body_html else body_text
            
            emails.append(EmailContent(
                id=msg['id'],
                subject=subject,
                sender=sender,
                date=date_str,
                body_text=clean_text,
                body_html=body_html
            ))
            logger.info(f"Fetched email: {subject} from {sender}")
            
    except Exception as e:
        logger.error(f"Error fetching newsletters: {e}")
        
    return emails

def _extract_body(payload: dict) -> tuple[str, str]:
    """Extract plain text and html body from the email payload."""
    body_text = ""
    body_html = ""
    
    parts = [payload] if 'parts' not in payload else payload['parts']
    
    def parse_parts(pts):
        nonlocal body_text, body_html
        for part in pts:
            mime_type = part.get('mimeType')
            data = part.get('body', {}).get('data')
            if part.get('parts'):
                parse_parts(part['parts'])
            if data:
                decoded_data = base64.urlsafe_b64decode(data).decode('utf-8')
                if mime_type == 'text/plain':
                    body_text += decoded_data
                elif mime_type == 'text/html':
                    body_html += decoded_data

    parse_parts(parts)
    return body_text, body_html

def _clean_html(html: str) -> str:
    """Clean HTML content to extract meaningful text."""
    soup = BeautifulSoup(html, 'html.parser')
    for script_or_style in soup(['script', 'style', 'nav', 'footer']):
        script_or_style.decompose()
    return soup.get_text(separator='\n', strip=True)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        srv = get_gmail_service()
        newsletters = fetch_todays_newsletters(srv, config.GMAIL_LABEL)
        print(f"Fetched {len(newsletters)} newsletters.")
    except Exception as e:
        print(f"Error during testing: {e}")
