import os
import sqlite3
import json
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ============================================================
# ENVIRONMENT
# ============================================================

# Load .env only if it exists.
# Never commit your real .env file to GitHub.
if os.path.exists(".env"):
    load_dotenv()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

client = None

if GEMINI_API_KEY:
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

# Vercel uses serverless instances.
# /tmp is writable during the lifetime of an instance.
#
# Local:
#     database.db
#
# Vercel:
#     /tmp/odletter_database.db

if os.getenv("VERCEL") == "1":
    DB_FILE = "/tmp/odletter_database.db"
else:
    DB_FILE = os.getenv(
        "DB_FILE",
        "database.db"
    )


# ============================================================
# STUDENT ROSTER
# ============================================================

ROSTER = {
    "255229101": "ABDUL RASIK S",
    "255229102": "ABISHEIK RUBAN C",
    "255229103": "ABISREE M",
    "255229104": "AFREEN M",
    "255229105": "AGSCE JEBAL B",
    "255229106": "AJAY RAAM E A",
    "255229107": "AMALA BINISHA C",
    "255229108": "ARAVINTHAN G",
    "255229109": "ARUMUGAPERUMAL S",
    "255229110": "BALAJI G",
    "255229111": "BALAMURUGAN P",
    "255229112": "BHUVANESHWARAN D",
    "255229113": "CYRIL SYLVESTER D",
    "255229114": "DHARANI K",
    "255229115": "DIVYA SRI M",
    "255229116": "DIWAKARAN A",
    "255229117": "EMEMA V",
    "255229118": "GAURI S",
    "255229119": "JAGADESHWARAN K",
    "255229120": "JENCY G",
    "255229121": "JENIFER JENITHA A",
    "255229122": "JERLIN G",
    "255229123": "JHONES J",
    "255229124": "JOEL A",
    "255229125": "KABIL B",
    "255229126": "KEERTHAN G",
    "255229127": "KEVIN LAZARUS B",
    "255229128": "KIRUTHIKA S",
    "255229129": "LAKSHITHAL",
    "255229130": "MAHALAKSHMI S",
    "255229131": "MANOVISHNU A V",
    "255229132": "NALAN S",
    "255229133": "NANDHINI R",
    "255229134": "NAVEENKUMAR C",
    "255229135": "NIDHEESH S",
    "255229136": "NIRMAL G",
    "255229137": "PRASANTH M",
    "255229138": "PRAVIN V",
    "255229139": "PREM SELVAN R",
    "255229140": "PRICILLA C",
    "255229141": "PRIYA THARSHINI R",
    "255229142": "RAJA VIGNESH P",
    "255229143": "RAJAKUMAR AZARIAH S",
    "255229144": "RITHIKA M",
    "255229145": "SARAN B",
    "255229146": "SARMILA BANU A",
    "255229147": "SELVAKUMAR K",
    "255229148": "SIVAGAMI A",
    "255229149": "SIVAKUMAR E",
    "255229150": "SRIRAM M",
    "255229151": "STANLEY WILSON M",
    "255229152": "SUSMITHA M",
    "255229153": "SWATHI S",
    "255229154": "THANUSIYA R",
    "255229155": "THIRUMALAI RAJAN S",
    "255229156": "THIRUPUGAZH M",
    "255229157": "VIJAY V S",
    "255229158": "YOGALAKSHMI K",
    "255229159": "JAYA VARSHINI I",
    "255229161": "KEERTHANA SIRJA S",
    "255229162": "SHARAN KUMAR",
    "255229163": "LOKESH",
}


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    """Create and seed the student database."""

    db_path = Path(DB_FILE)

    # Create parent directory if necessary.
    if db_path.parent and str(db_path.parent) != ".":
        db_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    conn = sqlite3.connect(DB_FILE)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                reg_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                year TEXT DEFAULT 'II',
                section TEXT DEFAULT 'A'
            )
            """
        )

        for reg_no, name in ROSTER.items():
            cursor.execute(
                """
                INSERT OR REPLACE INTO students
                (reg_no, name, year, section)
                VALUES (?, ?, ?, ?)
                """,
                (
                    reg_no,
                    name,
                    "II",
                    "A"
                )
            )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# INITIALIZE DATABASE
# ============================================================

# This is intentionally outside a route so Vercel initializes
# the database when it imports app.py.

try:
    init_db()
except Exception as e:
    print(
        f"Database initialization warning: {e}"
    )


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():

    try:
        conn = sqlite3.connect(DB_FILE)

        conn.row_factory = sqlite3.Row

        students = conn.execute(
            """
            SELECT
                reg_no,
                name,
                year,
                section
            FROM students
            ORDER BY reg_no ASC
            """
        ).fetchall()

        conn.close()

        return render_template(
            "index.html",
            students=students
        )

    except Exception as e:

        return (
            f"Database error while loading students: {e}",
            500
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify(
        {
            "status": "ok",
            "service": "OD Letter Generator",
            "gemini_configured": bool(
                GEMINI_API_KEY
            ),
            "gemini_model": GEMINI_MODEL
        }
    ), 200


# ============================================================
# GET STUDENTS API
# ============================================================

@app.route(
    "/api/students",
    methods=["GET"]
)
def get_students():

    try:

        conn = sqlite3.connect(DB_FILE)

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                reg_no,
                name,
                year,
                section
            FROM students
            ORDER BY reg_no ASC
            """
        ).fetchall()

        conn.close()

        students = [
            dict(row)
            for row in rows
        ]

        return jsonify(
            {
                "success": True,
                "students": students
            }
        ), 200

    except Exception as e:

        return jsonify(
            {
                "success": False,
                "error": (
                    "Unable to load students: "
                    + str(e)
                )
            }
        ), 500


