"""
make_sample_data.py
Creates (1) the training CSV for the classifier and (2) demo documents in sample_documents/.
All names, numbers and amounts are FICTIONAL. Run:  python scripts/make_sample_data.py
"""
import csv
import random
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST = ["Aminata", "Mohamed", "Fatmata", "Ibrahim", "Isatu", "Abu", "Mariama", "Sorie", "Hawa", "Alusine",
         "Kadiatu", "Foday", "Zainab", "Joseph", "Hannah", "Samuel", "Marie", "Musa", "Adama", "Patrick"]
LAST = ["Kamara", "Sesay", "Bangura", "Conteh", "Koroma", "Turay", "Jalloh", "Kargbo", "Mansaray", "Sankoh",
        "Bah", "Fofanah", "Sillah", "Kanu", "Lahai", "Massaquoi"]
PROGRAMMES = ["Diploma in Information Technology", "Diploma in Public Administration", "Diploma in Accounting",
              "Diploma in Business Administration", "Diploma in Human Resource Management",
              "Diploma in Procurement and Supply Chain"]
COURSES = ["Database Systems", "Public Policy Analysis", "Financial Accounting", "Organisational Behaviour",
           "Research Methods", "Computer Networks", "Programming Fundamentals", "Project Management",
           "Business Statistics", "Business Communication", "Principles of Management", "Web Development",
           "Human Resource Planning", "Public Finance", "Systems Analysis and Design", "Ethics in Public Service"]
GRADES = [("A", 4.0), ("B", 3.0), ("C", 2.0), ("D", 1.0), ("B", 3.0), ("A", 4.0), ("C", 2.0)]
YEARS = ["2022/2023", "2023/2024", "2024/2025", "2025/2026"]
NOISE = ["Kindly retain this document for your records.", "IPAM, Freetown, Sierra Leone.",
         "This document is issued by the Institute of Public Administration and Management.",
         "Please contact the relevant office for any clarification.", "Students are advised accordingly."]


def name(r):
    return r.choice(FIRST) + " " + r.choice(LAST)


def sid(r):
    return str(r.randint(10000, 19999))


def date(r):
    return f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/{r.choice(['2024', '2025', '2026'])}"


def leones(r, lo=300, hi=9000):
    return f"Le {r.randint(lo, hi):,}"


def transcript(r):
    rows, pts = [], 0
    picks = r.sample(COURSES, 5)
    for i, c in enumerate(picks):
        g, p = r.choice(GRADES)
        pts += p
        rows.append(f"IT{r.randint(101, 409)}  {c}  3 credits  Grade {g}  Points {p}")
    gpa = round(pts / 5, 2)
    head = r.choice(["OFFICIAL ACADEMIC TRANSCRIPT", "STATEMENT OF RESULTS", "EXAMINATION RESULTS SHEET", "STUDENT RESULT SLIP"])
    body = [head, "Institute of Public Administration and Management (IPAM)", f"Student Name: {name(r)}",
            f"Student ID: {sid(r)}", f"Programme: {r.choice(PROGRAMMES)}", f"Academic Year: {r.choice(YEARS)}",
            f"Semester: {r.choice(['One', 'Two'])}", "Course Code  Course Title  Credit  Grade  Grade Point"] + rows
    body += [f"Semester GPA: {gpa}", f"Cumulative GPA: {round(gpa + r.uniform(-0.3, 0.3), 2)}",
             r.choice(["Class of award: Pass", "Status: Good academic standing", "Remarks: Proceed to next level"]),
             "Issued by the Office of the Registrar. Grades are subject to Senate approval."]
    return "\n".join(body)


