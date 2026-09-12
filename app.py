import os
import sqlite3
import json
from datetime import datetime

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

from google import genai
from google.genai import types


# ============================================================
# ENVIRONMENT
# ============================================================

# Load .env only when it exists.
# This works locally and does not crash on Vercel.
if os.path.exists(".env"):
    load_dotenv()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Do NOT create the Gemini client if the API key is missing.
# This prevents the entire Vercel deployment from crashing.
client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        client = None


# ============================================================
# DATABASE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Local development database.
DB_FILE = os.path.join(BASE_DIR, "database.db")


# ============================================================
# DEFAULT STUDENT ROSTER
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
# DATABASE FUNCTIONS
# ============================================================

def get_db_connection():
    """
    Create a SQLite connection.
    """
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """
    Create the students table and insert the default roster.
    """

    try:
        conn = get_db_connection()
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

        cursor.execute("SELECT COUNT(*) FROM students")
        count = cursor.fetchone()[0]

        if count == 0:
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
                        "A",
                    ),
                )

        conn.commit()
        conn.close()

        return True

    except Exception as exc:
        print("Database initialization warning:", exc)
        return False


def get_students():
    """
    Get students from SQLite.

    If SQLite is unavailable, return the built-in roster.
    This is useful for Vercel/serverless deployment.
    """

    try:
        init_db()

        conn = get_db_connection()

        rows = conn.execute(
            """
            SELECT reg_no, name, year, section
            FROM students
            ORDER BY reg_no ASC
            """
        ).fetchall()

        conn.close()

        if rows:
            return [
                {
                    "reg_no": row["reg_no"],
                    "name": row["name"],
                    "year": row["year"],
                    "section": row["section"],
                }
                for row in rows
            ]

    except Exception as exc:
        print("Student database warning:", exc)

    # Fallback roster
    return [
        {
            "reg_no": reg_no,
            "name": name,
            "year": "II",
            "section": "A",
        }
        for reg_no, name in sorted(ROSTER.items())
    ]


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/", methods=["GET"])
def index():
    """
    Render the OD Letter Generator.
    """

    students = get_students()

    return render_template(
        "index.html",
        students=students
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    """
    Simple deployment health check.
    """

    return jsonify(
        {
            "status": "ok",
            "service": "OD Letter Generator",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "gemini_configured": bool(GEMINI_API_KEY),
            "gemini_client_ready": client is not None,
        }
    ), 200


# ============================================================
# STUDENT API
# ============================================================

@app.route("/api/students", methods=["GET"])
def api_students():
    """
    Return all students as JSON.
    """

    students = get_students()

    return jsonify(
        {
            "success": True,
            "count": len(students),
            "students": students,
        }
    ), 200


# ============================================================
# GEMINI DOCUMENT EXTRACTION
# ============================================================

@app.route("/api/parse-brochure", methods=["POST"])
def parse_brochure():
    """
    Extract event information from an uploaded
    invitation, brochure, notice or PDF.
    """

    # --------------------------------------------------------
    # Check uploaded file
    # --------------------------------------------------------

    if "file" not in request.files:
        return jsonify(
            {
                "success": False,
                "error": "No file uploaded."
            }
        ), 400

    file = request.files["file"]

    if file is None:
        return jsonify(
            {
                "success": False,
                "error": "Invalid uploaded file."
            }
        ), 400

    if not file.filename:
        return jsonify(
            {
                "success": False,
                "error": "Empty filename."
            }
        ), 400

    # --------------------------------------------------------
    # Check Gemini
    # --------------------------------------------------------

    if client is None:
        return jsonify(
            {
                "success": False,
                "error": (
                    "Gemini API is not configured. "
                    "Add GEMINI_API_KEY to Vercel Environment Variables."
                )
            }
        ), 500

    # --------------------------------------------------------
    # Validate extension
    # --------------------------------------------------------

    filename = file.filename.lower()

    allowed_extensions = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }

    extension = os.path.splitext(filename)[1]

    if extension not in allowed_extensions:
        return jsonify(
            {
                "success": False,
                "error": (
                    "Unsupported file type. "
                    "Use PDF, PNG, JPG, JPEG or WEBP."
                )
            }
        ), 400

    # --------------------------------------------------------
    # Read file
    # --------------------------------------------------------

    try:
        file_bytes = file.read()

        if not file_bytes:
            return jsonify(
                {
                    "success": False,
                    "error": "Uploaded file is empty."
                }
            ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": f"Could not read uploaded file: {str(exc)}"
            }
        ), 400

    # --------------------------------------------------------
    # MIME type
    # --------------------------------------------------------

    mime_type = file.content_type

    if not mime_type:
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

        mime_type = mime_map.get(
            extension,
            "application/octet-stream"
        )

    # --------------------------------------------------------
    # Gemini extraction prompt
    # --------------------------------------------------------

    prompt = """
You are an event-information extraction system for a
college On-Duty (OD) Letter Generator.

Read the uploaded invitation, brochure, notice or event document.

Extract ONLY information that is actually present in the document.

Return ONLY valid JSON.

Use this exact schema:

{
    "event_name": "",
    "organizer": "",
    "from_date": "",
    "to_date": "",
    "place": "",
    "venue": "",
    "event_type": "",
    "description": ""
}

Rules:

1. event_name:
   Extract the official event/workshop/seminar/conference name.

2. organizer:
   Extract the organization, department, college, company,
   institution or group organizing the event.

3. from_date:
   Return the starting date in YYYY-MM-DD format.

4. to_date:
   Return the ending date in YYYY-MM-DD format.
   If the event is only one day, use the same date as from_date.

5. place:
   Extract the city/location if clearly available.

6. venue:
   Extract the specific venue/hall/auditorium/institution
   if available.

7. event_type:
   Examples:
   Event
   Workshop
   Seminar
   Conference
   Symposium
   Hackathon
   Competition
   FDP
   Training
   Other

8. description:
   Give a short factual description based only on the document.

9. Never invent missing information.

10. If a value is unavailable, return an empty string.

11. Dates must be YYYY-MM-DD.

12. Return valid JSON only.
"""

    # --------------------------------------------------------
    # Call Gemini
    # --------------------------------------------------------

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type,
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

    except Exception as exc:
        print("Gemini extraction error:", repr(exc))

        return jsonify(
            {
                "success": False,
                "error": (
                    "Gemini could not process the document. "
                    f"{str(exc)}"
                )
            }
        ), 500

    # --------------------------------------------------------
    # Read Gemini response
    # --------------------------------------------------------

    try:
        response_text = response.text

        if not response_text:
            return jsonify(
                {
                    "success": False,
                    "error": "Gemini returned an empty response."
                }
            ), 500

        # Remove accidental markdown code fences.
        cleaned = response_text.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]

        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        # Validate JSON before returning.
        extracted_data = json.loads(cleaned)

    except json.JSONDecodeError:
        print("Invalid Gemini JSON:", response_text)

        return jsonify(
            {
                "success": False,
                "error": "Gemini returned invalid JSON.",
                "raw_response": response_text,
            }
        ), 500

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": f"Could not read Gemini response: {str(exc)}"
            }
        ), 500

    # --------------------------------------------------------
    # Normalize expected fields
    # --------------------------------------------------------

    fields = [
        "event_name",
        "organizer",
        "from_date",
        "to_date",
        "place",
        "venue",
        "event_type",
        "description",
    ]

    normalized = {}

    for field in fields:
        value = extracted_data.get(field, "")

        if value is None:
            value = ""

        normalized[field] = str(value).strip()

    # If only from_date exists, use it as to_date.
    if normalized["from_date"] and not normalized["to_date"]:
        normalized["to_date"] = normalized["from_date"]

    # --------------------------------------------------------
    # Return successful response
    # --------------------------------------------------------

    return jsonify(
        {
            "success": True,
            "data": normalized,
        }
    ), 200


# ============================================================
# GLOBAL ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):
    return jsonify(
        {
            "success": False,
            "error": "File is too large. Maximum size is 15 MB."
        }
    ), 413


@app.errorhandler(404)
def not_found(error):
    return jsonify(
        {
            "success": False,
            "error": "Route not found."
        }
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify(
        {
            "success": False,
            "error": "Internal server error."
        }
    ), 500


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    init_db()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
