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
# PATH / ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

ENV_FILE = BASE_DIR / ".env"
STUDENTS_FILE = BASE_DIR / "students.csv"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


# ============================================================
# GEMINI SDK
# ============================================================

try:
    from google import genai
    from google.genai import types

    GEMINI_SDK_AVAILABLE = True

except ImportError:
    genai = None
    types = None
    GEMINI_SDK_AVAILABLE = False


# ============================================================
# REPORTLAB
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash",
).strip()

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "odletter-development-secret",
)


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

app.secret_key = SECRET_KEY

# Maximum uploaded file = 15 MB
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


# ============================================================
# GEMINI CLIENT
# ============================================================

client = None


def initialize_gemini():
    """
    Initialize the Gemini Developer API client.

    Uses GEMINI_API_KEY from:
        - local .env
        - Vercel Environment Variables
    """

    global client

    client = None

    if not GEMINI_API_KEY:
        print("Gemini: API key not configured.")
        return

    if not GEMINI_SDK_AVAILABLE:
        print(
            "Gemini: google-genai package is not installed."
        )
        return

    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print(
            f"Gemini client initialized. "
            f"Model: {GEMINI_MODEL}"
        )

    except Exception as exc:
        print(
            "Gemini client initialization failed:"
        )
        print(exc)

        client = None


initialize_gemini()


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    """
    Convert a value safely into trimmed text.
    """

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# STUDENT CSV
# ============================================================

