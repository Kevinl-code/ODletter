import os
import io
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)
from dotenv import load_dotenv

# Optional Gemini SDK
try:
    from google import genai
except ImportError:
    genai = None

# Optional PDF library
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib import colors

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Load .env only when it exists.
# On Vercel, environment variables should be configured
# through Vercel Project Settings.
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

DATABASE_PATH = BASE_DIR / "database.db"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "odletter-development-secret"
)


# ============================================================
# FLASK APP
# ============================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


# ============================================================
# GEMINI CLIENT
# ============================================================

client = None

if GEMINI_API_KEY and genai is not None:
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )
    except Exception as exc:
        print(f"Gemini client initialization failed: {exc}")
        client = None


# ============================================================
# DATABASE
# ============================================================

DEFAULT_STUDENTS = [
    ("Student One", "DS001", "I M.Sc", "A", "", ""),
    ("Student Two", "DS002", "I M.Sc", "A", "", ""),
    ("Student Three", "DS003", "II M.Sc", "B", "", ""),
]


def get_db():
    """
    Open a SQLite connection.
    """
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    """
    Create the students table if it does not exist.
    """

    try:
        connection = get_db()

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                register_number TEXT UNIQUE NOT NULL,
                year TEXT,
                section TEXT,
                email TEXT,
                phone TEXT
            )
            """
        )

        existing = connection.execute(
            "SELECT COUNT(*) AS count FROM students"
        ).fetchone()

        if existing["count"] == 0:
            connection.executemany(
                """
                INSERT INTO students
                (
                    name,
                    register_number,
                    year,
                    section,
                    email,
                    phone
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                DEFAULT_STUDENTS,
            )

        connection.commit()
        connection.close()

    except Exception as exc:
        print(f"Database initialization warning: {exc}")


# Initialize when the module is imported by Vercel.
init_db()


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    """
    Safely convert a value to a trimmed string.
    """
    if value is None:
        return ""

    return str(value).strip()


def normalize_date(value):
    """
    Convert common date formats to DD/MM/YYYY.

    Accepted examples:
        2026-09-12
        12/09/2026
        12-09-2026
    """

    value = clean_text(value)

    if not value:
        return ""

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue

    return value


def event_date_sentence(from_date, to_date):
    """
    Produce deterministic wording for the OD letter.
    """

    from_date = normalize_date(from_date)
    to_date = normalize_date(to_date)

    if not from_date:
        return "on the specified date"

    if not to_date or from_date == to_date:
        return f"on {from_date}"

    return f"from {from_date} to {to_date}"


