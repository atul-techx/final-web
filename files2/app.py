"""
NoteShare v2 — Flask + MySQL
Features:
  - Upload goes to 'pending' → admin approves → then visible
  - Multiple admin accounts (superadmin can add/remove admins)
  - Admin panel hidden: access only via /admin/login?key=<secret>
  - Floating admin FAB removed from homepage
"""

from flask import (
    Flask, request, jsonify, render_template,
    send_from_directory, session, redirect, url_for
)
import os, uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error
from functools import wraps

# ── App config ────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'noteshare_v2_secret_key_change_me_2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024   # 50 MB

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'pptx',}

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

# ── MySQL config ──────────────────────────────────────────────
DB_CONFIG = {
    'host':       'localhost',
    'port':       3306,
    'user':       'root',
    'password':   'Drop_717',      # ← change if needed
    'database':   'noteshare',
    'charset':    'utf8mb4',
    'autocommit': True,
}

# ── DB helper ─────────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def query(sql, params=(), fetch='all'):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        if fetch == 'all':   return cur.fetchall()
        if fetch == 'one':   return cur.fetchone()
        conn.commit();       return None
    except Error as e:
        print(f"[DB ERROR] {e}")
        raise
    finally:
        conn.close()

# ── Settings ──────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    'site_title':       'NoteShare',
    'site_tagline':     'Collaborative Learning Platform',
    'hero_heading':     'Share notes. Learn faster. Together.',
    'hero_sub':         'Upload your study notes, discover what peers have shared.',
    'footer_text':      'Made with ♥ by Utkarsh, Sachin, Rohit & Naitik',
    'primary_color':    '#e0217a',
    'allow_uploads':    'true',
    'show_downloads':   'true',
    'admin_secret_key': 'noteshare_admin_2026',
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
    s['allow_uploads']  = str(s.get('allow_uploads',  'true')).lower() == 'true'
    s['show_downloads'] = str(s.get('show_downloads', 'true')).lower() == 'true'
    return s

def save_setting(key, value):
    query(
        "INSERT INTO settings (`key`,`value`) VALUES (%s,%s) "
        "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`)",
        (key, str(value)), fetch='none'
    )

# ── Notes helpers ─────────────────────────────────────────────
def load_notes(subject=None, status='approved'):
    """Load notes filtered by status. Public sees only approved."""
    if subject and subject != 'All':
        rows = query(
            "SELECT * FROM notes WHERE subject=%s AND status=%s ORDER BY uploaded_at DESC",
            (subject, status)
        )
    else:
        rows = query(
            "SELECT * FROM notes WHERE status=%s ORDER BY uploaded_at DESC",
            (status,)
        )
    for r in rows:
        if isinstance(r['uploaded_at'], datetime):
            r['uploaded_at'] = r['uploaded_at'].strftime('%d %b %Y, %I:%M %p')
        if r.get('reviewed_at') and isinstance(r['reviewed_at'], datetime):
            r['reviewed_at'] = r['reviewed_at'].strftime('%d %b %Y, %I:%M %p')
    return rows

def load_all_notes_admin():
    """Admin sees all notes with status."""
    rows = query("SELECT * FROM notes ORDER BY uploaded_at DESC")
    for r in rows:
        if isinstance(r['uploaded_at'], datetime):
            r['uploaded_at'] = r['uploaded_at'].strftime('%d %b %Y, %I:%M %p')
    return rows

def get_note_by_id(note_id):
    row = query("SELECT * FROM notes WHERE id=%s", (note_id,), fetch='one')
    if row and isinstance(row['uploaded_at'], datetime):
        row['uploaded_at'] = row['uploaded_at'].strftime('%d %b %Y, %I:%M %p')
    return row

def pending_count():
    row = query("SELECT COUNT(*) AS cnt FROM notes WHERE status='pending'", fetch='one')
    return row['cnt'] if row else 0

