from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
CONFIG_FILE  = os.path.join(BASE_DIR, 'config.json')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "177_cbVKg8azNSod84AU2UPX4yaB7HUWPfUTdeJz7a2I")

HEADERS = [
    "Timestamp", "Cohort",
    "Name", "Email", "Age", "City",
    "Praying Frequency", "Taught By", "Prayer Steps",
    "Gifting Habits", "Must-Have Item",
    "Religious Approach", "Primary Feeling", "Gift Decision Basis", "Gift Box Gap",
    "Occasion", "Deity", "Selected Items", "Total Price (Rs.)"
]

def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

print("\n" + "="*60)
print("  MANGALDEEP GIFT BOX - startup check")
print("="*60)
print(f"  app.py       : {BASE_DIR}")
print(f"  frontend/    : {'EXISTS' if os.path.isdir(FRONTEND_DIR) else 'MISSING'}")
print(f"  index.html   : {'EXISTS' if os.path.isfile(os.path.join(FRONTEND_DIR,'index.html')) else 'MISSING'}")
print(f"  config.json  : {'EXISTS' if os.path.isfile(CONFIG_FILE) else 'MISSING'}")
print(f"  Sheet ID     : {SPREADSHEET_ID}")
print("="*60 + "\n")

@app.route('/')
def index():
    print(f"[GET /] serving index.html")
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/api/config')
def get_config():
    print("[GET /api/config] loading config")
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        safe_config = {
            "occasion": config["occasion"],
            "deity": config["deity"],
            "themeColor": config.get("themeColor", "#C8522A"),
            "accentColor": config.get("accentColor", "#F5A623"),
            "items": [
                {"id": item["id"], "name": item["name"], "image": item["image"], "emoji": item.get("emoji", "🎁")}
                for item in config["items"]
            ]
        }
        print(f"[GET /api/config] OK - {len(safe_config['items'])} items | {config['occasion']} - {config['deity']}")
        return jsonify(safe_config)
    except Exception as e:
        print(f"[GET /api/config] ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/calculate', methods=['POST'])
def calculate_price():
    try:
        data = request.json
        selected_ids = data.get('selectedItems', [])
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        price_map = {item['id']: item['price'] for item in config['items']}
        total = sum(price_map.get(i, 0) for i in selected_ids)
        print(f"[POST /api/calculate] {len(selected_ids)} items -> Rs.{total}")
        return jsonify({"total": total})
    except Exception as e:
        print(f"[POST /api/calculate] ERROR: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/submit', methods=['POST'])
def submit():
    print("[POST /api/submit] received")
    try:
        data = request.json

        if not data.get('email'):
            return jsonify({"error": "Email is required"}), 400
        if not data.get('selectedItems'):
            return jsonify({"error": "Please select at least one item"}), 400

        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        price_map    = {item['id']: item['price'] for item in config['items']}
        name_map     = {item['id']: item['name']  for item in config['items']}
        selected_ids = data.get('selectedItems', [])
        total        = sum(price_map.get(i, 0) for i in selected_ids)
        item_names   = ", ".join(name_map.get(i, i) for i in selected_ids)

        print(f"[POST /api/submit] {data.get('email')} | cohort={data.get('cohort')} | items={item_names} | Rs.{total}")

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('cohort', ''),
            data.get('name', ''),
            data.get('email', ''),
            data.get('age', ''),
            data.get('city', ''),
            data.get('prayingFrequency', ''),
            data.get('taughtBy', ''),
            data.get('prayerSteps', ''),
            data.get('giftingHabits', ''),
            data.get('mustHaveItem', ''),
            data.get('religiousApproach', ''),
            data.get('primaryFeeling', ''),
            data.get('giftDecisionBasis', ''),
            data.get('giftBoxGap', ''),
            config['occasion'],
            config['deity'],
            item_names,
            total
        ]

        sheets_saved = False
        try:
            print("[POST /api/submit] connecting to Sheets...")
            client = get_sheets_client()
            sheet  = client.open_by_key(SPREADSHEET_ID).sheet1
            if not sheet.get_all_values():
                sheet.append_row(HEADERS)
                print("[POST /api/submit] header row created")
            sheet.append_row(row)
            sheets_saved = True
            print(f"[POST /api/submit] OK - row appended")
        except Exception as se:
            print(f"[POST /api/submit] Sheets ERROR: {se}")

        return jsonify({
            "success": True, "total": total, "sheetsSaved": sheets_saved,
            "message": "Thank you! Your gift box has been recorded." if sheets_saved
                       else "Saved locally — check your SPREADSHEET_ID if Sheets sync failed."
        })

    except Exception as e:
        print(f"[POST /api/submit] FATAL: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
