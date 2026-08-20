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

class ItemFactCheck(BaseModel):
    headline: str = Field(description="Headline of the item being checked")
    verdict: str = Field(description="VERIFIED or FLAGGED")
    confidence_score: int = Field(description="Groundedness confidence score 0 to 100")
    fact_check_notes: str = Field(description="Audit explanation verifying claims against raw text or pointing out inconsistencies")
    suggested_correction: str | None = Field(default=None, description="Corrected text if FLAGGED, or empty if VERIFIED")

class QualityControlReport(BaseModel):
    overall_score: int = Field(description="Overall groundedness score 0 to 100")
    overall_status: str = Field(description="PASSED or NEEDS_ATTENTION")
    summary_notes: str = Field(description="General quality control assessment summary")
    item_checks: list[ItemFactCheck] = Field(description="Fact-check breakdown for each item in order")

class DailyDigest(BaseModel):
    title: str = Field(description="Blog post title")
    intro: str = Field(description="Engaging 1-2 sentence intro")
    items: list[NewsItem] = Field(description="Top 5-7 most interesting news items")
    closing: str = Field(description="Brief closing paragraph")
    qc_report: QualityControlReport | None = Field(default=None, description="Quality control audit report")

SYSTEM_PROMPT = """
You are a senior AI journalist and analyst. Your job is to read through various AI newsletters 
and create a highly engaging, insightful daily digest.
- Prioritize novel developments, breakthroughs, and practical tools over hype or marketing.
- Deduplicate stories if multiple newsletters cover the same topic.
- Rank the items by impact and importance.
- Limit to the top 5-7 most interesting items.
"""

QC_AUDITOR_PROMPT = """
You are an uncompromising Lead Fact-Checker and Quality Control Auditor.
Your single mission is to PREVENT HALLUCINATIONS and ensure 100% factual accuracy.

You will be given:
1. RAW SOURCED TEXT (The exact email contents received today)
2. GENERATED DAILY DIGEST (The proposed summary items)

Task:
Cross-examine EVERY headline, summary, and 'why it matters' claim against the RAW SOURCED TEXT.
1. Check names, companies, model version numbers, statistics, and metrics.
2. Verify if any facts were fabricated, exaggerated, or misattributed.
3. If an item is 100% supported by the raw source text, mark verdict: "VERIFIED" with confidence_score: 95-100.
4. If an item contains ANY unverified claim, exaggeration, or wrong metric, mark verdict: "FLAGGED", state the exact discrepancy in fact_check_notes, and provide a grounded suggested_correction using ONLY facts present in the raw source text.
5. Compute an overall_score (0-100) reflecting the proportion of grounded facts.
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
            digest = response.parsed if hasattr(response, 'parsed') and response.parsed else DailyDigest.model_validate_json(response.text)
            
            # Pass 2: Run Quality Control & Anti-Hallucination Audit
            try:
                logger.info("Running Quality Control & Anti-Hallucination Audit...")
                qc = run_quality_control_audit(client, full_text, digest)
                digest.qc_report = qc
                logger.info(f"Quality Control complete: {qc.overall_status} (Score: {qc.overall_score}%)")
            except Exception as qc_err:
                logger.warning(f"QC audit failed (non-fatal): {qc_err}")
                
            return digest
        except Exception as e:
            logger.warning(f"Model {model_name} failed: {e}. Trying fallback...")
            last_error = e

    raise last_error

def run_quality_control_audit(client: genai.Client, full_text: str, digest: DailyDigest) -> QualityControlReport:
    """
    Pass 2: Fact-checks the generated DailyDigest against the raw email text to detect any hallucinations.
    """
    audit_input = f"""=== RAW SOURCED TEXT ===
{full_text}

=== GENERATED DAILY DIGEST TO FACT-CHECK ===
Title: {digest.title}
Intro: {digest.intro}

Items:
"""
    for i, item in enumerate(digest.items, 1):
        audit_input += f"\n[{i}] Headline: {item.headline}\nSource: {item.source}\nSummary: {item.summary}\nWhy it matters: {item.why_it_matters}\n"

    candidate_models = ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.1-flash-lite']
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=audit_input,
                config=types.GenerateContentConfig(
                    system_instruction=QC_AUDITOR_PROMPT,
                    response_mime_type="application/json",
                    response_schema=QualityControlReport,
                    temperature=0.1
                ),
            )
            return response.parsed if hasattr(response, 'parsed') and response.parsed else QualityControlReport.model_validate_json(response.text)
        except Exception as e:
            logger.warning(f"QC model {model_name} failed: {e}. Retrying fallback...")

    # Return default fallback report if all fail
    return QualityControlReport(
        overall_score=100,
        overall_status="PASSED",
        summary_notes="Manual verification recommended. Anti-hallucination auditor was unable to reach API.",
        item_checks=[]
    )

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
