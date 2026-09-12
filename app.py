import os
import io
import re
import csv
import json
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


# ============================================================
# OPTIONAL GEMINI SDK
# ============================================================

try:
    from google import genai
except ImportError:
    genai = None


# ============================================================
# OPTIONAL REPORTLAB
# ============================================================

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import (
        getSampleStyleSheet,
        ParagraphStyle,
    )
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

# IMPORTANT:
# students.csv must be in the ROOT of your GitHub repository.
STUDENTS_FILE = BASE_DIR / "students.csv"

# Local .env is optional.
# On Vercel, use Project Settings -> Environment Variables.
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "odletter-development-secret"
)

GEMINI_MODEL = "gemini-2.5-flash"

client = None

if GEMINI_API_KEY and genai is not None:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:
        print(f"Gemini client initialization failed: {exc}")
        client = None


# ============================================================
# FLASK APP
# ============================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

app.secret_key = SECRET_KEY

# Maximum uploaded file size = 15 MB
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


# ============================================================
# CSV STUDENT DATABASE
# ============================================================

def clean_text(value):
    """
    Safely convert a value to a trimmed string.
    """

    if value is None:
        return ""

    return str(value).strip()


def get_students():
    """
    Read students from students.csv.
    """

    students = []

    if not STUDENTS_FILE.exists():
        print(f"Student CSV not found: {STUDENTS_FILE}")
        return []

    try:
        with open(
            STUDENTS_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not reader.fieldnames:
                print("Student CSV has no header row.")
                return []

            # Normalize column names.
            fieldnames = [
                clean_text(field).lower()
                for field in reader.fieldnames
            ]

            required_columns = {
                "reg_no",
                "name",
                "year",
                "section",
            }

            missing_columns = (
                required_columns
                - set(fieldnames)
            )

            if missing_columns:
                print(
                    "Student CSV missing columns:",
                    sorted(missing_columns)
                )
                return []

            for row in reader:
                normalized_row = {}

                for key, value in row.items():
                    if key is None:
                        continue

                    normalized_key = (
                        clean_text(key).lower()
                    )

                    normalized_row[
                        normalized_key
                    ] = clean_text(value)

                reg_no = clean_text(
                    normalized_row.get("reg_no")
                )

                name = clean_text(
                    normalized_row.get("name")
                )

                year = clean_text(
                    normalized_row.get("year")
                )

                section = clean_text(
                    normalized_row.get("section")
                )

                if not reg_no and not name:
                    continue

                students.append(
                    {
                        "id": reg_no,
                        "register_number": reg_no,
                        "reg_no": reg_no,
                        "name": name,
                        "year": year,
                        "section": section,
                        "email": clean_text(
                            normalized_row.get("email")
                        ),
                        "phone": clean_text(
                            normalized_row.get("phone")
                        ),
                    }
                )

        students.sort(
            key=lambda student: (
                student["name"].lower()
            )
        )

        print(
            f"Loaded {len(students)} students from CSV."
        )

        return students

    except Exception as exc:
        print(f"Student CSV error: {exc}")
        return []


# ============================================================
# PAGE ROUTE
# ============================================================

@app.route("/", methods=["GET"])
def index():
    students = get_students()
    return render_template(
        "index.html",
        students=students,
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    students = get_students()
    return jsonify(
        {
            "success": True,
            "service": "OD Letter Generator",
            "gemini_configured": bool(client),
            "reportlab_available": REPORTLAB_AVAILABLE,
            "students_file_exists": STUDENTS_FILE.exists(),
            "student_count": len(students),
        }
    )


# ============================================================
# STUDENT API
# ============================================================

@app.route("/api/students", methods=["GET"])
def students_api():
    students = get_students()
    return jsonify(
        {
            "success": True,
            "students": students,
            "count": len(students),
        }
    )


# ============================================================
# DATE HELPERS
# ============================================================

def normalize_date(value):
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
            parsed = datetime.strptime(
                value,
                fmt,
            )
            return parsed.strftime(
                "%d/%m/%Y"
            )
        except ValueError:
            continue

    return value


def event_date_sentence(
    from_date,
    to_date,
):
    from_date = normalize_date(
        from_date
    )

    to_date = normalize_date(
        to_date
    )

    if not from_date:
        return "on the specified date"

    if (
        not to_date
        or from_date == to_date
    ):
        return f"on {from_date}"

    return (
        f"from {from_date} "
        f"to {to_date}"
    )


# ============================================================
# GEMINI JSON EXTRACTION
# ============================================================

def extract_json_from_text(text):
    text = clean_text(text)

    if not text:
        return {}

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

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL,
    )

    if match:
        try:
            return json.loads(
                match.group(0)
            )
        except json.JSONDecodeError:
            pass

    return {}


# ============================================================
# BROCHURE / INVITATION EXTRACTION
# ============================================================

@app.route(
    "/api/parse-brochure",
    methods=["POST"],
)
def parse_brochure():
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
                    "Add GEMINI_API_KEY in "
                    "Vercel Environment Variables."
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
uploaded invitation, brochure, circular, notice,
workshop document, seminar document, or event document.

Return ONLY valid JSON.

Required structure:

{
  "event_name": "",
  "organizer": "",
  "from_date": "",
  "to_date": "",
  "place": ""
}

Rules:

1. event_name:
   Extract the exact event/workshop/seminar/conference name.

2. organizer:
   Extract the institution, department, organization,
   company, club, or other organizer.

3. from_date:
   Extract the starting date.

4. to_date:
   Extract the ending date.

5. For a one-day event:
   from_date and to_date must contain the same date.

6. place:
   Extract the event venue/location.

7. Never invent information.

8. If a value is unavailable, return an empty string.

9. Prefer YYYY-MM-DD for dates.

10. Return JSON only.
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

        response_text = getattr(
            response,
            "text",
            "",
        )

        extracted = extract_json_from_text(
            response_text
        )

        result = {
            "event_name": clean_text(
                extracted.get("event_name", "")
            ),
            "organizer": clean_text(
                extracted.get("organizer", "")
            ),
            "from_date": clean_text(
                extracted.get("from_date", "")
            ),
            "to_date": clean_text(
                extracted.get("to_date", "")
            ),
            "place": clean_text(
                extracted.get("place", "")
            ),
        }

        if (
            result["from_date"]
            and not result["to_date"]
        ):
            result["to_date"] = (
                result["from_date"]
            )

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
                    "Check the uploaded file and "
                    "Gemini configuration."
                ),
            }
        ), 500


