"""
app.py — Flask application: routes and startup

Serves the web UI and JSON API endpoints.
Initialises the database and GPIO button on startup.

Routes
------
GET  /                        → homepage (task list + status)
POST /add-task                → manually add a task
POST /task/<id>/complete      → mark task as completed
POST /task/<id>/undo          → revert task to pending
POST /task/<id>/delete        → delete a task
POST /clear-completed         → delete all completed tasks
GET  /api/state               → JSON app state
GET  /api/tasks               → JSON task list
"""

import logging
import os

from flask import Flask, jsonify, redirect, render_template, request, url_for
from dotenv import load_dotenv

import db
import gpio_handler
import state

# ---------------------------------------------------------------------------
# Load environment variables from .env if present
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    current_state = state.get()
    pending = db.get_pending_tasks()
    completed = db.get_completed_tasks()
    return render_template(
        "index.html",
        app_state=current_state,
        pending=pending,
        completed=completed,
    )


# ---------------------------------------------------------------------------
# Task management routes
# ---------------------------------------------------------------------------

@app.route("/add-task", methods=["POST"])
def add_task():
    task_text = request.form.get("task_text", "").strip()
    if task_text:
        db.insert_task(task_text, source_transcript="manual")
        logger.info("[app] Manual task added: %s", task_text)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/complete", methods=["POST"])
def complete_task(task_id: int):
    db.mark_complete(task_id)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/undo", methods=["POST"])
def undo_task(task_id: int):
    db.mark_pending(task_id)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id: int):
    db.delete_task(task_id)
    return redirect(url_for("index"))


@app.route("/clear-completed", methods=["POST"])
def clear_completed():
    count = db.clear_completed()
    logger.info("[app] Cleared %d completed task(s).", count)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.route("/api/state")
def api_state():
    """Return the current in-memory app state as JSON."""
    return jsonify(state.get())


@app.route("/api/tasks")
def api_tasks():
    """Return all tasks as JSON, split into pending and completed lists."""
    return jsonify({
        "pending": db.get_pending_tasks(),
        "completed": db.get_completed_tasks(),
    })


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _startup() -> None:
    """Initialise the database and GPIO button before handling requests."""
    logger.info("[app] Initialising database...")
    try:
        db.init_db()
    except Exception as exc:
        logger.error("[app] Database initialisation failed: %s", exc)
        state.set_error(f"Database initialisation failed: {exc}")

    logger.info("[app] Initialising GPIO button...")
    gpio_handler.setup()

    logger.info("[app] Ready.")


_startup()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug, use_reloader=False)
