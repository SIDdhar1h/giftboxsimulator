import os
import json
import logging
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ──────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service_account.json")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "177_cbVKg8azNSod84AU2UPX4yaB7HUWPfUTdeJz7a2I")
TAB_NAME = os.environ.get("SHEET_TAB_NAME", "Master Data")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ──────────────────────────────────────────────
#  APP SETUP
# ──────────────────────────────────────────────
flask_app = Flask(__name__)
CORS(flask_app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  CONFIG LOADERS
# ──────────────────────────────────────────────

def load_items_config():
    with open(os.path.join(CONFIGS_DIR, "items_config.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def load_images_config():
    with open(os.path.join(CONFIGS_DIR, "images_config.json"), "r", encoding="utf-8") as f:
        return json.load(f)

# ──────────────────────────────────────────────
#  PRICING LOGIC  (isolated, never exposed to FE)
# ──────────────────────────────────────────────

def calculate_total(selected_ids, items):
    by_id = {it["id"]: it for it in items}
    return sum(by_id[sid]["price"] for sid in selected_ids if sid in by_id)

def get_selected_names(selected_ids, items):
    by_id = {it["id"]: it for it in items}
    return ", ".join(by_id[sid]["name"] for sid in selected_ids if sid in by_id)

# ──────────────────────────────────────────────
#  GOOGLE SHEETS
# ──────────────────────────────────────────────

def get_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)

def append_row(row):
    svc = get_sheets_service()
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{TAB_NAME}!A:Z",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    logger.info("Row appended to Google Sheet")

# ──────────────────────────────────────────────
#  API ROUTES
# ──────────────────────────────────────────────

from flask import send_from_directory

@flask_app.route("/")
def serve_frontend():
    return send_from_directory("frontend", "index.html")

@flask_app.route("/api/health")
def health():
    return jsonify(status="ok")

# --- Items config (no prices) ---
@flask_app.route("/api/config")
def get_config():
    cfg = load_items_config()
    items = []
    for it in cfg["items"]:
        items.append({
            "id": it["id"],
            "name": it["name"],
            "image": it.get("image", ""),
            "emoji": it.get("emoji", ""),
            "description": it.get("description", ""),
            "lore": it.get("lore", ""),
        })
    return jsonify(
        occasion=cfg["occasion"],
        deity=cfg["deity"],
        deity_blessing=cfg.get("deity_blessing", ""),
        items=items,
    )

# --- Images config ---
@flask_app.route("/api/images")
def get_images():
    return jsonify(load_images_config())

# --- Submit ---
@flask_app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(force=True)

    # Unpack pages
    p1 = data.get("page1", {})
    p2 = data.get("page2", {})
    selected_ids = data.get("selected_item_ids", [])
    p4 = data.get("page4", {})

    # Validate required
    if not p1.get("name") or not p1.get("email"):
        return jsonify(error="Name and email are required"), 400
    if not selected_ids:
        return jsonify(error="Please select at least one item"), 400

    # Load config for pricing
    cfg = load_items_config()
    items = cfg["items"]
    valid_ids = {it["id"] for it in items}
    bad = [s for s in selected_ids if s not in valid_ids]
    if bad:
        return jsonify(error=f"Invalid item IDs: {bad}"), 400

    total = calculate_total(selected_ids, items)
    names = get_selected_names(selected_ids, items)
    count = len(selected_ids)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build sheet row (22 cols)
    row = [
        ts,
        p1.get("name", ""),
        p1.get("email", ""),
        p1.get("age", ""),
        p1.get("gender", ""),
        p1.get("occupation", ""),
        p1.get("identity_type", ""),
        p1.get("gifting_spend", ""),  # ✅ NEW
        p1.get("considered_devotional", ""),  # ✅ NEW
        ", ".join(p1.get("gift_occasions", [])) if isinstance(p1.get("gift_occasions"), list) else p1.get("gift_occasions", ""),
        p1.get("gift_recipients", ""),
        p1.get("shopping_channel", ""),
        p2.get("decision_logic", ""),
        p2.get("prayer_frequency", ""),
        p2.get("ritual_teacher", ""),
        str(p2.get("ritual_strictness", "")) if p2.get("ritual_strictness") else "",
        str(p2.get("authenticity_importance", "")) if p2.get("authenticity_importance") else "",
        cfg["occasion"],
        cfg["deity"],
        names,
        str(count),
        p4.get("perceived_price", ""),
        p4.get("temple_vetted_price", ""),
        str(total),
    ]

    try:
        append_row(row)
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return jsonify(error=f"Failed to save: {e}"), 500

    return jsonify(
        success=True,
        total_price=total,
        selected_items=names,
        item_count=count,
        message="Your gift box preferences have been saved successfully!",
    )

# ──────────────────────────────────────────────
#  ASGI WRAPPER  (so uvicorn can serve Flask)
# ──────────────────────────────────────────────
from a2wsgi import WSGIMiddleware
app = WSGIMiddleware(flask_app)      # uvicorn picks up this `app`

# For local dev:  python server.py
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8001, debug=True)