def get_students():
    """
    Load students from students.csv.

    Required columns:

        reg_no
        name
        year
        section

    Optional:

        email
        phone
    """

    students = []

    if not STUDENTS_FILE.exists():

        print(
            f"Student CSV not found: {STUDENTS_FILE}"
        )

        return students

    try:

        with open(
            STUDENTS_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not reader.fieldnames:

                print(
                    "Student CSV has no header."
                )

                return students

            # ------------------------------------------------
            # Normalize headers
            # ------------------------------------------------

            headers = [
                clean_text(header).lower()
                for header in reader.fieldnames
            ]

            print(
                "Student CSV columns:",
                headers,
            )

            required_columns = {
                "reg_no",
                "name",
                "year",
                "section",
            }

            missing_columns = (
                required_columns
                - set(headers)
            )

            if missing_columns:

                print(
                    "Missing CSV columns:",
                    sorted(missing_columns),
                )

                return students

            # ------------------------------------------------
            # Read rows
            # ------------------------------------------------

            for row in reader:

                normalized = {}

                for key, value in row.items():

                    if key is None:
                        continue

                    normalized[
                        clean_text(key).lower()
                    ] = clean_text(value)

                reg_no = clean_text(
                    normalized.get("reg_no")
                )

                name = clean_text(
                    normalized.get("name")
                )

                year = clean_text(
                    normalized.get("year")
                )

                section = clean_text(
                    normalized.get("section")
                )

                # Skip completely empty rows
                if not reg_no and not name:
                    continue

                students.append(
                    {
                        "id": reg_no,
                        "reg_no": reg_no,
                        "register_number": reg_no,
                        "name": name,
                        "year": year,
                        "section": section,
                        "email": clean_text(
                            normalized.get("email")
                        ),
                        "phone": clean_text(
                            normalized.get("phone")
                        ),
                    }
                )

        # ----------------------------------------------------
        # Alphabetical sorting
        # ----------------------------------------------------

        students.sort(
            key=lambda item: (
                item.get("name", "").lower()
            )
        )

        print(
            f"Loaded {len(students)} students from CSV."
        )

        return students

    except Exception as exc:

        print(
            f"Student CSV error: {exc}"
        )

        return []


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def index():

    students = get_students()

    return render_template(
        "index.html",
        students=students,
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():

    students = get_students()

    return jsonify(
        {
            "success": True,
            "service": "OD Letter Generator",
            "gemini_configured": bool(client),
            "gemini_sdk_available": GEMINI_SDK_AVAILABLE,
            "gemini_model": GEMINI_MODEL,
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
# DATE NORMALIZATION
# ============================================================

def normalize_date(value):
    """
    Convert common date formats into DD/MM/YYYY.
    """

    value = clean_text(value)

    if not value:
        return ""

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
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


# ============================================================
# EVENT DATE SENTENCE
# ============================================================

def event_date_sentence(
    from_date,
    to_date,
):
    """
    Same day:

        on 12/09/2026

    Multiple days:

        from 12/09/2026 to 14/09/2026
    """

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
# JSON EXTRACTION
# ============================================================

def extract_json_from_text(text):

    text = clean_text(text)

    if not text:
        return {}

    # --------------------------------------------------------
    # Remove Markdown fences
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Direct JSON
    # --------------------------------------------------------

    try:

        result = json.loads(text)

        if isinstance(result, dict):
            return result

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # JSON embedded in text
    # --------------------------------------------------------

    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL,
    )

    if match:

        try:

            result = json.loads(
                match.group(0)
            )

            if isinstance(result, dict):
                return result

        except json.JSONDecodeError:
            pass

    return {}


# ============================================================
# GEMINI EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = """
You are an event-information extraction system.

Read the uploaded invitation, brochure, circular,
notice, workshop document, seminar document,
conference document, or event document.

Extract ONLY information explicitly present in the document.

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
   Extract the exact event, workshop, seminar,
   conference, symposium, competition, or program name.

2. organizer:
   Extract the institution, department,
   organization, company, club, or other organizer.

3. from_date:
   Extract the starting date.

4. to_date:
   Extract the ending date.

5. If the event is only one day:
   from_date and to_date must contain the same date.

6. place:
   Extract the venue/location.

7. Never invent missing information.

8. If information is unavailable,
   return an empty string.

9. Prefer YYYY-MM-DD for dates.

10. Return JSON only.
"""


# ============================================================
# FILE VALIDATION
# ============================================================

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def get_file_extension(filename):

    filename = clean_text(filename)

    if "." not in filename:
        return ""

    return Path(filename).suffix.lower()


# ============================================================
# BROCHURE PARSER
# ============================================================

@app.route(
    "/api/parse-brochure",
    methods=["POST"],
)
def parse_brochure():

    # --------------------------------------------------------
    # File exists?
    # --------------------------------------------------------

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
                "error": (
                    "Uploaded file has no filename."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # Extension
    # --------------------------------------------------------

    extension = get_file_extension(
        uploaded_file.filename
    )

    if extension not in ALLOWED_EXTENSIONS:

        return jsonify(
            {
                "success": False,
                "error": (
                    "Unsupported file type. "
                    "Upload PDF, PNG, JPG, JPEG "
                    "or WEBP."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # Gemini available?
    # --------------------------------------------------------

    if client is None:

        return jsonify(
            {
                "success": False,
                "error": (
                    "Gemini is not available. "
                    "Check GEMINI_API_KEY and "
                    "google-genai installation."
                ),
            }
        ), 503

    try:

        # ----------------------------------------------------
        # Read file
        # ----------------------------------------------------

        file_bytes = uploaded_file.read()

        if not file_bytes:

            return jsonify(
                {
                    "success": False,
                    "error": "Uploaded file is empty.",
                }
            ), 400

        # ----------------------------------------------------
        # MIME
        # ----------------------------------------------------

        mime_type = (
            uploaded_file.mimetype
            or "application/octet-stream"
        )

        # ----------------------------------------------------
        # Create Gemini binary part
        # ----------------------------------------------------

        if types is None:

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini SDK types are unavailable. "
                        "Run: pip install -U google-genai"
                    ),
                }
            ), 503

        file_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type,
        )

        # ----------------------------------------------------
        # Send to Gemini
        # ----------------------------------------------------

        print(
            "--------------------------------------------"
        )

        print(
            "Gemini brochure extraction started."
        )

        print(
            f"File  : {uploaded_file.filename}"
        )

        print(
            f"Type  : {mime_type}"
        )

        print(
            f"Size  : {len(file_bytes)} bytes"
        )

        print(
            f"Model : {GEMINI_MODEL}"
        )

        print(
            "--------------------------------------------"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                EXTRACTION_PROMPT,
                file_part,
            ],
        )

        # ----------------------------------------------------
        # Get response text
        # ----------------------------------------------------

        response_text = getattr(
            response,
            "text",
            "",
        )

        if not response_text:

            print(
                "Gemini returned empty response."
            )

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini returned an empty response."
                    ),
                }
            ), 502

        # ----------------------------------------------------
        # Extract JSON
        # ----------------------------------------------------

        extracted = extract_json_from_text(
            response_text
        )

        if not extracted:

            print(
                "Gemini returned invalid JSON."
            )

            print(
                response_text
            )

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini could not extract "
                        "structured event details."
                    ),
                }
            ), 502

        # ----------------------------------------------------
        # Normalize output
        # ----------------------------------------------------

        result = {
            "event_name": clean_text(
                extracted.get(
                    "event_name",
                    "",
                )
            ),
            "organizer": clean_text(
                extracted.get(
                    "organizer",
                    "",
                )
            ),
            "from_date": clean_text(
                extracted.get(
                    "from_date",
                    "",
                )
            ),
            "to_date": clean_text(
                extracted.get(
                    "to_date",
                    "",
                )
            ),
            "place": clean_text(
                extracted.get(
                    "place",
                    "",
                )
            ),
        }

        # ----------------------------------------------------
        # One-day event
        # ----------------------------------------------------

        if (
            result["from_date"]
            and not result["to_date"]
        ):

            result["to_date"] = (
                result["from_date"]
            )

        # ----------------------------------------------------
        # Normalize dates
        # ----------------------------------------------------

        if result["from_date"]:

            result["from_date"] = normalize_date(
                result["from_date"]
            )

        if result["to_date"]:

            result["to_date"] = normalize_date(
                result["to_date"]
            )

        print(
            "Gemini extracted:",
            result,
        )

        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )

    except Exception as exc:

        error_text = str(exc)

        print(
            "--------------------------------------------"
        )

        print(
            "Gemini extraction error:"
        )

        print(error_text)

        print(
            "--------------------------------------------"
        )

        # ----------------------------------------------------
        # Authentication failure
        # ----------------------------------------------------

        authentication_error = (
            "401" in error_text
            or "UNAUTHENTICATED"
            in error_text.upper()
            or "ACCESS_TOKEN_TYPE_UNSUPPORTED"
            in error_text
            or "INVALID_ARGUMENT"
            in error_text.upper()
        )

        if authentication_error:

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini authentication failed. "
                        "Create a fresh Gemini API key "
                        "in Google AI Studio and set it "
                        "as GEMINI_API_KEY. "
                        "Do not use a Vertex AI OAuth token."
                    ),
                }
            ), 502

        # ----------------------------------------------------
        # Permission failure
        # ----------------------------------------------------

        if (
            "403" in error_text
            or "PERMISSION_DENIED"
            in error_text.upper()
        ):

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini permission denied. "
                        "Check the API key and Gemini API "
                        "access for the Google project."
                    ),
                }
            ), 502

        # ----------------------------------------------------
        # Rate limit
        # ----------------------------------------------------

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED"
            in error_text.upper()
        ):

            return jsonify(
                {
                    "success": False,
                    "error": (
                        "Gemini rate limit or quota "
                        "was exceeded. Try again later."
                    ),
                }
            ), 429

        # ----------------------------------------------------
        # Generic failure
        # ----------------------------------------------------

        return jsonify(
            {
                "success": False,
                "error": (
                    "Unable to extract event details. "
                    "Check the uploaded document and "
                    "Gemini configuration."
                ),
            }
        ), 500


# ============================================================
# PDF GENERATION
# ============================================================

@app.route(
    "/api/generate-pdf",
    methods=["POST"],
)
def generate_pdf():

    # --------------------------------------------------------
    # ReportLab
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    ) or {}

    # --------------------------------------------------------
    # Fields
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Kevin special rule
    # --------------------------------------------------------

    if from_name.lower() == "kevin lazarus b":

        designation = (
            designation
            or "Technical Head"
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
        [],
    )

    if not isinstance(
        selected_students,
        list,
    ):

        selected_students = []

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

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
                "error": (
                    "Select at least one student."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # Date sentence
    # --------------------------------------------------------

    date_sentence = event_date_sentence(
        from_date,
        to_date,
    )

    # ========================================================
    # PDF DOCUMENT
    # ========================================================

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

    # --------------------------------------------------------
    # Styles
    # --------------------------------------------------------

    title_style = ParagraphStyle(
        "ODTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=15,
        leading=20,
        spaceAfter=10,
    )

    department_style = ParagraphStyle(
        "ODDepartment",
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

    # --------------------------------------------------------
    # Story
    # --------------------------------------------------------

    story = []

    # ========================================================
    # HEADER
    # ========================================================

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

    # ========================================================
    # FROM
    # ========================================================

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

    # ========================================================
    # TO
    # ========================================================

    story.append(
        Paragraph(
            "<b>To</b><br/>"
            "The Head of the Department<br/>"
            f"{department}<br/>"
            f"{college}",
            body_style,
        )
    )

    # ========================================================
    # SUBJECT
    # ========================================================

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

    story.append(
        Spacer(
            1,
            4,
        )
    )

    # ========================================================
    # EVENT DETAILS
    # ========================================================

    event_details = []

    if event_name:

        event_details.append(
            [
                "Event",
                event_name,
            ]
        )

    if organizer:

        event_details.append(
            [
                "Organizer",
                organizer,
            ]
        )

    if place:

        event_details.append(
            [
                "Venue",
                place,
            ]
        )

    if from_date:

        normalized_from = normalize_date(
            from_date
        )

        normalized_to = normalize_date(
            to_date
        )

        if (
            normalized_to
            and normalized_from
            != normalized_to
        ):

            display_date = (
                f"{normalized_from} "
                f"to {normalized_to}"
            )

        else:

            display_date = normalized_from

        event_details.append(
            [
                "Date",
                display_date,
            ]
        )

    if event_details:

        event_table = Table(
            event_details,
            colWidths=[
                32 * mm,
                115 * mm,
            ],
        )

        event_table.setStyle(
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

        story.append(
            event_table
        )

        story.append(
            Spacer(
                1,
                12,
            )
        )

    # ========================================================
    # STUDENTS
    # ========================================================

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

        if isinstance(
            student,
            dict,
        ):

            student_name = clean_text(
                student.get("name")
            )

            register_number = clean_text(
                student.get(
                    "register_number"
                )
                or student.get(
                    "reg_no"
                )
                or student.get(
                    "registerNumber"
                )
                or student.get(
                    "id"
                )
            )

        else:

            student_name = clean_text(
                student
            )

            register_number = ""

        # Do not add completely empty student
        if not student_name and not register_number:
            continue

        student_rows.append(
            [
                str(index),
                student_name,
                register_number,
            ]
        )

    if len(student_rows) == 1:

        return jsonify(
            {
                "success": False,
                "error": (
                    "Selected student information "
                    "is empty."
                ),
            }
        ), 400

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

    story.append(
        student_table
    )

    story.append(
        Spacer(
            1,
            15,
        )
    )

    # ========================================================
    # REQUEST PARAGRAPH
    # ========================================================

    request_text = (
        "I kindly request that the "
        "above-mentioned student(s) "
        "be permitted to attend "
        f"<b>{event_name}</b> "
        f"{date_sentence}"
    )

    if place:

        request_text += (
            f" at <b>{place}</b>"
        )

    if organizer:

        request_text += (
            f", organized by "
            f"<b>{organizer}</b>"
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

    # ========================================================
    # SIGNATURE
    # ========================================================

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

    # ========================================================
    # BUILD
    # ========================================================

    document.build(
        story
    )

    pdf_buffer.seek(0)

    # ========================================================
    # SAFE FILENAME
    # ========================================================

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

    print(
        "Internal server error:",
        error,
    )

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

    print()
    print(
        "============================================"
    )
    print(
        "       OD LETTER GENERATOR"
    )
    print(
        "============================================"
    )

    print(
        f"Students CSV : {STUDENTS_FILE}"
    )

    print(
        "CSV exists   :",
        STUDENTS_FILE.exists(),
    )

    students = get_students()

    print(
        f"Students     : {len(students)}"
    )

    print(
        "Gemini SDK   :",
        (
            "Available"
            if GEMINI_SDK_AVAILABLE
            else "Missing"
        ),
    )

    print(
        "Gemini       :",
        (
            "Configured"
            if client
            else "Not configured"
        ),
    )

    print(
        "Gemini model :",
        GEMINI_MODEL,
    )

    print(
        "ReportLab    :",
        (
            "Available"
            if REPORTLAB_AVAILABLE
            else "Missing"
        ),
    )

    print(
        "============================================"
    )

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
