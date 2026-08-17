"""
Main Flask application for the AI Newsletter Agent.

Provides a web dashboard for fetching AI newsletters from Gmail,
summarizing them with Gemini, reviewing/editing the draft, and
publishing to SharePoint as a News post.
"""
import json
import logging
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

import config
import gmail_reader
import summarizer
import sharepoint_publisher
import storage
from summarizer import DailyDigest, NewsItem

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Home page — shows today's status and action buttons."""
    draft_row = storage.get_today_draft()
    draft_status = "Ready for review" if draft_row else "No draft yet"
    published_count = len(storage.get_published_posts())

    # Build a lightweight draft preview dict for the template
    draft_preview = None
    if draft_row:
        try:
            digest = DailyDigest.model_validate_json(draft_row["content_json"])
            draft_preview = {"title": digest.title, "intro": digest.intro}
        except Exception:
            draft_preview = {"title": draft_row.get("title", ""), "intro": ""}

    return render_template(
        "dashboard.html",
        email_count=0,
        draft_status=draft_status,
        published_count=published_count,
        draft=draft_preview,
    )


@app.route("/fetch", methods=["POST"])
def fetch():
    """Fetch today's newsletters from Gmail, summarize with Gemini, save draft."""
    try:
        service = gmail_reader.get_gmail_service()
        emails = gmail_reader.fetch_todays_newsletters(service, config.GMAIL_LABEL)

        # Filter out already-processed emails
        new_emails = [e for e in emails if not storage.is_email_processed(e.id)]

        if not new_emails:
            flash("No new newsletters found today.", "info")
        else:
            digest = summarizer.summarize_newsletters(new_emails)

            # Mark every processed email so we don't re-summarize
            for e in new_emails:
                storage.mark_email_processed(e.id, e.subject)

            today = datetime.now().strftime("%Y-%m-%d")
            storage.save_draft(today, digest.title, digest.model_dump_json())

            flash(
                f"Summarized {len(new_emails)} newsletter(s) into "
                f"{len(digest.items)} stories.",
                "success",
            )

    except Exception as e:
        logger.error("Fetch error: %s", e, exc_info=True)
        flash(f"Error: {e}", "error")

    return redirect(url_for("dashboard"))


@app.route("/review", methods=["GET", "POST"])
def review():
    """Review, edit, and approve the daily digest draft."""
    draft_row = storage.get_today_draft()
    if not draft_row:
        flash("No draft available for today.", "info")
        return redirect(url_for("dashboard"))

    # ---- POST: save edits or approve & publish ----
    if request.method == "POST":
        action = request.form.get("action")

        # Reconstruct a DailyDigest from the individual form fields
        try:
            item_count = int(request.form.get("item_count", 0))
            items: list[NewsItem] = []
            for i in range(item_count):
                headline = request.form.get(f"items[{i}].headline", "")
                summary_text = request.form.get(f"items[{i}].summary", "")
                why = request.form.get(f"items[{i}].why_it_matters", "")
                source = request.form.get(f"items[{i}].source", "")
                # Skip items that have been "removed" (all fields blank)
                if headline.strip() or summary_text.strip():
                    items.append(
                        NewsItem(
                            headline=headline,
                            summary=summary_text,
                            why_it_matters=why,
                            source=source,
                        )
                    )

            digest = DailyDigest(
                title=request.form.get("title", ""),
                intro=request.form.get("intro", ""),
                items=items,
                closing=request.form.get("closing", ""),
            )
        except Exception as e:
            flash(f"Error parsing form data: {e}", "error")
            return redirect(url_for("review"))

        if action == "save":
            storage.update_draft(
                draft_row["id"], digest.title, digest.model_dump_json()
            )
            flash("Draft saved.", "success")
            return redirect(url_for("review"))

        elif action == "approve":
            try:
                # Update draft content in DB
                storage.update_draft(
                    draft_row["id"], digest.title, digest.model_dump_json()
                )
                storage.mark_draft_published(draft_row["id"])
                
                today = datetime.now().strftime("%Y-%m-%d")
                ready_url = url_for("ready", draft_id=draft_row["id"])
                storage.save_published_post(today, digest.title, ready_url)

                flash("Draft approved! Content is ready to copy into SharePoint.", "success")
                return redirect(url_for("ready", draft_id=draft_row["id"]))
            except Exception as e:
                logger.error("Approve error: %s", e, exc_info=True)
                flash(f"Error: {e}", "error")

            return redirect(url_for("dashboard"))

    # ---- GET: show the draft for editing ----
    digest = DailyDigest.model_validate_json(draft_row["content_json"])
    return render_template("review.html", draft=digest)


@app.route("/ready/<int:draft_id>")
def ready(draft_id: int):
    """Show the approved digest formatted for manual copy/paste into SharePoint."""
    draft_row = storage.get_draft_by_id(draft_id)
    if not draft_row:
        flash("Draft not found.", "error")
        return redirect(url_for("dashboard"))

    digest = DailyDigest.model_validate_json(draft_row["content_json"])
    html_content = sharepoint_publisher.digest_to_html(digest)
    markdown_content = sharepoint_publisher.digest_to_markdown(digest)

    return render_template(
        "ready.html",
        digest=digest,
        html_content=html_content,
        markdown_content=markdown_content,
    )


@app.route("/history")
def history():
    """Show all previously published posts."""
    posts = storage.get_published_posts()
    return render_template("history.html", posts=posts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting AI Newsletter Agent on http://localhost:5000")
    app.run(debug=True, port=5000)
