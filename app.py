import sqlite3
import secrets
import os
import shutil
import tempfile
from contextlib import contextmanager
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response

try:
    import turso_db
except ImportError:
    from . import turso_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "templates")
if not os.path.isdir(templates_dir):
    templates_dir = os.path.join(os.path.dirname(BASE_DIR), "templates")

app = Flask(__name__, template_folder=templates_dir)
# Stable secret key across serverless instances so admin login persists
app.secret_key = os.environ.get("SECRET_KEY", "moksha_fest_2026_super_secret_session_key")


class VercelPathFixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path.startswith('/api/index.py'):
            environ['PATH_INFO'] = path[len('/api/index.py'):] or '/'
        elif path.startswith('/api/index'):
            environ['PATH_INFO'] = path[len('/api/index'):] or '/'
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "moksha2026")
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def is_using_turso():
    return bool(os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"))


def get_db_path():
    if IS_VERCEL:
        tmp_dir = tempfile.gettempdir()
        tmp_db = os.path.join(tmp_dir, "moksha.db")
        orig_db = os.path.join(BASE_DIR, "moksha.db")
        if not os.path.exists(tmp_db) and os.path.exists(orig_db):
            shutil.copy2(orig_db, tmp_db)
        return tmp_db
    return os.path.join(BASE_DIR, "moksha.db")


def is_admin():
    return session.get("admin") is True


def GET_DB():
    if is_using_turso():
        return turso_db.TursoConnection(
            os.environ["TURSO_DATABASE_URL"],
            os.environ["TURSO_AUTH_TOKEN"]
        )
    # timeout: wait up to 30s instead of failing instantly if the file is briefly locked
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode: readers (incl. external tools like DB Browser) don't block our writes
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = GET_DB()
    try:
        yield conn, conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    base_dir = os.path.dirname(__file__)
    schema_path = os.path.join(base_dir, "schema.sql")

    with db() as (conn, cursor):
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                sql_script = f.read()

            # Only build the schema (and seed data) on first run.
            existing = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='PARTICIPANT'").fetchone()
            if not existing:
                cursor.executescript(sql_script)

        # FEEDBACK used by the dashboard
        cursor.execute("""CREATE TABLE IF NOT EXISTS FEEDBACK (
            feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, role TEXT, category TEXT,
            message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")


try:
    init_db()
except Exception as _e:
    pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/events", methods=["GET"])
def api_events():
    with db() as (conn, cursor):
        rows = cursor.execute(
            "SELECT event_id, name, category, venue, event_date, fee, max_seats FROM EVENT"
        ).fetchall()
        events = []
        for r in rows:
            registered = cursor.execute(
                "SELECT COUNT(*) FROM REGISTRATION WHERE event_id = ?", (r[0],)).fetchone()[0]
            events.append({
                "event_id": r[0], "name": r[1], "category": r[2], "venue": r[3],
                "event_date": r[4], "fee": r[5], "max_seats": r[6],
                "seats_left": max(0, r[6] - registered)
            })
    return jsonify(events)


@app.route("/api/stalls", methods=["GET"])
def api_stalls():
    with db() as (conn, cursor):
        rows = cursor.execute(
            "SELECT stall_id, location, size, price, status FROM STALL").fetchall()
    return jsonify([{"stall_id": r[0], "location": r[1], "size": r[2],
                     "price": r[3], "status": r[4]} for r in rows])


@app.route("/api/tiers", methods=["GET"])
def api_tiers():
    with db() as (conn, cursor):
        rows = cursor.execute(
            "SELECT tier_id, name, amount, benefits FROM SPONSORSHIP_TIER").fetchall()
    return jsonify([{"tier_id": r[0], "name": r[1], "amount": r[2], "benefits": r[3]}
                    for r in rows])


def clean(v):
    """Turn empty dropdown/input values into proper NULLs for the DB."""
    if v is None:
        return None
    v = str(v).strip()
    return v if v != "" else None


@app.route("/api/register", methods=["POST"])
def api_register():
    try:
        data = request.get_json()
        with db() as (conn, cursor):
            # Ensure college exists or insert it
            college_name = (data.get("college_name") or "").strip()
            college_id = None
            if college_name:
                row = cursor.execute(
                    "SELECT college_id FROM COLLEGE WHERE name=?", (college_name,)).fetchone()
                if row:
                    college_id = row[0]
                else:
                    cursor.execute(
                        "INSERT INTO COLLEGE (name, city, is_nsut) VALUES (?, ?, ?)",
                        (college_name, data.get("college_city") or "",
                         1 if college_name == "NSUT" else 0))
                    college_id = cursor.lastrowid

            cursor.execute(
                """INSERT INTO PARTICIPANT (full_name, email, phone, age, gender, college_id, enrollment_no, year_of_study, course_branch, state, emergency_name, emergency_phone, dietary_pref, tshirt_size, accommodation, id_proof_type, how_heard, participant_role, special_needs)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data.get("full_name"), data.get("email"), data.get("phone"),
                 int(data["age"]) if clean(data.get("age")) else 0,
                 data.get("gender"), college_id, clean(data.get("enrollment_no")),
                 int(data["year_of_study"]) if clean(data.get("year_of_study")) else None,
                 clean(data.get("course_branch")), clean(data.get("state")),
                 clean(data.get("emergency_name")), clean(data.get("emergency_phone")),
                 clean(data.get("dietary_pref")), clean(data.get("tshirt_size")),
                 data.get("accommodation", "No") or "No",
                 clean(data.get("id_proof_type")),
                 clean(data.get("how_heard")), clean(data.get("participant_role")),
                 clean(data.get("special_needs"))))
            participant_id = cursor.lastrowid

            event_ids = data.get("event_ids", []) or []
            team_name = data.get("team_name", "")
            team_size = data.get("team_size")
            experience_level = data.get("experience_level", "")
            pass_type = data.get("pass_type", "All Days")

            for eid in event_ids:
                cursor.execute(
                    "INSERT INTO REGISTRATION (participant_id, event_id, team_name, team_size, experience_level) VALUES (?, ?, ?, ?, ?)",
                    (participant_id, int(eid), team_name or None,
                     int(team_size) if team_size else None,
                     experience_level or None))

            # Entry pass price = sum of selected event fees (0 if none)
            fee = 0
            if event_ids:
                placeholders = ",".join("?" * len(event_ids))
                fees = [r[0] for r in cursor.execute(
                    f"SELECT fee FROM EVENT WHERE event_id IN ({placeholders})",
                    event_ids).fetchall()]
                fee = sum(fees) if fees else 0
            final_price = data.get("fee") or fee

            cursor.execute(
                "INSERT INTO ENTRY_PASS (participant_id, pass_type, price) VALUES (?, ?, ?)",
                (participant_id, pass_type or "All Days", float(final_price)))

        return jsonify({"ok": True, "participant_id": participant_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": friendly_error(e)}), 400


@app.route("/api/vendor", methods=["POST"])
def api_vendor():
    try:
        data = request.get_json()
        with db() as (conn, cursor):
            # Sponsor form has no phone field — default to '' (schema requires non-null)
            cursor.execute(
                """INSERT INTO VENDOR (company_name, contact_person, email, phone, business_type, website, social_handle, address, city, gst_number, fssai_no, years_in_business, alt_phone)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data.get("company_name"), data.get("contact_person"), data.get("email"),
                 data.get("phone") or "", data.get("business_type") or "Other", data.get("website"),
                 data.get("social_handle"), data.get("address"), data.get("city"),
                 data.get("gst_number"), data.get("fssai_no"),
                 data.get("years_in_business"), data.get("alt_phone")))
            vendor_id = cursor.lastrowid

            # Stall booking
            stall_id = data.get("stall_id")
            if stall_id and str(stall_id).strip() != "":
                cursor.execute(
                    """INSERT INTO STALL_BOOKING (vendor_id, stall_id, products_description, staff_count, power_required_kw, equipment_needed, preferred_days, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')""",
                    (vendor_id, int(stall_id), data.get("products_description"),
                     data.get("staff_count"), data.get("power_required_kw"),
                     data.get("equipment_needed"), data.get("preferred_days")))
                cursor.execute(
                    "UPDATE STALL SET status='Booked' WHERE stall_id=?", (int(stall_id),))

            # Sponsorship
            tier_id = data.get("tier_id")
            event_id = data.get("event_id")
            if tier_id and str(tier_id).strip() != "":
                event_id_int = int(event_id) if event_id and str(event_id).strip() != "" else None
                cursor.execute(
                    """INSERT INTO SPONSORSHIP (vendor_id, tier_id, event_id, sponsor_type, proposed_amount, brand_objective, promo_requirements, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')""",
                    (vendor_id, int(tier_id), event_id_int, data.get("sponsor_type"),
                     data.get("proposed_amount"), data.get("brand_objective"),
                     data.get("promo_requirements")))

        return jsonify({"ok": True, "vendor_id": vendor_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": friendly_error(e)}), 400


@app.route("/api/feedback", methods=["GET"])
def api_feedback():
    with db() as (conn, cursor):
        rows = cursor.execute(
            "SELECT feedback_id, name, email, role, category, message, created_at FROM FEEDBACK ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([{"feedback_id": r[0], "name": r[1], "email": r[2], "role": r[3],
                     "category": r[4], "message": r[5], "created_at": r[6]} for r in rows])


@app.route("/api/feedback", methods=["POST"])
def api_feedback_post():
    try:
        data = request.get_json()
        with db() as (conn, cursor):
            cursor.execute(
                "INSERT INTO FEEDBACK (name, email, role, category, message) VALUES (?, ?, ?, ?, ?)",
                (data.get("name"), data.get("email"), data.get("role", "Participant"),
                 data.get("category", "Feedback"), data.get("message")))
            feedback_id = cursor.lastrowid
        return jsonify({"ok": True, "feedback_id": feedback_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": friendly_error(e)}), 400


@app.route("/admin/login", methods=["GET", "POST"])
@app.route("/admin/login/", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_page"))
        error = "Wrong password. Try again."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
@app.route("/admin/logout/")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@app.route("/admin/")
def admin_page():
    if not is_admin():
        return redirect(url_for("admin_login"))
    return render_template("admin.html")


@app.route("/api/admin", methods=["GET"])
def api_admin():
    if not is_admin():
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    try:
        with db() as (conn, cursor):
            participants = [{
                "id": r[0], "name": r[1], "email": r[2], "phone": r[3],
                "age": r[4], "gender": r[5], "college": r[6] or "-",
                "role": r[7] or "-", "emergency": r[8],
                "registered_at": r[9],
            } for r in cursor.execute("""
                SELECT p.participant_id, p.full_name, p.email, p.phone, p.age, p.gender,
                       c.name, p.participant_role, p.emergency_phone, p.created_at
                FROM PARTICIPANT p LEFT JOIN COLLEGE c ON p.college_id = c.college_id
                ORDER BY p.participant_id DESC""").fetchall()]

            registrations = [{
                "reg": r[0], "participant": r[1], "event": r[2], "date": r[3],
                "team": r[4] or "-", "size": r[5] or "-", "experience": r[6] or "-",
            } for r in cursor.execute("""
                SELECT g.reg_id, p.full_name, e.name, g.reg_date, g.team_name,
                       g.team_size, g.experience_level
                FROM REGISTRATION g
                JOIN PARTICIPANT p ON g.participant_id = p.participant_id
                JOIN EVENT e ON g.event_id = e.event_id
                ORDER BY g.reg_id DESC""").fetchall()]

            passes = [{
                "pass_id": r[0], "participant": r[1], "type": r[2], "price": r[3],
                "issued": r[4],
            } for r in cursor.execute("""
                SELECT ep.pass_id, p.full_name, ep.pass_type, ep.price, ep.issued_at
                FROM ENTRY_PASS ep JOIN PARTICIPANT p ON ep.participant_id = p.participant_id
                ORDER BY ep.pass_id DESC""").fetchall()]

            events = [{
                "id": r[0], "name": r[1], "category": r[2], "fee": r[3],
                "seats": r[4], "filled": r[5],
            } for r in cursor.execute("""
                SELECT e.event_id, e.name, e.category, e.fee, e.max_seats,
                       (SELECT COUNT(*) FROM REGISTRATION g WHERE g.event_id = e.event_id)
                FROM EVENT e ORDER BY e.event_id""").fetchall()]

            vendors = [{
                "id": r[0], "company": r[1], "contact": r[2], "email": r[3],
                "type": r[4], "city": r[5] or "-", "stall": r[6] or "-", "tier": r[7] or "-",
            } for r in cursor.execute("""
                SELECT v.vendor_id, v.company_name, v.contact_person, v.email,
                       v.business_type, v.city,
                       (SELECT s.location FROM STALL_BOOKING b JOIN STALL s
                          ON b.stall_id = s.stall_id WHERE b.vendor_id = v.vendor_id),
                       (SELECT t.name FROM SPONSORSHIP sp JOIN SPONSORSHIP_TIER t
                          ON sp.tier_id = t.tier_id WHERE sp.vendor_id = v.vendor_id)
                FROM VENDOR v ORDER BY v.vendor_id DESC""").fetchall()]

            feedback = [{
                "name": r[0], "role": r[1] or "Participant", "category": r[2],
                "message": r[3], "created": r[4],
            } for r in cursor.execute("""
                SELECT name, role, category, message, created_at
                FROM FEEDBACK ORDER BY created_at DESC""").fetchall()]

            stats = cursor.execute("""
                SELECT (SELECT COUNT(*) FROM PARTICIPANT),
                       (SELECT COUNT(*) FROM REGISTRATION),
                       (SELECT COUNT(*) FROM VENDOR),
                       (SELECT COUNT(*) FROM FEEDBACK)""").fetchone()

            db_mode = "turso" if is_using_turso() else ("vercel_tmp" if IS_VERCEL else "local_sqlite")

        return jsonify({
            "db_mode": db_mode,
            "stats": {"participants": stats[0], "registrations": stats[1],
                      "vendors": stats[2], "feedback": stats[3]},
            "participants": participants,
            "registrations": registrations,
            "passes": passes,
            "events": events,
            "vendors": vendors,
            "feedback": feedback,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": friendly_error(e)}), 400


@app.route("/api/admin/export_csv", methods=["GET"])
def api_admin_export_csv():
    if not is_admin():
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    import csv
    import io
    
    with db() as (conn, cursor):
        rows = cursor.execute("""
            SELECT p.participant_id, p.full_name, p.email, p.phone, p.age, p.gender,
                   c.name, p.course_branch, p.year_of_study, p.enrollment_no,
                   p.participant_role, ep.pass_type, ep.price, p.emergency_name,
                   p.emergency_phone, p.dietary_pref, p.tshirt_size, p.accommodation,
                   p.created_at
            FROM PARTICIPANT p
            LEFT JOIN COLLEGE c ON p.college_id = c.college_id
            LEFT JOIN ENTRY_PASS ep ON p.participant_id = ep.participant_id
            ORDER BY p.participant_id DESC
        """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Name", "Email", "Phone", "Age", "Gender", "College",
        "Branch", "Year", "Enrollment", "Role", "Pass Type", "Pass Price",
        "Emergency Name", "Emergency Phone", "Dietary", "T-Shirt", "Accommodation", "Registered At"
    ])
    for r in rows:
        writer.writerow(list(r))
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=moksha_participants.csv"}
    )


def friendly_error(e):
    """Map raw sqlite constraint errors to messages the user can act on."""
    if isinstance(e, sqlite3.IntegrityError):
        msg = str(e)
        if "PARTICIPANT.email" in msg or "VENDOR.email" in msg:
            return "This email is already registered. Please use a different email address."
        return "Some required details are missing or invalid. Please check the form and try again."
    return str(e)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
