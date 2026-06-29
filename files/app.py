"""
NoteShare — Flask + SQLite backend
Run:  python app.py
Requires: pip install flask werkzeug
"""

from flask import (
    Flask, request, jsonify, render_template,
    send_from_directory, session, redirect, url_for
)
import os, uuid, sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename
from functools import wraps

# ── App config ────────────────────────────────────────────────
app = Flask(__name__, template_folder='Templates')
app.secret_key = 'noteshare_secret_key_2026_change_me'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024   # 50 MB

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'txt'
}

SUBJECT_COLORS = {
    'C Programming':     ('icon-blue',   'ti-code'),
    'MySQL':             ('icon-pink',   'ti-database'),
    'MATLAB':            ('icon-amber',  'ti-chart-line'),
    'Data Structures':   ('icon-green',  'ti-binary-tree'),
    'Operating Systems': ('icon-teal',   'ti-cpu'),
    'Discrete Maths':    ('icon-purple', 'ti-math-function'),
    'Python':            ('icon-blue',   'ti-brand-python'),
    'Other':             ('icon-pink',   'ti-file'),
}

# ── SQLite connection config ──────────────────────────────────
DB_FILE = os.path.join(BASE_DIR, 'noteshare.db')

# ── DB helpers ────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def query(sql, params=(), fetch='all'):
    """
    Execute SQL and return results.
    fetch='all'  → list of dicts
    fetch='one'  → single dict or None
    fetch='none' → None (for INSERT/UPDATE/DELETE)
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if fetch == 'all':
            return [dict(row) for row in cur.fetchall()]
        elif fetch == 'one':
            row = cur.fetchone()
            return dict(row) if row else None
        else:
            conn.commit()
            return None
    except sqlite3.Error as e:
        print(f"[DB ERROR] {e}")
        raise
    finally:
        conn.close()

def init_db():
    print("Ensuring database tables exist...")
    conn = get_db()
    schema_path = os.path.join(BASE_DIR, 'schema_sqlite.sql')
    with open(schema_path, 'r') as f:
        conn.executescript(f.read())
    conn.close()

# ── Settings helpers ──────────────────────────────────────────
DEFAULT_SETTINGS = {
    'site_title':       'NoteShare',
    'site_tagline':     'Collaborative Learning Platform',
    'hero_heading':     'Knowledge Grows When Shared',
    'hero_sub':         'Upload, discover, and download lecture notes effortlessly.',
    'footer_text':      'Made with ♥ by Utkarsh, Sachin, Rohit & Naitik',
    'primary_color':    '#e0217a',
    'allow_uploads':    'true',
    'show_downloads':   'true',
    'admin_password':   'admin',
    'contact_name':     'Utkarsh Agarwal',
    'contact_role':     'Creator & Developer — NoteShare',
    'contact_email':    'agarwalutkarsh1948@gmail.com',
    'contact_phone':    '+91 7818026130',
    'contact_linkedin': 'https://www.linkedin.com/in/utkarsh-agarwal-a436a2383/',
}


def load_settings():
    rows = query("SELECT `key`, `value` FROM settings")
    s = DEFAULT_SETTINGS.copy()
    for row in rows:
        s[row['key']] = row['value']
    # Normalise boolean strings → Python bools
    s['allow_uploads']  = str(s.get('allow_uploads',  'true')).lower()  == 'true'
    s['show_downloads'] = str(s.get('show_downloads', 'true')).lower()  == 'true'
    return s


def save_setting(key, value):
    """Upsert a single setting row."""
    query(
        "INSERT INTO settings (`key`, `value`) VALUES (?, ?) "
        "ON CONFLICT(`key`) DO UPDATE SET `value` = excluded.`value`",
        (key, str(value)),
        fetch='none'
    )


# ── Note helpers ──────────────────────────────────────────────
def format_date(date_obj):
    if isinstance(date_obj, datetime):
        return date_obj.strftime('%d %b %Y, %I:%M %p')
    elif isinstance(date_obj, str):
        try:
            # handle SQLite default format 'YYYY-MM-DD HH:MM:SS'
            dt = datetime.strptime(date_obj, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%d %b %Y, %I:%M %p')
        except ValueError:
            return date_obj
    return date_obj

def load_notes(subject=None, status='approved'):
    if subject and subject != 'All':
        rows = query(
            "SELECT * FROM notes WHERE subject = ? AND status = ? ORDER BY uploaded_at DESC",
            (subject, status)
        )
    else:
        rows = query("SELECT * FROM notes WHERE status = ? ORDER BY uploaded_at DESC", (status,))
    # Format datetime for templates
    for r in rows:
        r['uploaded_at'] = format_date(r['uploaded_at'])
    return rows


def load_all_notes_admin():
    rows = query("SELECT * FROM notes ORDER BY uploaded_at DESC")
    for r in rows:
        r['uploaded_at'] = format_date(r['uploaded_at'])
    return rows


def pending_count():
    row = query("SELECT COUNT(*) AS cnt FROM notes WHERE status='pending'", fetch='one')
    return row['cnt'] if row else 0


def get_note_by_id(note_id):
    row = query("SELECT * FROM notes WHERE id = ?", (note_id,), fetch='one')
    if row:
        row['uploaded_at'] = format_date(row['uploaded_at'])
    return row


def get_note_by_filename(filename):
    return query(
        "SELECT * FROM notes WHERE filename = ?", (filename,), fetch='one'
    )


# ── Auth decorator ────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ── Public routes ─────────────────────────────────────────────
@app.route('/')
def index():
    notes = load_notes(status='approved')
    s     = load_settings()
    return render_template('index.html', notes=notes,
                           subject_colors=SUBJECT_COLORS, s=s)


@app.route('/upload', methods=['POST'])
def upload_file():
    s = load_settings()
    if not s.get('allow_uploads', True):
        return jsonify({'error': 'Uploads are currently disabled by the admin.'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file        = request.files['file']
    title       = request.form.get('title',       '').strip()
    subject     = request.form.get('subject',     'Other').strip()
    description = request.form.get('description', '').strip()
    uploader    = request.form.get('uploader',    'Anonymous').strip()

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    ext         = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path   = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(save_path)

    file_size = os.path.getsize(save_path)
    size_str  = (
        f"{file_size // 1024} KB"
        if file_size < 1024 * 1024
        else f"{file_size // (1024 * 1024)} MB"
    )

    note_id = uuid.uuid4().hex
    note_title = title or secure_filename(file.filename)

    # SQLite compatible datetime format
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    query(
        """INSERT INTO notes
           (id, title, subject, description, uploader,
            filename, original_name, ext, size, downloads, status, uploaded_at)
           VALUES (?,?,?,?,?,?,?,?,?,0,'pending',?)""",
        (note_id, note_title, subject,
         description or f"Notes on {subject}",
         uploader, unique_name, file.filename, ext, size_str, now_str),
        fetch='none'
    )

    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS['Other'])
    note = {
        'id':            note_id,
        'title':         note_title,
        'subject':       subject,
        'description':   description or f"Notes on {subject}",
        'uploader':      uploader,
        'filename':      unique_name,
        'original_name': file.filename,
        'ext':           ext,
        'size':          size_str,
        'uploaded_at':   datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'downloads':     0,
        'status':        'pending',
        'icon_class':    colors[0],
        'icon_name':     colors[1],
    }
    return jsonify({'success': True, 'pending': True, 'message': '✅ Your note has been submitted! It will appear after admin approval.', 'note': note})


@app.route('/preview/<filename>')
@admin_required
def preview_file(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'], filename, as_attachment=False
    )


@app.route('/download/<filename>')
def download_file(filename):
    query(
        "UPDATE notes SET downloads = downloads + 1 WHERE filename = ?",
        (filename,), fetch='none'
    )
    return send_from_directory(
        app.config['UPLOAD_FOLDER'], filename, as_attachment=True
    )


@app.route('/api/notes')
def api_notes():
    subject = request.args.get('subject', '')
    notes   = load_notes(subject, status='approved')
    return jsonify(notes)


# ── Admin routes ──────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    error = None
    if request.method == 'POST':
        un = request.form.get('username', '')
        pw = request.form.get('password', '')
        s  = load_settings()
        if un == s.get('admin_username', 'admin') and pw == s.get('admin_password', 'admin'):
            session['admin_logged_in'] = True
            session.permanent = False
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid username or password. Please try again.'

    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    notes    = load_all_notes_admin()
    s        = load_settings()
    total_dl = sum(n.get('downloads', 0) for n in notes)
    pending  = pending_count()

    approved = [n for n in notes if n['status'] == 'approved']
    subjects = {}
    for n in approved:
        subjects[n['subject']] = subjects.get(n['subject'], 0) + 1

    return render_template('admin.html', notes=notes, s=s,
                           total_dl=total_dl, subjects=subjects, pending_count=pending)


@app.route('/admin/note/approve/<note_id>', methods=['POST'])
@admin_required
def admin_approve_note(note_id):
    query("UPDATE notes SET status='approved' WHERE id = ?", (note_id,), fetch='none')
    return jsonify({'success': True})


@app.route('/admin/note/reject/<note_id>', methods=['POST'])
@admin_required
def admin_reject_note(note_id):
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], note['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    query("UPDATE notes SET status='rejected' WHERE id = ?", (note_id,), fetch='none')
    return jsonify({'success': True})


@app.route('/admin/note/delete/<note_id>', methods=['POST'])
@admin_required
def admin_delete_note(note_id):
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], note['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    query("DELETE FROM notes WHERE id = ?", (note_id,), fetch='none')
    return jsonify({'success': True})


@app.route('/admin/note/edit/<note_id>', methods=['POST'])
@admin_required
def admin_edit_note(note_id):
    data = request.get_json()
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    query(
        """UPDATE notes
           SET title=?, subject=?, description=?, uploader=?
           WHERE id=?""",
        (
            data.get('title',       note['title']),
            data.get('subject',     note['subject']),
            data.get('description', note['description']),
            data.get('uploader',    note['uploader']),
            note_id,
        ),
        fetch='none'
    )
    return jsonify({'success': True})


@app.route('/admin/settings/save', methods=['POST'])
@admin_required
def admin_save_settings():
    data = request.get_json()

    EDITABLE = [
        'site_title', 'site_tagline', 'hero_heading', 'hero_sub',
        'contact_name', 'contact_role', 'contact_email',
        'contact_phone', 'contact_linkedin',
        'footer_text', 'primary_color',
        'show_downloads', 'allow_uploads',
    ]
    for key in EDITABLE:
        if key in data:
            save_setting(key, data[key])

    # Credentials change
    if data.get('new_password') or data.get('new_username'):
        current = data.get('current_password', '')
        s = load_settings()
        if current != s.get('admin_password', 'admin'):
            return jsonify({'error': 'Current password is incorrect!'}), 400
            
        if data.get('new_password'):
            if len(data['new_password']) < 6:
                return jsonify({'error': 'Password must be at least 6 characters!'}), 400
            save_setting('admin_password', data['new_password'])
            
        if data.get('new_username'):
            save_setting('admin_username', data['new_username'])

    return jsonify({'success': True})


@app.route('/admin/api/stats')
@admin_required
def admin_stats():
    notes = load_notes()
    return jsonify({
        'total':    len(notes),
        'total_dl': sum(n.get('downloads', 0) for n in notes),
        'subjects': list({n['subject'] for n in notes}),
    })


# ── Initialization ──────────────────────────────────────────────
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
init_db()

# ── Entry point ───────────────────────────────────────────────
if __name__ == '__main__':
    print("\n[+] NoteShare (SQLite) is running!")
    print("   [+] Website  ->  http://localhost:5000")
    print("   [+] Admin    ->  http://localhost:5000/admin/login")
    print("   [+] Database ->  SQLite .  noteshare.db\n")
    app.run(debug=True, port=5000)