# ============================================================
# BROCHURE / INVITATION PARSER
# ============================================================

@app.route(
    "/api/parse-brochure",
    methods=["POST"]
)
def parse_brochure():

    # --------------------------------------------------------
    # CHECK FILE
    # --------------------------------------------------------

    if "file" not in request.files:

        return jsonify(
            {
                "success": False,
                "error": "No file uploaded."
            }
        ), 400

    file = request.files["file"]

    if not file or file.filename == "":

        return jsonify(
            {
                "success": False,
                "error": (
                    "The uploaded file has "
                    "no filename."
                )
            }
        ), 400

    # --------------------------------------------------------
    # CHECK GEMINI
    # --------------------------------------------------------

    if client is None:

        return jsonify(
            {
                "success": False,
                "error": (
                    "GEMINI_API_KEY is not configured "
                    "on the server. Add GEMINI_API_KEY "
                    "to Vercel Environment Variables "
                    "and redeploy."
                )
            }
        ), 500

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    try:

        file_bytes = file.read()

        if not file_bytes:

            return jsonify(
                {
                    "success": False,
                    "error": "The uploaded file is empty."
                }
            ), 400

        mime_type = (
            file.content_type
            or "application/pdf"
        )

        # ----------------------------------------------------
        # GEMINI EXTRACTION PROMPT
        # ----------------------------------------------------

        prompt = """
You are an event-document information extraction system.

Extract ONLY information that is actually present in the
uploaded invitation, brochure, circular, notice, workshop
document, or event document.

Return ONLY valid JSON.

Use exactly these keys:

{
  "event_name": "",
  "organizer": "",
  "from_date": "",
  "to_date": "",
  "place": ""
}

Rules:

1. event_name:
   Extract the official event, workshop, seminar, conference,
   program, or activity name.

2. organizer:
   Extract the organizing institution, department, club,
   organization, company, committee, or association.

3. from_date:
   Extract the starting date.
   Return YYYY-MM-DD.
   If unavailable, return "".

4. to_date:
   Extract the ending date.
   Return YYYY-MM-DD.
   If the event is a single-day event, use the same date
   as from_date.
   If unavailable, return "".

5. place:
   Extract the actual venue/location.

6. Do NOT invent information.

7. Do NOT guess missing information.

8. If a value cannot be determined reliably, return "".

9. Return JSON only.

10. Do not return Markdown.

11. Do not include explanations.
"""

        # ----------------------------------------------------
        # CALL GEMINI
        # ----------------------------------------------------

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type
                ),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        extracted_text = (
            response.text or ""
        ).strip()

        if not extracted_text:

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini returned an empty "
                        "extraction result."
                    )
                }
            ), 502

        # ----------------------------------------------------
        # PARSE JSON
        # ----------------------------------------------------

        try:

            extracted_data = json.loads(
                extracted_text
            )

        except json.JSONDecodeError:

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini returned invalid JSON."
                    )
                }
            ), 502

        # ----------------------------------------------------
        # NORMALIZE RESPONSE
        # ----------------------------------------------------

        result = {
            "event_name": str(
                extracted_data.get(
                    "event_name",
                    ""
                ) or ""
            ).strip(),

            "organizer": str(
                extracted_data.get(
                    "organizer",
                    ""
                ) or ""
            ).strip(),

            "from_date": str(
                extracted_data.get(
                    "from_date",
                    ""
                ) or ""
            ).strip(),

            "to_date": str(
                extracted_data.get(
                    "to_date",
                    ""
                ) or ""
            ).strip(),

            "place": str(
                extracted_data.get(
                    "place",
                    ""
                ) or ""
            ).strip()
        }

        return jsonify(
            {
                "success": True,
                "data": result
            }
        ), 200

    # --------------------------------------------------------
    # ERROR HANDLING
    # --------------------------------------------------------

    except Exception as e:

        print(
            f"Brochure extraction error: {e}"
        )

        return jsonify(
            {
                "success": False,
                "error": (
                    "Brochure extraction failed: "
                    + str(e)
                )
            }
        ), 500


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),
        debug=True
    )
