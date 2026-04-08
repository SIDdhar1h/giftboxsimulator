# 🎁 MangalDeep – Gift Box WTP Tool

A gamified "Make Your Own Gift Box" experience to test willingness to pay across religious/festive contexts.

---

## 📁 Project Structure

```
giftbox/
├── app.py              ← Flask backend
├── config.json         ← 🔁 SWAP THIS to change theme
├── requirements.txt
├── frontend/
│   └── index.html      ← Single-page frontend
└── README.md
```

---

## ⚡ Quick Start (Local)

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Set your Google Sheet ID**

Open `app.py` and set:
```python
SPREADSHEET_ID = "your_google_sheet_id_here"
```

> The Sheet ID is in the URL: `https://docs.google.com/spreadsheets/d/THIS_PART/edit`

**3. Run**
```bash
python app.py
```

Open `http://localhost:5000` in your browser.

---

## 🔁 Changing Theme / Occasion

Edit **`config.json`** only. No code changes needed.

```json
{
  "occasion": "Diwali",
  "deity": "Goddess Lakshmi",
  "themeColor": "#C8522A",
  "accentColor": "#F5A623",
  "items": [
    {
      "id": "item_1",
      "name": "Lotus Flowers",
      "image": "https://...",
      "price": 80,
      "emoji": "🌸"
    }
  ]
}
```

✅ Prices are **never sent to the frontend** — calculated server-side only.

---

## 📊 Google Sheets Schema

Headers auto-created on first submission:

| Timestamp | Name | Email | Age | Praying Frequency | Gifting Habits | Occasion | Deity | Selected Items | Total Price (₹) |

---

## 🌐 Deploying to GitHub Pages (Frontend Only)

For a static demo (without backend), you can host `frontend/index.html` on GitHub Pages and point the API to a cloud backend (Railway, Render, etc.).

For full stack, deploy `app.py` to **Railway** or **Render** (both free tier):
1. Push to GitHub
2. Connect repo on Railway/Render
3. Set `SPREADSHEET_ID` as an environment variable
4. Deploy — done ✅

---

## 🔐 Security Notes

- Service account credentials are in `app.py` (backend only, never sent to browser)
- For production, move credentials to environment variables
