"""
Module for publishing content to Microsoft SharePoint.
"""
import atexit
import logging
import requests
import msal

import config
from summarizer import DailyDigest

logger = logging.getLogger(__name__)

SCOPES = ['Sites.ReadWrite.All']
CACHE_FILE = 'ms_token_cache.json'
AUTHORITY = f"https://login.microsoftonline.com/{config.MS_TENANT_ID}"

def _build_msal_app() -> msal.PublicClientApplication:
    """Build the MSAL Public Client App with token cache."""
    cache = msal.SerializableTokenCache()
    try:
        with open(CACHE_FILE, 'r') as f:
            cache.deserialize(f.read())
    except FileNotFoundError:
        pass
    
    atexit.register(lambda: open(CACHE_FILE, 'w').write(cache.serialize()) if cache.has_state_changed else None)
    
    return msal.PublicClientApplication(
        config.MS_CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache
    )

def get_access_token() -> str:
    """Acquire an access token for Microsoft Graph."""
    app = _build_msal_app()
    accounts = app.get_accounts()
    result = None
    
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        
    if not result:
        logger.info("No suitable token exists in cache. Starting interactive auth...")
        # device_code_flow could be used here as well for headless servers
        result = app.acquire_token_interactive(scopes=SCOPES)
        
    if "access_token" in result:
        return result["access_token"]
    else:
        logger.error(f"Failed to acquire token: {result.get('error')} - {result.get('error_description')}")
        raise Exception(f"Failed to acquire token: {result.get('error')}")

def get_site_id(token: str, hostname: str, site_path: str) -> str:
    """Retrieve the Site ID for the configured SharePoint site."""
    headers = {'Authorization': f'Bearer {token}'}
    # For site_path, ensure it starts with a slash, e.g. /sites/AESE
    url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data['id']

def digest_to_html(digest: DailyDigest) -> str:
    """Convert a DailyDigest into HTML content suitable for a SharePoint post."""
    html = []
    html.append(f"<p><em>{digest.intro}</em></p>")
    html.append("<hr>")
    
    for item in digest.items:
        html.append(f"<h3>{item.headline}</h3>")
        html.append(f"<p><strong>Source:</strong> {item.source}</p>")
        html.append(f"<p>{item.summary}</p>")
        html.append(f"<p><strong>Why it matters:</strong> {item.why_it_matters}</p>")
        html.append("<br>")
        
    html.append("<hr>")
    html.append(f"<p>{digest.closing}</p>")
    
    return "\n".join(html)

def digest_to_markdown(digest: DailyDigest) -> str:
    """Convert a DailyDigest into Markdown content for SharePoint or text editors."""
    md = []
    md.append(f"# {digest.title}\n")
    md.append(f"*{digest.intro}*\n\n---")
    
    for item in digest.items:
        md.append(f"### {item.headline}")
        md.append(f"**Source:** {item.source}\n")
        md.append(f"{item.summary}\n")
        md.append(f"> **Why it matters:** {item.why_it_matters}\n")
        
    md.append("---\n")
    md.append(digest.closing)
    
    return "\n\n".join(md)

def create_news_post(token: str, site_id: str, digest: DailyDigest) -> str:
    """Create and publish a News Post on SharePoint."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # 1. Create the page
    create_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/pages"
    page_data = {
        "@odata.type": "#microsoft.graph.sitePage",
        "title": digest.title,
        "pageLayout": "article",
        "promotionKind": "newsPost"
    }
    
    logger.info("Creating page on SharePoint...")
    response = requests.post(create_url, headers=headers, json=page_data)
    response.raise_for_status()
    page = response.json()
    page_id = page['id']
    web_url = page.get('webUrl')
    
    # 2. Add content (canvas layout)
    # The Graph API for editing modern pages is complex, often requires Beta endpoints or specific schema
    # For simplicity, we use the v1.0 standard textWebPart if supported, or beta API.
    # We'll use the v1.0 endpoint as described in best practices if possible.
    html_content = digest_to_html(digest)
    
    # Simple workaround for content (Graph API v1.0 page content update):
    # This might require beta depending on tenant settings, but we will stick to v1.0 layout structures.
    # NOTE: Modern page publishing via Graph API v1.0 using canvasLayouts.
    patch_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/pages/{page_id}"
    patch_data = {
        "canvasLayout": {
            "horizontalSections": [
                {
                    "layout": "OneColumn",
                    "id": "1",
                    "columns": [
                        {
                            "id": "1",
                            "webparts": [
                                {
                                    "@odata.type": "#microsoft.graph.textWebPart",
                                    "innerHtml": html_content
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    logger.info("Adding content to page...")
    requests.patch(patch_url, headers=headers, json=patch_data).raise_for_status()
    
    # 3. Publish the page
    publish_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/pages/{page_id}/publish"
    logger.info("Publishing page...")
    requests.post(publish_url, headers=headers).raise_for_status()
    
    return web_url

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Simple manual test
    try:
        tok = get_access_token()
        print("Token acquired successfully.")
        # site = get_site_id(tok, config.SHAREPOINT_HOSTNAME, config.SHAREPOINT_SITE_PATH)
        # print(f"Site ID: {site}")
    except Exception as e:
        print(f"Error: {e}")
