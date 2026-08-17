"""
Module for summarizing newsletters using Google Gemini AI.
"""
import logging
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import config
from gmail_reader import EmailContent

logger = logging.getLogger(__name__)

class NewsItem(BaseModel):
    headline: str = Field(description="Catchy, concise headline")
    summary: str = Field(description="2-3 sentence summary")
    why_it_matters: str = Field(description="Why this matters for AI practitioners")
    source: str = Field(description="Newsletter name or source")

class DailyDigest(BaseModel):
    title: str = Field(description="Blog post title")
    intro: str = Field(description="Engaging 1-2 sentence intro")
    items: list[NewsItem] = Field(description="Top 5-7 most interesting news items")
    closing: str = Field(description="Brief closing paragraph")

SYSTEM_PROMPT = """
You are a senior AI journalist and analyst. Your job is to read through various AI newsletters 
and create a highly engaging, insightful daily digest.
- Prioritize novel developments, breakthroughs, and practical tools over hype or marketing.
- Deduplicate stories if multiple newsletters cover the same topic.
- Rank the items by impact and importance.
- Limit to the top 5-7 most interesting items.
"""

def summarize_newsletters(emails: list[EmailContent]) -> DailyDigest:
    """
    Summarize a list of emails into a single DailyDigest using Gemini.
    """
    if not emails:
        raise ValueError("No emails provided for summarization.")
        
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    combined_context = []
    for email in emails:
        combined_context.append(f"Source: {email.sender}\nSubject: {email.subject}\nContent:\n{email.body_text}\n---")
    
    full_text = "\n".join(combined_context)
    logger.info(f"Total context length for summarization: {len(full_text)} characters")
    
    # In a fully robust production system, we'd chunk this if len(full_text) > 100k
    # For now, we will pass it directly assuming context window (1M tokens) is sufficient.
    
    candidate_models = ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.1-flash-lite']
    last_error = None

    for model_name in candidate_models:
        try:
            logger.info(f"Calling Gemini ({model_name}) for summarization...")
            response = client.models.generate_content(
                model=model_name,
                contents=full_text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=DailyDigest,
                    temperature=0.3
                ),
            )
            logger.info(f"Summarization complete using {model_name}.")
            return response.parsed if hasattr(response, 'parsed') and response.parsed else DailyDigest.model_validate_json(response.text)
        except Exception as e:
            logger.warning(f"Model {model_name} failed: {e}. Trying fallback...")
            last_error = e

    raise last_error

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sample_emails = [
        EmailContent(id="1", subject="OpenAI releases new model", sender="AI Weekly", date="Today", body_text="OpenAI has released a new reasoning model today.", body_html=""),
        EmailContent(id="2", subject="Gemini 2.0 Flash is here", sender="Google News", date="Today", body_text="Google announced Gemini 2.0 Flash, a highly efficient model.", body_html="")
    ]
    try:
        digest = summarize_newsletters(sample_emails)
        print(digest.model_dump_json(indent=2))
    except Exception as e:
        print(f"Error during testing: {e}")