# ============================================================
# SERVER-SIDE PDF GENERATION
# ============================================================

@app.route(
    "/api/generate-pdf",
    methods=["POST"],
)
def generate_pdf():
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

    data = request.get_json(
        silent=True
    ) or {}

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

    department_style = ParagraphStyle(
        "Department",
        parent=title_style,
        fontSize=12,
        leading=16,
    )

    body_style = ParagraphStyle(
        "ODBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=11,
        leading=18,
        spaceAfter=10,
    )

    story = []

    story.append(
        Paragraph(
            f"<b>{college}</b>",
            title_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>{department}</b>",
            department_style,
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "<b>ON-DUTY REQUEST</b>",
            title_style,
        )
    )

    story.append(Spacer(1, 8))

    from_block = (
        "<b>From</b><br/>"
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
        Paragraph(
            "<b>To</b><br/>"
            "The Head of the Department<br/>"
            f"{department}<br/>"
            f"{college}",
            body_style,
        )
    )

    subject = (
        "<b>Subject:</b> Request for "
        "On-Duty permission to attend "
        f"{event_name}"
    )

    story.append(
        Paragraph(
            subject,
            body_style,
        )
    )

    story.append(Spacer(1, 4))

    event_details = []

    if event_name:
        event_details.append(["Event", event_name])

    if organizer:
        event_details.append(["Organizer", organizer])

    if place:
        event_details.append(["Venue", place])

    if from_date:
        display_date = (
            date_sentence
            .replace("on ", "", 1)
        )
        event_details.append(["Date", display_date])

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
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        story.append(table)
        story.append(Spacer(1, 12))

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
                or student.get("reg_no")
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
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(student_table)
    story.append(Spacer(1, 15))

    request_text = (
        "I kindly request that the "
        "above-mentioned student(s) "
        f"be permitted to attend "
        f"<b>{event_name}</b> "
        f"{date_sentence}"
    )

    if place:
        request_text += f" at <b>{place}</b>"

    if organizer:
        request_text += f", organized by <b>{organizer}</b>"

    request_text += "."

    story.append(
        Paragraph(
            request_text,
            body_style,
        )
    )

    story.append(Spacer(1, 25))

    story.append(
        Paragraph(
            "Yours faithfully,",
            body_style,
        )
    )

    story.append(Spacer(1, 18))

    story.append(
        Paragraph(
            (
                f"<b>{from_name}</b><br/>"
                f"{designation}"
            ),
            body_style,
        )
    )

    document.build(story)

    pdf_buffer.seek(0)

    safe_event_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        event_name,
    ).strip("_")

    filename = (
        "OD_Letter_"
        f"{safe_event_name or 'Event'}"
        ".pdf"
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
            "error": (
                "Uploaded file is too large. "
                "Maximum size is 15 MB."
            ),
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
    print(f"Students CSV : {STUDENTS_FILE}")
    print("Students CSV exists:", STUDENTS_FILE.exists())

    students = get_students()

    print(f"Students loaded: {len(students)}")
    print(
        f"Gemini       : "
        f"{'Configured' if client else 'Not configured'}"
    )
    print(
        f"ReportLab    : "
        f"{'Available' if REPORTLAB_AVAILABLE else 'Missing'}"
    )
    print("--------------------------------------------")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