def admission(r):
    who, prog = name(r), r.choice(PROGRAMMES)
    v = r.randint(0, 2)
    if v == 0:
        return "\n".join(["LETTER OF PROVISIONAL ADMISSION", f"Dear {who},",
                          f"We are pleased to offer you admission into the {prog} for the {r.choice(YEARS)} academic year.",
                          f"Your application number is APP{r.randint(1000, 9999)}. Your WASSCE results met the minimum entry requirements.",
                          f"Please accept this offer and complete registration before {date(r)}. Orientation for new students begins on {date(r)}.",
                          "Bring your original certificates, birth certificate and two passport photographs.",
                          "Director of Admissions, IPAM"])
    if v == 1:
        return "\n".join(["APPLICATION FORM FOR ADMISSION", f"Applicant Name: {who}", f"Date of Birth: {date(r)}",
                          f"Programme applied for: {prog}", f"Application number: APP{r.randint(1000, 9999)}",
                          f"WASSCE credits: English Language, Mathematics, {r.choice(['Economics', 'Physics', 'Government'])}",
                          "Entry requirements: five credits including English Language and Mathematics",
                          "Declaration: I confirm the information provided is correct.", "Applicant signature and date"])
    return "\n".join(["ADMISSION COMMITTEE REPORT", f"The admission committee met on {date(r)} to review applications for {prog}.",
                      f"{r.randint(30, 120)} applicants were considered and {r.randint(20, 80)} were offered admission.",
                      "Applicants who did not meet the entry requirements were placed on the waiting list.",
                      "Successful applicants will receive admission letters and registration instructions."])


def memo(r):
    subj = r.choice([
        ("Staff Meeting", "All Heads of Department are invited to a management meeting to review the semester plan."),
        ("Examination Timetable", "The final examination timetable has been approved. Invigilators must report thirty minutes early."),
        ("Public Holiday Closure", "The Institute will be closed on the public holiday. Normal activities resume on the next working day."),
        ("Submission of Grades", "Lecturers must submit all marked scripts and grades to the Examinations Office by the stated deadline."),
        ("Office Fumigation", "Offices will be fumigated this weekend. Staff should remove important papers from desks."),
        ("Staff Dress Code", "All staff are reminded to observe the approved dress code while on duty."),
        ("Committee Appointment", "The Registrar has approved the new committee to coordinate the graduation ceremony."),
    ])
    lines = ["MEMORANDUM", f"To: {r.choice(['All Staff', 'All Heads of Department', 'All Lecturers', 'Deans and Directors'])}",
             f"From: {r.choice(['The Registrar', 'The Principal', 'The Director of Administration', 'Head of Human Resources'])}",
             f"Date: {date(r)}", f"Subject: {subj[0]}", subj[1],
             r.choice(["Please be guided accordingly.", "Your cooperation is highly appreciated.", "All concerned should take note."]),
             f"Ref: IPAM/ADM/{r.randint(100, 999)}"]
    return "\n".join(lines)


def financial(r):
    v = r.randint(0, 2)
    if v == 0:
        paid = r.randint(1500, 6000)
        return "\n".join(["OFFICIAL RECEIPT", f"Receipt No: RC{r.randint(10000, 99999)}", f"Received from: {name(r)}",
                          f"Amount paid: Le {paid:,}", f"Being payment for: {r.choice(['tuition fees', 'registration fee', 'examination fee', 'library fee'])}",
                          f"Payment method: {r.choice(['Bank deposit', 'Orange Money', 'Cash', 'Cheque'])}",
                          f"Balance outstanding: Le {r.randint(0, 3000):,}", f"Date: {date(r)}", "Bursar, IPAM"])
    if v == 1:
        qty, price = r.randint(2, 40), r.randint(50, 900)
        return "\n".join(["SUPPLIER INVOICE", f"Invoice No: INV{r.randint(1000, 9999)}", f"Supplier: {r.choice(['Freetown Office Supplies', 'Salone Print Works', 'Kissy IT Traders'])}",
                          f"Item: {r.choice(['printer paper reams', 'toner cartridges', 'desktop computers', 'office chairs'])}",
                          f"Quantity: {qty}  Unit price: Le {price:,}  Total: Le {qty * price:,}", "GST 15% included. Payment due within 30 days.",
                          "Approved for payment by the Bursar."])
    return "\n".join(["QUARTERLY EXPENDITURE STATEMENT", f"Period: Quarter {r.randint(1, 4)}, {r.choice(YEARS)}",
                      f"Total income: {leones(r, 50000, 90000)}", f"Salaries: {leones(r, 20000, 40000)}",
                      f"Utilities and maintenance: {leones(r, 3000, 9000)}", f"Budget variance: {leones(r, 100, 3000)}",
                      "Prepared by the Finance Office. Account reconciled with the bank statement."])


