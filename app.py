import os
import sqlite3
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

DB_FILE = "database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            reg_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            year TEXT DEFAULT 'II',
            section TEXT DEFAULT 'A'
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM students")
    if cursor.fetchone()[0] == 0:
        roster = {
            "255229101": "ABDUL RASIK S", "255229102": "ABISHEIK RUBAN C", "255229103": "ABISREE M",
            "255229104": "AFREEN M", "255229105": "AGSCE JEBAL B", "255229106": "AJAY RAAM E A",
            "255229107": "AMALA BINISHA C", "255229108": "ARAVINTHAN G", "255229109": "ARUMUGAPERUMAL S",
            "255229110": "BALAJI G", "255229111": "BALAMURUGAN P", "255229112": "BHUVANESHWARAN D",
            "255229113": "CYRIL SYLVESTER D", "255229114": "DHARANI K", "255229115": "DIVYA SRI M",
            "255229116": "DIWAKARAN A", "255229117": "EMEMA V", "255229118": "GAURI S",
            "255229119": "JAGADESHWARAN K", "255229120": "JENCY G", "255229121": "JENIFER JENITHA A",
            "255229122": "JERLIN G", "255229123": "JHONES J", "255229124": "JOEL A",
            "255229125": "KABIL B", "255229126": "KEERTHAN G", "255229127": "KEVIN LAZARUS B",
            "255229128": "KIRUTHIKA S", "255229129": "LAKSHITHAL", "255229130": "MAHALAKSHMI S",
            "255229131": "MANOVISHNU A V", "255229132": "NALAN S", "255229133": "NANDHINI R",
            "255229134": "NAVEENKUMAR C", "255229135": "NIDHEESH S", "255229136": "NIRMAL G",
            "255229137": "PRASANTH M", "255229138": "PRAVIN V", "255229139": "PREM SELVAN R",
            "255229140": "PRICILLA C", "255229141": "PRIYA THARSHINI R", "255229142": "RAJA VIGNESH P",
            "255229143": "RAJAKUMAR AZARIAH S", "255229144": "RITHIKA M", "255229145": "SARAN B",
            "255229146": "SARMILA BANU A", "255229147": "SELVAKUMAR K", "255229148": "SIVAGAMI A",
            "255229149": "SIVAKUMAR E", "255229150": "SRIRAM M", "255229151": "STANLEY WILSON M",
            "255229152": "SUSMITHA M", "255229153": "SWATHI S", "255229154": "THANUSIYA R",
            "255229155": "THIRUMALAI RAJAN S", "255229156": "THIRUPUGAZH M", "255229157": "VIJAY V S",
            "255229158": "YOGALAKSHMI K", "255229159": "JAYA VARSHINI I",
            "255229161": "KEERTHANA SIRJA S", "255229162": "SHARAN KUMAR", "255229163": "LOKESH"
        }
        for reg, name in roster.items():
            cursor.execute("INSERT OR REPLACE INTO students (reg_no, name, year, section) VALUES (?, ?, ?, ?)", 
                           (reg, name, "II", "A"))
        conn.commit()
    conn.close()

@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    students = conn.execute("SELECT * FROM students ORDER BY reg_no ASC").fetchall()
    conn.close()
    return render_template("index.html", students=students)

@app.route("/api/parse-brochure", methods=["POST"])
def parse_brochure():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    try:
        file_bytes = file.read()
        mime_type = file.content_type or "application/pdf"

        prompt = """
        Extract the following event details from this document/invitation/brochure and return ONLY valid JSON:
        {
          "event_name": "",
          "organizer": "",
          "from_date": "YYYY-MM-DD format if available else empty string",
          "to_date": "YYYY-MM-DD format if available else empty string",
          "place": ""
        }
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type,
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        return response.text, 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
