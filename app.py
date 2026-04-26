from flask import Flask, request, redirect
import sqlite3
import os
import secrets
import re
from datetime import datetime

app = Flask(__name__)
DB_NAME = "buildpulse.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            owner_key TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            rating INTEGER,
            confusing TEXT,
            useless TEXT,
            missing TEXT,
            use_again TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    """)

    conn.commit()
    conn.close()


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "project"


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()

        if not project_name:
            return redirect("/")

        base_slug = slugify(project_name)
        slug = f"{base_slug}-{secrets.token_hex(3)}"
        owner_key = secrets.token_urlsafe(16)

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO projects (name, slug, owner_key, created_at) VALUES (?, ?, ?, ?)",
            (project_name, slug, owner_key, datetime.utcnow().isoformat())
        )

        conn.commit()
        conn.close()

        return redirect(f"/created/{slug}?key={owner_key}")

    return render_page("""
        <section class="hero">
            <div class="badge">Feedback collector for side projects</div>
            <h1>Collect feedback that actually helps you improve.</h1>
            <p>
                Create a feedback page, share the link, and get useful answers:
                what is confusing, useless, missing, and whether people would use it again.
            </p>
        </section>

        <div class="card">
            <h2>Create your feedback page</h2>
            <form method="POST">
                <input name="project_name" placeholder="Project name, e.g. Wealth Dashboard" required>
                <button type="submit">Create Feedback Page</button>
            </form>
        </div>
    """)


@app.route("/created/<slug>")
def created(slug):
    key = request.args.get("key", "")

    public_link = request.host_url.rstrip("/") + f"/p/{slug}"
    dashboard_link = request.host_url.rstrip("/") + f"/dashboard/{slug}?key={key}"

    return render_page(f"""
        <div class="card">
            <h2>✅ Feedback page created</h2>

            <p class="muted">Share this link with testers:</p>
            <div class="linkbox">{public_link}</div>

            <p class="muted">Your private dashboard link:</p>
            <div class="linkbox">{dashboard_link}</div>

            <p class="warning">
                Save your dashboard link. Anyone with this link can see your feedback.
            </p>

            <a class="button-link" href="/p/{slug}">Open feedback page</a>
            <a class="button-link secondary" href="/dashboard/{slug}?key={key}">Open dashboard</a>
        </div>
    """)


@app.route("/p/<slug>", methods=["GET", "POST"])
def feedback_page(slug):
    conn = get_db()
    cur = conn.cursor()

    project = cur.execute(
        "SELECT * FROM projects WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not project:
        conn.close()
        return render_page("<div class='card'><h2>Project not found</h2></div>")

    if request.method == "POST":
        rating = request.form.get("rating")
        confusing = request.form.get("confusing", "").strip()
        useless = request.form.get("useless", "").strip()
        missing = request.form.get("missing", "").strip()
        use_again = request.form.get("use_again", "").strip()

        cur.execute("""
            INSERT INTO feedback
            (project_id, rating, confusing, useless, missing, use_again, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project["id"],
            rating,
            confusing,
            useless,
            missing,
            use_again,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        return render_page(f"""
            <div class="card center">
                <h2>✅ Thanks for the feedback</h2>
                <p>Your response was submitted for <strong>{project["name"]}</strong>.</p>
            </div>
        """)

    conn.close()

    return render_page(f"""
        <div class="card">
            <div class="badge">Feedback request</div>
            <h2>{project["name"]}</h2>
            <p class="muted">
                Help the maker improve this project. Be honest and specific.
            </p>

            <form method="POST">
                <label>How useful is this project?</label>
                <select name="rating" required>
                    <option value="">Choose rating</option>
                    <option value="10">10 - Very useful</option>
                    <option value="8">8 - Useful</option>
                    <option value="5">5 - Maybe useful</option>
                    <option value="3">3 - Not very useful</option>
                    <option value="1">1 - Not useful</option>
                </select>

                <label>What feels confusing?</label>
                <textarea name="confusing" placeholder="What did you not understand?"></textarea>

                <label>What feels useless or unnecessary?</label>
                <textarea name="useless" placeholder="What should be removed or simplified?"></textarea>

                <label>What is missing?</label>
                <textarea name="missing" placeholder="What would make this more useful?"></textarea>

                <label>Would you use this again?</label>
                <textarea name="use_again" placeholder="Why or why not?"></textarea>

                <button type="submit">Submit Feedback</button>
            </form>
        </div>
    """)


@app.route("/dashboard/<slug>")
def dashboard(slug):
    key = request.args.get("key", "")

    conn = get_db()
    cur = conn.cursor()

    project = cur.execute(
        "SELECT * FROM projects WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not project:
        conn.close()
        return render_page("<div class='card'><h2>Project not found</h2></div>")

    if key != project["owner_key"]:
        conn.close()
        return render_page("<div class='card'><h2>Unauthorized</h2><p>Invalid dashboard key.</p></div>")

    feedback_items = cur.execute(
        "SELECT * FROM feedback WHERE project_id = ? ORDER BY id DESC",
        (project["id"],)
    ).fetchall()

    conn.close()

    if not feedback_items:
        feedback_html = """
            <div class="empty">
                <h3>No feedback yet</h3>
                <p>Share your public feedback link and responses will appear here.</p>
            </div>
        """
    else:
        cards = ""

        for item in feedback_items:
            cards += f"""
                <div class="feedback-card">
                    <div class="rating">Rating: {item["rating"]}/10</div>

                    <h4>Confusing</h4>
                    <p>{item["confusing"] or "No answer"}</p>

                    <h4>Useless / unnecessary</h4>
                    <p>{item["useless"] or "No answer"}</p>

                    <h4>Missing</h4>
                    <p>{item["missing"] or "No answer"}</p>

                    <h4>Would use again?</h4>
                    <p>{item["use_again"] or "No answer"}</p>
                </div>
            """

        feedback_html = cards

    public_link = request.host_url.rstrip("/") + f"/p/{slug}"

    return render_page(f"""
        <div class="dashboard-header">
            <div>
                <div class="badge">Dashboard</div>
                <h2>{project["name"]}</h2>
                <p class="muted">Public feedback link:</p>
                <div class="linkbox">{public_link}</div>
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <strong>{len(feedback_items)}</strong>
                <span>Total responses</span>
            </div>
        </div>

        {feedback_html}
    """)


def render_page(content):
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BuildPulse</title>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    min-height: 100vh;
    font-family: 'Inter', Arial, sans-serif;
    color: #f8fafc;
    background:
        radial-gradient(circle at top left, rgba(34,197,94,0.14), transparent 30%),
        radial-gradient(circle at top right, rgba(96,165,250,0.14), transparent 30%),
        linear-gradient(180deg, #050914 0%, #0f172a 100%);
    padding: 30px 18px 50px;
}}

.page {{
    max-width: 900px;
    margin: 0 auto;
}}

.nav {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 38px;
}}