MAKERS = {"Transcripts": transcript, "Admission": admission, "Administrative Memos": memo, "Financial Records": financial}
# Sentences borrowed from other categories so the task is not artificially easy
CROSS = {"Transcripts": ["Outstanding fees must be cleared before results are released."],
         "Admission": ["Tuition fees are payable at registration."],
         "Administrative Memos": ["New students will be admitted next semester.", "Student results will be released soon."],
         "Financial Records": ["Student ID must be quoted on all payments.", "Issued by the Office of the Registrar."]}


def make_doc(cat, r):
    text = MAKERS[cat](r)
    if r.random() < 0.30:
        text += "\n" + r.choice(CROSS[cat])
    if r.random() < 0.40:
        text += "\n" + r.choice(NOISE)
    return text


def make_training_csv(per_class=70, seed=42):
    r = random.Random(seed)
    out = ROOT / "data" / "training" / "seed_documents.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["text", "category"])
        for cat in MAKERS:
            for _ in range(per_class):
                w.writerow([make_doc(cat, r), cat])
    return out


def _render_scan(text, path, as_pdf=False, seed=1):
    """Draw text on a page and add tilt + noise so it looks like a real scan."""
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 26)
    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    y = 110
    for line in text.split("\n"):
        for sub in textwrap.wrap(line, 62) or [""]:
            d.text((90, y), sub, fill=20, font=font)
            y += 40
    rng = np.random.default_rng(seed)
    img = img.rotate(rng.uniform(-0.8, 0.8), fillcolor=255, resample=Image.BICUBIC)
    arr = np.asarray(img).astype("float32") + rng.normal(0, 9, (1754, 1240))
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    img.save(str(path), "PDF", resolution=150) if as_pdf else img.save(str(path))


def make_sample_documents():
    import docx
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    r = random.Random(2026)
    out = ROOT / "sample_documents"
    out.mkdir(exist_ok=True)
    plan = [("Transcripts", "docx"), ("Transcripts", "pdf"), ("Transcripts", "scan_png"),
            ("Admission", "txt"), ("Admission", "pdf"), ("Admission", "scan_pdf"),
            ("Administrative Memos", "txt"), ("Administrative Memos", "docx"), ("Administrative Memos", "scan_pdf"),
            ("Financial Records", "pdf"), ("Financial Records", "scan_png"), ("Financial Records", "docx")]
    truth = []
    for i, (cat, kind) in enumerate(plan, 1):
        text = make_doc(cat, r)
        base = f"{i:02d}_{cat.lower().replace(' ', '_')}"
        if kind == "txt":
            fname = base + ".txt"
            (out / fname).write_text(text, encoding="utf-8")
        elif kind == "docx":
            fname = base + ".docx"
            d = docx.Document()
            for line in text.split("\n"):
                d.add_paragraph(line)
            d.save(str(out / fname))
        elif kind == "pdf":
            fname = base + ".pdf"
            c = canvas.Canvas(str(out / fname), pagesize=A4)
            y = 800
            for line in text.split("\n"):
                for sub in textwrap.wrap(line, 90) or [""]:
                    c.drawString(50, y, sub)
                    y -= 16
            c.save()
        elif kind == "scan_png":
            fname = base + "_scan.png"
            _render_scan(text, out / fname, seed=i)
        else:
            fname = base + "_scan.pdf"
            _render_scan(text, out / fname, as_pdf=True, seed=i)
        (out / "_truth").mkdir(exist_ok=True)
        (out / "_truth" / (fname + ".txt")).write_text(text, encoding="utf-8")
        truth.append((fname, cat))
    with open(out / "ground_truth.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "true_category"])
        w.writerows(truth)
    return len(truth)


if __name__ == "__main__":
    print("Training CSV:", make_training_csv())
    print("Sample documents created:", make_sample_documents())