def extract_json_from_text(text):
    """
    Gemini occasionally returns JSON surrounded by markdown.
    Extract the JSON object safely.
    """

    text = clean_text(text)

    if not text:
        return {}

    # Remove markdown code fences.
    text = re.sub(
        r"```json\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"```\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.strip()

    # Import json only here.
    import json

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to locate the first JSON object.
    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL,
    )

    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def get_students_from_database():
    """
    Return all students as dictionaries.
    """

    try:
        connection = get_db()

        rows = connection.execute(
            """
            SELECT
                id,
                name,
                register_number,
                year,
                section,
                email,
                phone
            FROM students
            ORDER BY name ASC
            """
        ).fetchall()

        connection.close()

        return [
            dict(row)
            for row in rows
        ]

    except Exception as exc:
        print(f"Student database error: {exc}")
        return []


# ============================================================
# PAGE ROUTE
# ============================================================

@app.route("/", methods=["GET"])
def index():
    """
    Render the main OD Letter Generator page.
    """

    students = get_students_from_database()

    return render_template(
        "index.html",
        students=students,
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    """
    Simple deployment health endpoint.
    """

    return jsonify(
        {
            "success": True,
            "service": "OD Letter Generator",
            "gemini_configured": bool(client),
            "reportlab_available": REPORTLAB_AVAILABLE,
        }
    )


# ============================================================
# STUDENT API
# ============================================================

@app.route("/api/students", methods=["GET"])
def students_api():
    """
    Return all students.
    """

    students = get_students_from_database()

    return jsonify(
        {
            "success": True,
            "students": students,
            "count": len(students),
        }
    )


# ============================================================
# ADD STUDENT
# ============================================================

@app.route("/api/students", methods=["POST"])
def add_student():
    """
    Add one student.
    """

    data = request.get_json(silent=True) or {}

    name = clean_text(data.get("name"))
    register_number = clean_text(
        data.get("register_number")
        or data.get("registerNumber")
    )
    year = clean_text(data.get("year"))
    section = clean_text(data.get("section"))
    email = clean_text(data.get("email"))
    phone = clean_text(data.get("phone"))

    if not name or not register_number:
        return jsonify(
            {
                "success": False,
                "error": "Name and register number are required.",
            }
        ), 400

    try:
        connection = get_db()

        cursor = connection.execute(
            """
            INSERT INTO students
            (
                name,
                register_number,
                year,
                section,
                email,
                phone
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                register_number,
                year,
                section,
                email,
                phone,
            ),
        )

        connection.commit()

        student_id = cursor.lastrowid

        connection.close()

        return jsonify(
            {
                "success": True,
                "message": "Student added successfully.",
                "id": student_id,
            }
        )

    except sqlite3.IntegrityError:
        return jsonify(
            {
                "success": False,
                "error": "Register number already exists.",
            }
        ), 409

    except Exception as exc:
        print(f"Add student error: {exc}")

        return jsonify(
            {
                "success": False,
                "error": "Unable to add student.",
            }
        ), 500


# ============================================================
# BROCHURE / INVITATION EXTRACTION
# ============================================================

@app.route("/api/parse-brochure", methods=["POST"])
def parse_brochure():
    """
    Extract event details from an uploaded brochure/invitation.

    Expected fields:
        event_name
        organizer
        from_date
        to_date
        place
    """

    if "file" not in request.files:
        return jsonify(
            {
                "success": False,
                "error": "No file was uploaded.",
            }
        ), 400

    uploaded_file = request.files["file"]

    if not uploaded_file.filename:
        return jsonify(
            {
                "success": False,
                "error": "Uploaded file has no filename.",
            }
        ), 400

    if client is None:
        return jsonify(
            {
                "success": False,
                "error": (
                    "Gemini is not configured. "
                    "Add GEMINI_API_KEY in Vercel Environment Variables."
                ),
            }
        ), 503

    try:
        file_bytes = uploaded_file.read()

        if not file_bytes:
            return jsonify(
                {
                    "success": False,
                    "error": "Uploaded file is empty.",
                }
            ), 400

        mime_type = (
            uploaded_file.mimetype
            or "application/pdf"
        )

        prompt = """
You are an event-information extraction system.

Extract ONLY information explicitly available in the
uploaded invitation, brochure, circular, or event document.

Return ONLY valid JSON.

Required JSON structure:

{
  "event_name": "",
  "organizer": "",
  "from_date": "",
  "to_date": "",
  "place": ""
}

Rules:

1. event_name:
   Exact or closest clear event/workshop/seminar name.

2. organizer:
   Institution, department, organization, club, company,
   or other organizer explicitly mentioned.

3. from_date:
   Event starting date.

4. to_date:
   Event ending date.
   If it is a one-day event, use the same date.

5. place:
   Venue/location where the event occurs.

6. Never invent missing information.

7. If a field cannot be determined, return an empty string.

8. Use dates in YYYY-MM-DD format whenever possible.
"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": file_bytes,
                            }
                        },
                    ],
                }
            ],
        )

        extracted = extract_json_from_text(
            getattr(response, "text", "")
        )

        result = {
            "event_name": clean_text(
                extracted.get("event_name")
            ),
            "organizer": clean_text(
                extracted.get("organizer")
            ),
            "from_date": clean_text(
                extracted.get("from_date")
            ),
            "to_date": clean_text(
                extracted.get("to_date")
            ),
            "place": clean_text(
                extracted.get("place")
            ),
        }

        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )

    except Exception as exc:
        print(f"Brochure extraction error: {exc}")

        return jsonify(
            {
                "success": False,
                "error": (
                    "Unable to extract event details. "
                    "Check the uploaded file and Gemini configuration."
                ),
            }
        ), 500


# ============================================================
# SERVER-SIDE PDF GENERATION
# ============================================================

@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf():
    """
    Generate an OD letter PDF on the server.

    This avoids relying on browser-side html2canvas/jsPDF.
    """

    if not REPORTLAB_AVAILABLE:
        return jsonify(
            {
                "success": False,
                "error": (
                    "ReportLab is not installed. "
                    "Add reportlab to requirements.txt."
                ),
            }
        ), 503

    data = request.get_json(silent=True) or {}

    event_name = clean_text(
        data.get("event_name")
    )

    organizer = clean_text(
        data.get("organizer")
    )

    from_date = clean_text(
        data.get("from_date")
    )

    to_date = clean_text(
        data.get("to_date")
    )

    place = clean_text(
        data.get("place")
    )

    from_name = clean_text(
        data.get("from_name")
        or "Kevin Lazarus B"
    )

    designation = clean_text(
        data.get("designation")
    )

    college = clean_text(
        data.get("college")
        or "Bishop Heber College"
    )

    department = clean_text(
        data.get("department")
        or "Department of Data Science"
    )

    selected_students = data.get(
        "students",
        []
    )

    if not isinstance(selected_students, list):
        selected_students = []

    if not event_name:
        return jsonify(
            {
                "success": False,
                "error": "Event name is required.",
            }
        ), 400

    if not selected_students:
        return jsonify(
            {
                "success": False,
                "error": "Select at least one student.",
            }
        ), 400

    date_sentence = event_date_sentence(
        from_date,
        to_date,
    )

    # --------------------------------------------------------
    # Build PDF in memory
    # --------------------------------------------------------

    pdf_buffer = io.BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="On-Duty Request Letter",
        author="OD Letter Generator",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ODTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=15,
        leading=20,
        spaceAfter=10,
    )

    body_style = ParagraphStyle(
        "ODBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=11,
        leading=18,
        spaceAfter=10,
    )

    small_style = ParagraphStyle(
        "ODSmall",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
    )

    story = []

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    story.append(
        Paragraph(
            f"<b>{college}</b>",
            title_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>{department}</b>",
            ParagraphStyle(
                "Dept",
                parent=title_style,
                fontSize=12,
                leading=16,
            ),
        )
    )

    story.append(
        Spacer(
            1,
            10,
        )
    )

    story.append(
        Paragraph(
            "<b>ON-DUTY REQUEST</b>",
            title_style,
        )
    )

    story.append(
        Spacer(
            1,
            8,
        )
    )

    # --------------------------------------------------------
    # From
    # --------------------------------------------------------

    from_block = (
        f"<b>From</b><br/>"
        f"{from_name}<br/>"
        f"{designation}"
    )

    story.append(
        Paragraph(
            from_block,
            body_style,
        )
    )

    story.append(
        Spacer(
            1,
            4,
        )
    )

    # --------------------------------------------------------
    # To
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "<b>To</b><br/>"
            "The Head of the Department<br/>"
            f"{department}<br/>"
            f"{college}",
            body_style,
        )
    )

    story.append(
        Spacer(
            1,
            6,
        )
    )

    # --------------------------------------------------------
    # Subject
    # --------------------------------------------------------

    subject = (
        f"<b>Subject:</b> Request for On-Duty permission "
        f"to attend {event_name}"
    )

    story.append(
        Paragraph(
            subject,
            body_style,
        )
    )

    story.append(
        Spacer(
            1,
            4,
        )
    )

    # --------------------------------------------------------
    # Event details
    # --------------------------------------------------------

    event_details = []

    if event_name:
        event_details.append(
            ["Event", event_name]
        )

    if organizer:
        event_details.append(
            ["Organizer", organizer]
        )

    if place:
        event_details.append(
            ["Venue", place]
        )

    if from_date:
        event_details.append(
            [
                "Date",
                date_sentence.replace(
                    "on ",
                    "",
                    1,
                ),
            ]
        )

    if event_details:
        table = Table(
            event_details,
            colWidths=[
                32 * mm,
                115 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (0, -1),
                        "Helvetica-Bold",
                    ),
                    (
                        "FONTNAME",
                        (1, 0),
                        (1, -1),
                        "Helvetica",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        9,
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        story.append(table)

        story.append(
            Spacer(
                1,
                12,
            )
        )

    # --------------------------------------------------------
    # Student table
    # --------------------------------------------------------

    student_rows = [
        [
            "S.No",
            "Student Name",
            "Register No.",
        ]
    ]

    for index, student in enumerate(
        selected_students,
        start=1,
    ):
        if isinstance(student, dict):
            student_name = clean_text(
                student.get("name")
            )

            register_number = clean_text(
                student.get("register_number")
                or student.get("registerNumber")
            )
        else:
            student_name = clean_text(student)
            register_number = ""

        student_rows.append(
            [
                str(index),
                student_name,
                register_number,
            ]
        )

    student_table = Table(
        student_rows,
        colWidths=[
            15 * mm,
            95 * mm,
            45 * mm,
        ],
        repeatRows=1,
    )

    student_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (0, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(student_table)

    story.append(
        Spacer(
            1,
            15,
        )
    )

    # --------------------------------------------------------
    # Request paragraph
    # --------------------------------------------------------

    request_text = (
        f"I kindly request that the above-mentioned student(s) "
        f"be permitted to attend <b>{event_name}</b> "
        f"{date_sentence}"
    )

    if place:
        request_text += (
            f" at <b>{place}</b>"
        )

    if organizer:
        request_text += (
            f", organized by <b>{organizer}</b>"
        )

    request_text += "."

    story.append(
        Paragraph(
            request_text,
            body_style,
        )
    )

    story.append(
        Spacer(
            1,
            25,
        )
    )

    # --------------------------------------------------------
    # Signature
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "Yours faithfully,",
            body_style,
        )
    )

    story.append(
        Spacer(
            1,
            18,
        )
    )

    story.append(
        Paragraph(
            (
                f"<b>{from_name}</b><br/>"
                f"{designation}"
            ),
            body_style,
        )
    )

    # --------------------------------------------------------
    # Build
    # --------------------------------------------------------

    document.build(story)

    pdf_buffer.seek(0)

    safe_event_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        event_name,
    ).strip("_")

    filename = (
        f"OD_Letter_{safe_event_name or 'Event'}.pdf"
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify(
        {
            "success": False,
            "error": "Route not found.",
        }
    ), 404


@app.errorhandler(413)
def file_too_large(error):
    return jsonify(
        {
            "success": False,
            "error": "Uploaded file is too large. Maximum size is 15 MB.",
        }
    ), 413


@app.errorhandler(500)
def internal_error(error):
    print(f"Internal server error: {error}")

    return jsonify(
        {
            "success": False,
            "error": "Internal server error.",
        }
    ), 500


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    print("--------------------------------------------")
    print("OD Letter Generator")
    print("--------------------------------------------")
    print(f"Database : {DATABASE_PATH}")
    print(f"Gemini   : {'Configured' if client else 'Not configured'}")
    print(f"ReportLab: {'Available' if REPORTLAB_AVAILABLE else 'Missing'}")
    print("--------------------------------------------")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