.logo {{
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 800;
    font-size: 22px;
}}

.logo-icon {{
    width: 42px;
    height: 42px;
    border-radius: 14px;
    background: linear-gradient(135deg, #22c55e, #14b8a6);
    display: flex;
    align-items: center;
    justify-content: center;
}}

.nav-pill {{
    color: #bbf7d0;
    background: rgba(34,197,94,0.10);
    border: 1px solid rgba(34,197,94,0.22);
    border-radius: 999px;
    padding: 9px 13px;
    font-size: 13px;
    font-weight: 600;
}}

.hero {{
    text-align: center;
    margin-bottom: 26px;
}}

.badge {{
    display: inline-block;
    color: #bbf7d0;
    background: rgba(34,197,94,0.10);
    border: 1px solid rgba(34,197,94,0.22);
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 14px;
}}

.hero h1 {{
    max-width: 760px;
    margin: 0 auto;
    font-size: 44px;
    line-height: 1.05;
    letter-spacing: -0.055em;
}}

.hero p {{
    max-width: 650px;
    margin: 16px auto 0;
    color: #94a3b8;
    line-height: 1.7;
}}

.card {{
    background: rgba(15,23,42,0.78);
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 26px;
    padding: 26px;
    box-shadow: 0 24px 70px rgba(0,0,0,0.42);
    backdrop-filter: blur(18px);
}}

.card h2 {{
    margin-top: 0;
    font-size: 28px;
    letter-spacing: -0.04em;
}}

input, textarea, select {{
    width: 100%;
    margin: 8px 0 16px;
    padding: 14px;
    border-radius: 16px;
    border: 1px solid rgba(148,163,184,0.18);
    background: rgba(255,255,255,0.045);
    color: white;
    font-size: 14px;
    outline: none;
}}

textarea {{
    min-height: 95px;
    resize: vertical;
}}

option {{
    color: black;
}}

label {{
    display: block;
    color: #cbd5e1;
    font-size: 14px;
    font-weight: 700;
}}

button, .button-link {{
    display: inline-block;
    width: 100%;
    text-align: center;
    margin-top: 10px;
    padding: 15px 18px;
    border: none;
    border-radius: 17px;
    background: linear-gradient(135deg, #22c55e, #16a34a);
    color: white;
    font-weight: 800;
    font-size: 15px;
    text-decoration: none;
    cursor: pointer;
}}

.secondary {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(148,163,184,0.16);
}}

.muted {{
    color: #94a3b8;
}}

.warning {{
    color: #fbbf24;
    font-size: 14px;
}}

.linkbox {{
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(148,163,184,0.14);
    color: #bfdbfe;
    padding: 14px;
    border-radius: 16px;
    word-break: break-all;
    margin: 8px 0 18px;
}}

.center {{
    text-align: center;
}}

.dashboard-header {{
    margin-bottom: 20px;
}}

.stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 18px;
}}

.stat {{
    background: rgba(15,23,42,0.78);
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 20px;
    padding: 18px;
}}

.stat strong {{
    display: block;
    font-size: 32px;
}}

.stat span {{
    color: #94a3b8;
}}

.feedback-card {{
    background: rgba(15,23,42,0.78);
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 22px;
    padding: 20px;
    margin-bottom: 16px;
}}

.feedback-card h4 {{
    margin-bottom: 4px;
    color: #cbd5e1;
}}

.feedback-card p {{
    margin-top: 0;
    color: #e2e8f0;
    line-height: 1.5;
}}

.rating {{
    color: #86efac;
    font-weight: 800;
    margin-bottom: 12px;
}}

.empty {{
    text-align: center;
    color: #94a3b8;
    background: rgba(15,23,42,0.78);
    border: 1px solid rgba(148,163,184,0.16);
    border-radius: 22px;
    padding: 30px;
}}

@media (max-width: 640px) {{
    body {{
        padding: 20px 12px 40px;
    }}

    .nav {{
        flex-direction: column;
        align-items: flex-start;
        gap: 14px;
    }}

    .hero h1 {{
        font-size: 32px;
    }}

    .card {{
        padding: 20px;
        border-radius: 22px;
    }}
}}
</style>
</head>

<body>
<div class="page">

    <div class="nav">
        <div class="logo">
            <div class="logo-icon">💬</div>
            BuildPulse
        </div>
        <div class="nav-pill">No login MVP</div>
    </div>

    {content}

</div>
</body>
</html>
"""


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