# ── Admin auth helpers ────────────────────────────────────────
def get_admin(username):
    return query("SELECT * FROM admins WHERE username=%s", (username,), fetch='one')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        if session.get('admin_role') != 'superadmin':
            return jsonify({'error': 'Superadmin access required'}), 403
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        return jsonify({'error': 'Uploads are currently disabled.'}), 403

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
    size_str  = (f"{file_size//1024} KB" if file_size < 1024*1024
                 else f"{file_size//(1024*1024)} MB")

    note_id    = uuid.uuid4().hex
    note_title = title or secure_filename(file.filename)

    # Status = 'pending' → needs admin approval
    query(
        """INSERT INTO notes
           (id,title,subject,description,uploader,
            filename,original_name,ext,size,downloads,status,uploaded_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,'pending',NOW())""",
        (note_id, note_title, subject,
         description or f"Notes on {subject}",
         uploader, unique_name, file.filename, ext, size_str),
        fetch='none'
    )

    return jsonify({
        'success': True,
        'pending': True,
        'message': '✅ Your note has been submitted! It will appear after admin approval.'
    })

@app.route('/download/<filename>')
def download_file(filename):
    # Only allow download of approved notes
    note = query("SELECT * FROM notes WHERE filename=%s AND status='approved'",
                 (filename,), fetch='one')
    if not note:
        return "File not available", 404

    query("UPDATE notes SET downloads=downloads+1 WHERE filename=%s",
          (filename,), fetch='none')
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/api/notes')
def api_notes():
    subject = request.args.get('subject', '')
    notes   = load_notes(subject, status='approved')
    return jsonify(notes)

# ── Admin Login (Secret Key Protected) ───────────────────────
# Access URL: /admin/login?key=noteshare_admin_2026
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    # Secret key check
    s          = load_settings()
    secret_key = s.get('admin_secret_key', 'noteshare_admin_2026')
    url_key    = request.args.get('key', '')

    # Store key in session once validated via URL
    if url_key == secret_key:
        session['admin_key_ok'] = True

    if not session.get('admin_key_ok'):
        return render_template('404.html'), 404   # looks like normal 404 to outsiders

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        admin    = get_admin(username)

        if admin and admin['password'] == password:
            session['admin_logged_in'] = True
            session['admin_username']  = admin['username']
            session['admin_role']      = admin['role']
            session.permanent          = False
            # Update last login
            query("UPDATE admins SET last_login=NOW() WHERE username=%s",
                  (username,), fetch='none')
            return redirect(url_for('admin_dashboard'))
        error = 'Wrong username or password.'

    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))

# ── Admin Dashboard ───────────────────────────────────────────
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

    admins = query("SELECT id,username,role,created_at,last_login FROM admins ORDER BY id")

    return render_template('admin.html',
                           notes=notes,
                           s=s,
                           total_dl=total_dl,
                           subjects=subjects,
                           pending_count=pending,
                           admins=admins,
                           current_admin=session.get('admin_username'),
                           current_role=session.get('admin_role'))

# ── Admin: Approve / Reject note ──────────────────────────────
@app.route('/admin/note/approve/<note_id>', methods=['POST'])
@admin_required
def admin_approve_note(note_id):
    query(
        "UPDATE notes SET status='approved', reviewed_at=NOW(), reviewed_by=%s WHERE id=%s",
        (session.get('admin_username'), note_id), fetch='none'
    )
    return jsonify({'success': True})

@app.route('/admin/note/reject/<note_id>', methods=['POST'])
@admin_required
def admin_reject_note(note_id):
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Not found'}), 404

    # Delete file from disk on reject
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], note['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    query(
        "UPDATE notes SET status='rejected', reviewed_at=NOW(), reviewed_by=%s WHERE id=%s",
        (session.get('admin_username'), note_id), fetch='none'
    )
    return jsonify({'success': True})

