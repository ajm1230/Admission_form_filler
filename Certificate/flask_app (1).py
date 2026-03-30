"""
Nucleus Public School — Certificate Generator Backend
PythonAnywhere: Abc12302.pythonanywhere.com
Path: /home/Abc12302/mysite/flask_app.py
"""

import os
import json
import zipfile
import io
import re
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*", methods=["GET","POST","PUT","DELETE","OPTIONS"],
     allow_headers=["Content-Type","Authorization"])

# ── Paths ──────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STUDENTS_DIR  = os.path.join(BASE_DIR, 'students')
GENERATED_DIR = os.path.join(BASE_DIR, 'generated')
CERT_TEMPLATE = os.path.join(BASE_DIR, 'certificate.png')

os.makedirs(STUDENTS_DIR,  exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# ── Certificate coordinates (confirmed correct for this template) ──
# All positions are (x, y) for PIL draw.text on the original certificate.png
CERT_COORDS = {
    'name'       : (450, 323),
    'class'      : (310, 387),   # current class number
    'promoted'   : (707, 387),   # promoted-to class number
    'rank'       : (567, 440),
    'grade'      : (748, 440),
    'remark'     : (470, 490),
    'session'    : (980, 385),
}

# ── Font paths ──────────────────────────────────────────────────
# All three confirmed present on PythonAnywhere free tier (DejaVu family)
FONT_PATHS = {
    'bold'   : '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'regular': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    'italic' : '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf',
}

# ── Helpers ────────────────────────────────────────────────────
def sanitize(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '', name.replace(' ', '_'))

def unique_4digit() -> str:
    import random
    return str(random.randint(1000, 9999))

def student_dir(class_num: str, name: str) -> tuple:
    """Returns (dir_path, folder_name). Always creates a NEW unique folder.
    Never reuses - so two students with the same name each get their own folder."""
    sfile    = sanitize(name)
    cls_path = os.path.join(STUDENTS_DIR, f'class-{class_num}')
    os.makedirs(cls_path, exist_ok=True)
    existing_folders = set(os.listdir(cls_path))
    for _ in range(100):
        folder_name = f'{sfile}-{unique_4digit()}'
        if folder_name not in existing_folders:
            break
    d = os.path.join(cls_path, folder_name)
    os.makedirs(d, exist_ok=True)
    return d, folder_name

def load_font(style='bold', size=35):
    """
    Load a DejaVu TrueType font — confirmed available on PythonAnywhere free tier.
    NO silent fallback: raises clearly if font file is missing so the real
    error shows in the log instead of silently using PIL's tiny bitmap font.
    """
    from PIL import ImageFont
    path = FONT_PATHS.get(style, FONT_PATHS['bold'])
    if not os.path.exists(path):
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(path, size)

# ── CORS preflight ──────────────────────────────────────────────
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        from flask import Response
        r = Response()
        r.headers['Access-Control-Allow-Origin']  = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return r, 200

# ── Health ──────────────────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'server': 'Nucleus Certificate Generator'})

# ── Generate Certificate (PIL server-side) ──────────────────────
@app.route('/generate_certificate', methods=['POST', 'OPTIONS'])
def generate_certificate():
    """
    Accepts JSON: { studentName, class, rank, grade, promotedTo, remark, session }
    Draws text on certificate.png using PIL.
    Font: DejaVuSans-Bold / DejaVuSerif-Italic (confirmed on PythonAnywhere)
    Sizes:
      name          → 35  DejaVuSans-Bold
      class/promoted/rank/grade/session → 30  DejaVuSans-Bold
      remark        → 30  DejaVuSerif-Italic
    Returns: { status, imageUrl, filename }
    """
    try:
        from PIL import Image, ImageDraw

        data         = request.json or {}
        student_name = data.get('studentName', '').strip()
        class_num    = str(data.get('class', '')).strip()
        rank         = str(data.get('rank', '')).strip()
        grade        = str(data.get('grade', '')).strip()
        promoted_to  = str(data.get('promotedTo', '')).strip()
        remark       = str(data.get('remark', '')).strip()
        session      = str(data.get('session', '2025-26')).strip()

        if not student_name:
            return jsonify({'status': 'error', 'message': 'studentName is required'}), 400
        if not os.path.exists(CERT_TEMPLATE):
            return jsonify({'status': 'error',
                            'message': f'certificate.png not found at {CERT_TEMPLATE}'}), 500

        # Load template
        img  = Image.open(CERT_TEMPLATE).convert('RGB')
        draw = ImageDraw.Draw(img)

        # ── Fonts ────────────────────────────────────────────────
        font_name   = load_font('bold',   35)   # student name
        font_fields = load_font('bold',   30)   # class, rank, grade, session
        font_remark = load_font('italic', 24)   # remark line

        text_color = (0, 0, 0)

        # Draw each field
        draw.text(CERT_COORDS['name'],     student_name,         fill=text_color, font=font_name)
        draw.text(CERT_COORDS['class'],    class_num,            fill=text_color, font=font_fields)
        draw.text(CERT_COORDS['promoted'], promoted_to,          fill=text_color, font=font_fields)
        draw.text(CERT_COORDS['rank'],     rank_ordinal(rank),   fill=text_color, font=font_fields)
        draw.text(CERT_COORDS['grade'],    grade,                fill=text_color, font=font_fields)
        draw.text(CERT_COORDS['remark'],   remark,               fill=text_color, font=font_remark)
        draw.text(CERT_COORDS['session'],  session,              fill=text_color, font=font_fields)

        # Save to /students/class-{N}/{sanitized_name}-XXXX/{sanitized_name}.png+json
        sfile              = sanitize(student_name)
        sdir_out, foldname = student_dir(class_num, student_name)
        img_out  = os.path.join(sdir_out, sfile + '.png')
        json_out = os.path.join(sdir_out, sfile + '.json')

        img.save(img_out, 'PNG', quality=95)

        record = {
            'studentName' : student_name,
            'class'       : class_num,
            'promotedTo'  : promoted_to,
            'rank'        : rank,
            'grade'       : grade,
            'remark'      : remark,
            'session'     : session,
            'folder'      : foldname,
            'filename'    : sfile + '.png',
            'generatedAt' : datetime.utcnow().isoformat() + 'Z',
        }
        with open(json_out, 'w') as f:
            json.dump(record, f, indent=2)

        img_url = f'/students/class-{class_num}/{foldname}/{sfile}.png'
        return jsonify({
            'status'   : 'ok',
            'message'  : f'{student_name} certificate generated',
            'imageUrl' : img_url,
            'filename' : sfile + '.png',
            'folder'   : foldname,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


def rank_ordinal(rank: str) -> str:
    """Convert rank number to ordinal string: 1 → 1st, 2 → 2nd etc."""
    try:
        r = int(rank)
        if 11 <= (r % 100) <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(r % 10, 'th')
        return f'{r}{suffix}'
    except Exception:
        return rank


# ── Serve generated certificates ────────────────────────────────
@app.route('/generated/<path:filename>')
def serve_generated(filename):
    return send_from_directory(GENERATED_DIR, filename)


# ── List Generated Certificates ─────────────────────────────────
@app.route('/list_certificates')
def list_certificates():
    """Returns a list of all generated certificate JSON records."""
    records = []
    try:
        for fname in sorted(os.listdir(GENERATED_DIR), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(GENERATED_DIR, fname)
                with open(fpath) as f:
                    data = json.load(f)
                img_name = fname.replace('.json', '.png')
                data['hasImage'] = os.path.exists(os.path.join(GENERATED_DIR, img_name))
                data['imageUrl'] = f'/generated/{img_name}'
                records.append(data)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'ok', 'certificates': records})


# ── Upload Certificate (legacy — keeps old flow working) ────────
@app.route('/upload_certificate', methods=['POST', 'OPTIONS'])
def upload_certificate():
    try:
        student_name = request.form.get('studentName', 'Unknown')
        class_num    = request.form.get('class', '0').replace('th','').replace('st','').replace('nd','').replace('rd','').strip()
        json_str     = request.form.get('json', '{}')
        student_data = json.loads(json_str)

        sdir, _ = student_dir(class_num, student_name)
        sfile = sanitize(student_name)

        json_path = os.path.join(sdir, sfile + '.json')
        student_data['generatedAt'] = datetime.utcnow().isoformat() + 'Z'
        with open(json_path, 'w') as f:
            json.dump(student_data, f, indent=2)

        if 'image' in request.files:
            img = request.files['image']
            img.save(os.path.join(sdir, sfile + '.png'))

        return jsonify({
            'status' : 'ok',
            'message': f'{student_name} uploaded successfully',
            'path'   : f'/students/class-{class_num}/{sfile}/',
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── List Students (legacy) ──────────────────────────────────────
@app.route('/list_students')
def list_students():
    students = []
    classes  = []
    if not os.path.exists(STUDENTS_DIR):
        return jsonify({'students': [], 'classes': []})
    for cls_folder in sorted(os.listdir(STUDENTS_DIR)):
        if not cls_folder.startswith('class-'):
            continue
        class_num = cls_folder.replace('class-', '')
        classes.append(class_num)
        cls_path = os.path.join(STUDENTS_DIR, cls_folder)
        for student_folder in sorted(os.listdir(cls_path)):
            student_path = os.path.join(cls_path, student_folder)
            if not os.path.isdir(student_path):
                continue
            base_name    = student_folder.rsplit('-', 1)[0] if '-' in student_folder else student_folder
            json_path    = os.path.join(student_path, base_name + '.json')
            img_path     = os.path.join(student_path, base_name + '.png')
            if not os.path.exists(json_path):
                continue
            with open(json_path) as f:
                data = json.load(f)
            cls_folder_name = f'class-{class_num}'
            img_url = f'/students/{cls_folder_name}/{student_folder}/{base_name}.png'
            students.append({
                **data,
                'class'     : class_num,
                'hasImage'  : os.path.exists(img_path),
                'folderName': student_folder,
                'imageUrl'  : img_url,
            })
    return jsonify({'students': students, 'classes': sorted(set(classes))})


# ── Serve student files ─────────────────────────────────────────
@app.route('/students/<path:filename>')
def serve_student_file(filename):
    return send_from_directory(STUDENTS_DIR, filename)


# ── Download ────────────────────────────────────────────────────
@app.route('/download_all')
def download_all():
    file_type = request.args.get('type', 'all')
    return _zip_directory(GENERATED_DIR, 'all_certificates', file_type)

@app.route('/download_class')
def download_class():
    class_num = request.args.get('class', '')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(GENERATED_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(GENERATED_DIR, fname)
            with open(fpath) as f:
                d = json.load(f)
            if str(d.get('class', '')) == str(class_num):
                img_name = fname.replace('.json', '.png')
                img_path = os.path.join(GENERATED_DIR, img_name)
                if os.path.exists(img_path):
                    zf.write(img_path, img_name)
                zf.write(fpath, fname)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'class_{class_num}_certificates.zip')

def _zip_directory(directory: str, zipname: str, file_type: str):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(directory):
            for file in files:
                fpath   = os.path.join(root, file)
                arcname = os.path.relpath(fpath, directory)
                if _should_include(file, file_type):
                    zf.write(fpath, arcname)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'{zipname}.zip')

def _should_include(filename: str, file_type: str) -> bool:
    if file_type == 'all'  : return True
    if file_type == 'img'  : return filename.endswith('.png') or filename.endswith('.jpg')
    if file_type == 'json' : return filename.endswith('.json')
    return True


# ── Job Status ──────────────────────────────────────────────────
JOB_STATUS = {}

@app.route('/job_status')
def job_status():
    return jsonify({'jobs': list(JOB_STATUS.values())})

@app.route('/update_job', methods=['POST', 'OPTIONS'])
def update_job():
    data   = request.json or {}
    job_id = data.get('id')
    if job_id:
        JOB_STATUS[job_id] = data
    return jsonify({'status': 'ok'})


# ── Root ────────────────────────────────────────────────────────
@app.route('/')
def index():
    return jsonify({
        'app'      : 'Nucleus Public School Certificate Generator',
        'version'  : '3.0',
        'endpoints': [
            'GET  /health',
            'POST /generate_certificate',
            'GET  /list_certificates',
            'GET  /generated/<filename>',
            'GET  /download_all',
            'GET  /download_class?class=8',
            'POST /upload_certificate  (legacy)',
            'GET  /list_students       (legacy)',
            'GET  /job_status',
        ]
    })

if __name__ == '__main__':
    app.run(debug=True)
