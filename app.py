import os
import json
import logging
from datetime import datetime

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ──────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")
SHEET_ID    = os.environ.get("GOOGLE_SHEET_ID", "177_cbVKg8azNSod84AU2UPX4yaB7HUWPfUTdeJz7a2I")
TAB_NAME    = os.environ.get("SHEET_TAB_NAME", "Master Data")
SCOPES      = ["https://www.googleapis.com/auth/spreadsheets"]

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
#  PRICING LOGIC  (never exposed to frontend)
# ──────────────────────────────────────────────

def calculate_total(selected_ids, items):
    by_id = {it["id"]: it for it in items}
    return sum(by_id[sid]["price"] for sid in selected_ids if sid in by_id)

def get_selected_names(selected_ids, items):
    by_id = {it["id"]: it for it in items}
    return ", ".join(by_id[sid]["name"] for sid in selected_ids if sid in by_id)

# ──────────────────────────────────────────────
#  PERSONALITY SCORING  (mirrors frontend logic)
# ──────────────────────────────────────────────

def compute_personality(p1: dict) -> str:
    score = 0
    score += (p1.get("ritual_strictness") or 0) * 12
    score += (p1.get("authenticity_importance") or 0) * 10

    decision_logic = p1.get("decision_logic") or []
    if isinstance(decision_logic, str):
        decision_logic = [x.strip() for x in decision_logic.split(",")]
    if "tradition"   in decision_logic: score += 20
    if "meaning"     in decision_logic: score += 10
    if "convenience" in decision_logic: score -= 15

    prayer = p1.get("prayer_frequency") or []
    if isinstance(prayer, str):
        prayer = [x.strip() for x in prayer.split(",")]
    if "Twice a day"  in prayer: score += 20
    if "Daily"        in prayer: score += 14
    if "Weekly"       in prayer: score += 8
    if "On festivals" in prayer: score += 3
    if "Rarely"       in prayer: score -= 5
    if "Never"        in prayer: score -= 10

    teacher = p1.get("ritual_teacher", "")
    if teacher in ("Parents / Grandparents", "Priest / Pandit"):
        score += 10
    if teacher in ("YouTube / Social media", "Self-taught"):
        score -= 5

    if score >= 80: return "The Devoted"
    if score >= 50: return "The Ritualist"
    if score >= 25: return "The Seeker"
    return "The Celebrant"

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def join_list(val):
    """Accept a list or comma-string, return a comma-joined string."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val) if val else ""

def sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"

# ──────────────────────────────────────────────
#  GOOGLE SHEETS
# ──────────────────────────────────────────────

def get_sheets_service():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in os.environ:
        creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)

def append_row(row):
    try:
        svc = get_sheets_service()
        svc.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=f"{TAB_NAME}!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute(num_retries=3)
        logger.info("Row appended to Google Sheet")

    except Exception as e:
        logger.error(f"Sheet error: {e}")
        raise

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

@flask_app.route("/api/config")
def get_config():
    cfg = load_items_config()
    items = [
        {
            "id":          it["id"],
            "name":        it["name"],
            "image":       it.get("image", ""),
            "emoji":       it.get("emoji", ""),
            "description": it.get("description", ""),
            "lore":        it.get("lore", ""),
        }
        for it in cfg["items"]
    ]
    return jsonify(
        occasion=cfg["occasion"],
        deity=cfg["deity"],
        deity_blessing=cfg.get("deity_blessing", ""),
        items=items,
    )

@flask_app.route("/api/images")
def get_images():
    return jsonify(load_images_config())

@flask_app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(force=True)

    p1           = data.get("page1", {})
    selected_ids = data.get("selected_item_ids", [])
    p3           = data.get("page3", {})

    # ── Validation ──
    if not selected_ids:
        return jsonify(error="Please select at least one item"), 400
    if not p3.get("perceived_price"):
        return jsonify(error="Perceived price is required"), 400
    if not p3.get("temple_vetted_price"):
        return jsonify(error="Temple-vetted price is required"), 400
    if not (p3.get("other_item_suggestion") or "").strip():
        return jsonify(error="Please fill in the other item suggestion field"), 400
    if not (p3.get("age") or "").strip():
        return jsonify(error="Age is required"), 400
    if not (p3.get("gender") or "").strip():
        return jsonify(error="Gender is required"), 400
    if not (p3.get("occupation") or "").strip():
        return jsonify(error="Occupation is required"), 400

    # ── Pricing ──
    cfg = load_items_config()
    items = cfg["items"]
    valid_ids = {it["id"] for it in items}
    bad = [s for s in selected_ids if s not in valid_ids]
    if bad:
        return jsonify(error=f"Invalid item IDs: {bad}"), 400

    total       = calculate_total(selected_ids, items)
    names       = get_selected_names(selected_ids, items)
    count       = len(selected_ids)
    ts          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    personality = compute_personality(p1)

    # ── Sheet row — 23 columns (A–W) ──
    # Update your sheet header row to match:
    # A=Timestamp, B=Gift Occasions, C=Recipients, D=Shopping Channel,
    # E=Spend Bracket, F=Considered Devotional, G=Decision Logic,
    # H=Prayer Frequency, I=Ritual Teacher, J=Ritual Strictness,
    # K=Authenticity Importance, L=Occasion, M=Deity,
    # N=Selected Items, O=Item Count, P=Perceived Price,
    # Q=Temple WTP, R=Other Item Suggestion, S=Actual Total,
    # T=Personality, U=Age, V=Gender, W=Occupation
    row = [
        ts,                                                          # A
        join_list(p1.get("gift_occasions")),                         # B
        join_list(p1.get("gift_recipients")),                        # C
        join_list(p1.get("shopping_channel")),                       # D
        p1.get("gifting_spend", ""),                                 # E
        p1.get("considered_devotional", ""),                         # F
        join_list(p1.get("decision_logic")),                         # G
        join_list(p1.get("prayer_frequency")),                       # H
        join_list(p1.get("ritual_teacher")),                         # I
        str(p1.get("ritual_strictness") or ""),                      # J
        str(p1.get("authenticity_importance") or ""),                # K
        cfg["occasion"],                                             # L
        cfg["deity"],                                                # M
        names,                                                       # N
        str(count),                                                  # O
        p3.get("perceived_price", ""),                               # P
        p3.get("temple_vetted_price", ""),                           # Q
        (p3.get("other_item_suggestion") or "").strip(),             # R
        str(total),                                                  # S
        personality,                                                 # T
        p3.get("age", ""),                                           # U
        p3.get("gender", ""),                                        # V
        p3.get("occupation", ""),                                    # W
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
        personality=personality,
        message="Your gift box preferences have been saved successfully!",
    )


@flask_app.route("/api/submit-stream", methods=["POST"])
def submit_stream():
    """
    Same logic as /api/submit but streams progress via Server-Sent Events.
    Each event is: data: {"step": <int 1-4>, "label": "<text>", "done": false|true, "result": {...}}
    Steps:
      1 – Validating your answers
      2 – Computing your gifting personality
      3 – Saving to Google Sheets
      4 – Done (carries the result payload)
    On error: data: {"error": "<message>"}
    """
    data = request.get_json(force=True)

    p1           = data.get("page1", {})
    selected_ids = data.get("selected_item_ids", [])
    p3           = data.get("page3", {})

    def generate():
        # ── Step 1: Validate ──
        yield sse_event({"step": 1, "label": "Validating your answers…", "done": False})

        if not selected_ids:
            yield sse_event({"error": "Please select at least one item"}); return
        if not p3.get("perceived_price"):
            yield sse_event({"error": "Perceived price is required"}); return
        if not p3.get("temple_vetted_price"):
            yield sse_event({"error": "Temple-vetted price is required"}); return
        if not (p3.get("other_item_suggestion") or "").strip():
            yield sse_event({"error": "Please fill in the other item suggestion field"}); return
        if not (p3.get("age") or "").strip():
            yield sse_event({"error": "Age is required"}); return
        if not (p3.get("gender") or "").strip():
            yield sse_event({"error": "Gender is required"}); return
        if not (p3.get("occupation") or "").strip():
            yield sse_event({"error": "Occupation is required"}); return

        cfg = load_items_config()
        items = cfg["items"]
        valid_ids = {it["id"] for it in items}
        bad = [s for s in selected_ids if s not in valid_ids]
        if bad:
            yield sse_event({"error": f"Invalid item IDs: {bad}"}); return

        # ── Step 2: Compute personality ──
        yield sse_event({"step": 2, "label": "Computing your gifting personality…", "done": False})

        total       = calculate_total(selected_ids, items)
        names       = get_selected_names(selected_ids, items)
        count       = len(selected_ids)
        ts          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        personality = compute_personality(p1)

        row = [
            ts,
            join_list(p1.get("gift_occasions")),
            join_list(p1.get("gift_recipients")),
            join_list(p1.get("shopping_channel")),
            p1.get("gifting_spend", ""),
            p1.get("considered_devotional", ""),
            join_list(p1.get("decision_logic")),
            join_list(p1.get("prayer_frequency")),
            join_list(p1.get("ritual_teacher")),
            str(p1.get("ritual_strictness") or ""),
            str(p1.get("authenticity_importance") or ""),
            cfg["occasion"],
            cfg["deity"],
            names,
            str(count),
            p3.get("perceived_price", ""),
            p3.get("temple_vetted_price", ""),
            (p3.get("other_item_suggestion") or "").strip(),
            str(total),
            personality,
            p3.get("age", ""),
            p3.get("gender", ""),
            p3.get("occupation", ""),
        ]

        # ── Step 3: Save to Sheets ──
        yield sse_event({"step": 3, "label": "Saving your gift box to our records…", "done": False})

        try:
            append_row(row)
        except Exception as e:
            logger.error(f"Sheet error: {e}")
            yield sse_event({"error": f"Failed to save: {e}"}); return

        # ── Step 4: Done ──
        result = {
            "success":        True,
            "total_price":    total,
            "selected_items": names,
            "item_count":     count,
            "personality":    personality,
            "message":        "Your gift box preferences have been saved successfully!",
        }
        yield sse_event({"step": 4, "label": "All done!", "done": True, "result": result})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering if present
        },
    )


app = flask_app

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8001, debug=True)