# ── Admin: Delete note ────────────────────────────────────────
@app.route('/admin/note/delete/<note_id>', methods=['POST'])
@admin_required
def admin_delete_note(note_id):
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], note['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    query("DELETE FROM notes WHERE id=%s", (note_id,), fetch='none')
    return jsonify({'success': True})

# ── Admin: Edit note ──────────────────────────────────────────
@app.route('/admin/note/edit/<note_id>', methods=['POST'])
@admin_required
def admin_edit_note(note_id):
    data = request.get_json()
    note = get_note_by_id(note_id)
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    query(
        "UPDATE notes SET title=%s,subject=%s,description=%s,uploader=%s WHERE id=%s",
        (data.get('title', note['title']),
         data.get('subject', note['subject']),
         data.get('description', note['description']),
         data.get('uploader', note['uploader']),
         note_id),
        fetch='none'
    )
    return jsonify({'success': True})

# ── Admin: Manage Admins (superadmin only) ────────────────────
@app.route('/admin/admins/add', methods=['POST'])
@superadmin_required
def admin_add_admin():
    data     = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role     = data.get('role', 'admin')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if role not in ('admin', 'superadmin'):
        role = 'admin'

    existing = get_admin(username)
    if existing:
        return jsonify({'error': 'Username already exists'}), 400

    query(
        "INSERT INTO admins (username,password,role) VALUES (%s,%s,%s)",
        (username, password, role), fetch='none'
    )
    return jsonify({'success': True})

@app.route('/admin/admins/delete/<int:admin_id>', methods=['POST'])
@superadmin_required
def admin_delete_admin(admin_id):
    # Cannot delete yourself
    target = query("SELECT * FROM admins WHERE id=%s", (admin_id,), fetch='one')
    if not target:
        return jsonify({'error': 'Admin not found'}), 404
    if target['username'] == session.get('admin_username'):
        return jsonify({'error': 'Cannot delete your own account'}), 400

    query("DELETE FROM admins WHERE id=%s", (admin_id,), fetch='none')
    return jsonify({'success': True})

@app.route('/admin/admins/change-password', methods=['POST'])
@admin_required
def admin_change_password():
    data         = request.get_json()
    current_pw   = data.get('current_password', '')
    new_pw       = data.get('new_password', '')
    username     = session.get('admin_username')

    admin = get_admin(username)
    if not admin or admin['password'] != current_pw:
        return jsonify({'error': 'Current password is incorrect'}), 400
    if len(new_pw) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400

    query("UPDATE admins SET password=%s WHERE username=%s",
          (new_pw, username), fetch='none')
    return jsonify({'success': True})

# ── Admin: Settings ───────────────────────────────────────────
@app.route('/admin/settings/save', methods=['POST'])
@admin_required
def admin_save_settings():
    data = request.get_json()
    EDITABLE = [
        'site_title', 'site_tagline', 'hero_heading', 'hero_sub',
        'contact_name', 'contact_role', 'contact_email',
        'contact_phone', 'contact_linkedin',
        'footer_text', 'primary_color', 'show_downloads', 'allow_uploads',
    ]
    for key in EDITABLE:
        if key in data:
            save_setting(key, data[key])

    # Secret key change (superadmin only)
    if data.get('admin_secret_key') and session.get('admin_role') == 'superadmin':
        val = data['admin_secret_key'].strip()
        if len(val) >= 8:
            save_setting('admin_secret_key', val)

    return jsonify({'success': True})

@app.route('/admin/api/stats')
@admin_required
def admin_stats():
    notes = load_all_notes_admin()
    return jsonify({
        'total':    len(notes),
        'approved': len([n for n in notes if n['status'] == 'approved']),
        'pending':  len([n for n in notes if n['status'] == 'pending']),
        'rejected': len([n for n in notes if n['status'] == 'rejected']),
        'total_dl': sum(n.get('downloads', 0) for n in notes),
    })

# ── Entry point ───────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    print("\n[+] NoteShare v2 (MySQL) is running!")
    print("   [~] Website  ->  http://localhost:5000")
    print("   [!] Admin    ->  http://localhost:5000/admin/login?key=noteshare_admin_2026")
    print("   [*] Database ->  MySQL . noteshare\n")
    app.run(debug=True, port=5000)
