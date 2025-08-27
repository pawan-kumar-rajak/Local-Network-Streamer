# import os
# from flask import Flask, render_template, request, send_from_directory, Response, jsonify, abort, session, redirect, url_for
# import ffmpeg
# import secrets
# from functools import wraps
# import logging
# from logging.handlers import QueueHandler
# import subprocess
# import sys

# # --- Configuration ---
# BASE_DIR = os.path.expanduser('~')
# FFMPEG_PATH = 'ffmpeg'
# FFPROBE_PATH = 'ffprobe'
# SERVER_CONFIG = {}

# # --- Flask App Initialization ---
# app = Flask(__name__)
# app.config['SECRET_KEY'] = secrets.token_hex(16)

# def set_ffmpeg_path(ffmpeg_exec, ffprobe_exec):
#     global FFMPEG_PATH, FFPROBE_PATH
#     FFMPEG_PATH = ffmpeg_exec
#     FFPROBE_PATH = ffprobe_exec

# # --- Authentication and Path Validation ---
# def auth_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if not session.get('username'):
#             if SERVER_CONFIG.get('mode') == 'users':
#                 return redirect(url_for('login'))
#             abort(403)
#         return f(*args, **kwargs)
#     return decorated_function

# def get_real_path_from_virtual(virtual_path):
#     if not virtual_path: return None
#     parts = virtual_path.replace('/', os.sep).split(os.sep)
#     root_folder_name = parts[0]
#     sub_path = os.path.join(*parts[1:]) if len(parts) > 1 else ""
#     folder_map = session.get('folder_map', {})
#     real_base_path = folder_map.get(root_folder_name)
#     if not real_base_path: return None
#     full_path = os.path.abspath(os.path.join(real_base_path, sub_path))
#     if os.path.commonpath([full_path, real_base_path]) != os.path.normpath(real_base_path):
#         logging.error(f"SECURITY ALERT: Path traversal attempt by '{session.get('username')}' to '{full_path}'")
#         return None
#     return full_path

# # --- Helper Functions ---
# def get_directory_contents(path):
#     items = {'folders': [], 'files': []}
#     try:
#         for item in os.listdir(path):
#             item_path = os.path.join(path, item)
#             if os.path.isdir(item_path): items['folders'].append(item)
#             else: items['files'].append(item)
#     except PermissionError:
#         logging.warning(f"Permission denied for directory: {path}"); return "ACCESS_DENIED"
#     except OSError as e: 
#         logging.error(f"Could not read directory {path}: {e}"); return None
#     items['folders'].sort(); items['files'].sort()
#     return items

# def get_breadcrumbs(virtual_path):
#     if not virtual_path: return []
#     breadcrumbs, current_path = [], ''
#     parts = virtual_path.split('/')
#     for part in parts:
#         current_path = f"{current_path}/{part}" if current_path else part
#         breadcrumbs.append({'name': part, 'path': current_path})
#     return breadcrumbs

# def is_path_safe(path):
#     return os.path.abspath(path).startswith(os.path.abspath(BASE_DIR))


# # --- Routes ---

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if SERVER_CONFIG.get('mode') != 'users':
#         return "Login is not enabled in the current server mode.", 404
#     if request.method == 'POST':
#         username = request.form.get('username'); password = request.form.get('password')
#         user_data = SERVER_CONFIG.get('permissions', {}).get('users', {}).get(username)
#         if user_data and user_data.get('password') == password:
#             session['username'] = username
#             session['folder_map'] = {os.path.basename(p): p for p in user_data.get('allowed_folders', [])}
#             logging.info(f"User '{username}' logged in successfully.")
#             return redirect(url_for('index'))
#         else:
#             logging.warning(f"Failed login attempt for user '{username}'.")
#             return render_template('login.html', error="Invalid username or password")
#     return render_template('login.html')

# @app.route('/logout')
# def logout():
#     session.clear()
#     if SERVER_CONFIG.get('mode') == 'users':
#         return redirect(url_for('login'))
#     return "You have been logged out."

# @app.route('/auth/<token>')
# def auth(token):
#     server_token = SERVER_CONFIG.get('token')
#     if SERVER_CONFIG.get('mode') == 'full_access' and token == server_token:
#         session['username'] = 'admin (Full Access)'
#         session['folder_map'] = {os.path.basename(BASE_DIR): BASE_DIR}
#         return redirect(url_for('index'))
#     else:
#         abort(401)

# @app.route('/', defaults={'path': ''})
# @app.route('/<path:path>')
# @auth_required
# def index(path=""):
#     if not path:
#         virtual_folders = list(session.get('folder_map', {}).keys())
#         return render_template('index_v2.html', path="", folders=virtual_folders, files=[], base_dir_name="My Shared Folders", breadcrumbs=[])

#     full_path = get_real_path_from_virtual(path)
#     if not full_path: abort(403)
    
#     contents = get_directory_contents(full_path)
#     if contents == "ACCESS_DENIED":
#         error_message = f"Access is denied to the directory: {path}"
#         return render_template('index_v2.html', path=path, folders=[], files=[], base_dir_name="My Shared Folders", breadcrumbs=get_breadcrumbs(path), error_message=error_message)
#     if contents is None: abort(500)
    
#     return render_template('index_v2.html', path=path, **contents, base_dir_name="My Shared Folders", breadcrumbs=get_breadcrumbs(path))

# @app.route('/media_info/<path:filepath>')
# @auth_required
# def media_info(filepath):
#     full_path = get_real_path_from_virtual(filepath)
#     if not full_path or not os.path.isfile(full_path): abort(404)
#     try:
#         probe = ffmpeg.probe(full_path, cmd=FFPROBE_PATH); audio_streams, subtitle_streams = [], []
#         for stream in probe.get('streams', []):
#             tags = stream.get('tags', {}); lang = tags.get('language', 'und'); title = tags.get('title', f"Track {stream['index']}")
#             if stream.get('codec_type') == 'audio': audio_streams.append({'index': stream['index'], 'language': lang, 'title': title})
#             elif stream.get('codec_type') == 'subtitle':
#                 codec = stream.get('codec_name', 'unknown'); is_text_based = codec in ['subrip', 'srt', 'ass', 'webvtt', 'mov_text']
#                 subtitle_streams.append({'index': stream['index'], 'language': lang, 'title': title, 'codec': codec, 'is_text_based': is_text_based})
#         return jsonify({'audio': audio_streams, 'subtitles': subtitle_streams})
#     except ffmpeg.Error as e:
#         logging.error(f"FFPROBE ERROR: {e.stderr.decode()}"); return jsonify({'error': 'Could not probe file.'}), 500

# @app.route('/subtitle/<int:track_index>/<path:filepath>')
# def serve_subtitle(track_index, filepath):
#     safe_os_path = filepath.replace('/', os.sep); full_path = os.path.join(BASE_DIR, safe_os_path)
#     if not is_path_safe(full_path) or not os.path.isfile(full_path): abort(404)
#     try:
#         out, err = ffmpeg.input(full_path).output('pipe:', f='webvtt', map=f'0:{track_index}').run(capture_stdout=True, capture_stderr=True, cmd=FFMPEG_PATH)
#         if err: logging.warning(f"FFMPEG SUBTITLE WARNING: {err.decode()}")
#         return Response(out, mimetype='text/vtt')
#     except ffmpeg.Error as e:
#         error_message = e.stderr.decode(); logging.error(f"FFMPEG SUBTITLE FATAL ERROR: {error_message}"); abort(500)


# @app.route('/stream/<path:filepath>')
# def stream_video(filepath):
#     full_path = get_real_path_from_virtual(filepath)
#     if not full_path or not os.path.isfile(full_path): abort(404)
#     audio_track_index = request.args.get('audio_track', None)
#     if not audio_track_index: return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
#     try:
#         probe = ffmpeg.probe(full_path, cmd=FFPROBE_PATH); streams = probe['streams']
#         video_stream = next((s for s in streams if s['codec_type'] == 'video'), None)
#         audio_stream = next((s for s in streams if s['codec_type'] == 'audio' and str(s['index']) == audio_track_index), None)
#         if not video_stream or not audio_stream: abort(500)
#         ffmpeg_input = ffmpeg.input(full_path)
#         process = ffmpeg.output(ffmpeg_input[str(video_stream['index'])], ffmpeg_input[str(audio_stream['index'])], 'pipe:', f='mp4', vcodec='copy', acodec='copy', movflags='frag_keyframe+empty_moov').run_async(pipe_stdout=True, pipe_stderr=True, cmd=FFMPEG_PATH)
#         def generate():
#             for chunk in iter(lambda: process.stdout.read(8192), b''): yield chunk
#         return Response(generate(), mimetype='video/mp4')
#     except ffmpeg.Error as e:
#         logging.error(f"FFMPEG STREAMING ERROR: {e.stderr.decode()}"); return abort(500)

# @app.route('/download/<path:filepath>')
# @auth_required
# def download_file(filepath):
#     full_path = get_real_path_from_virtual(filepath)
#     if not full_path or not os.path.isfile(full_path): abort(404)
#     return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), as_attachment=True)

# @app.route('/view/<path:filepath>')
# @auth_required
# def view_file(filepath):
#     full_path = get_real_path_from_virtual(filepath)
#     if not full_path or not os.path.isfile(full_path): abort(404)
#     return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

# @app.route('/open', methods=['POST'])
# @auth_required
# def open_file():
#     filepath = request.get_json().get('path')
#     full_path = get_real_path_from_virtual(filepath)
#     if not full_path: return jsonify({'status': 'error', 'message': 'Access Denied.'}), 403
#     try:
#         if sys.platform == "win32": os.startfile(full_path)
#         else: subprocess.call(["open" if sys.platform == "darwin" else "xdg-open", full_path])
#         return jsonify({'status': 'success', 'message': f'Launched {os.path.basename(full_path)}'})
#     except Exception as e: 
#         logging.error(f"Failed to open file {full_path}: {e}"); return jsonify({'status': 'error', 'message': f'Failed to open file: {str(e)}'}), 500

# def start_server_process(log_queue, host, port, server_config):
#     global SERVER_CONFIG
#     SERVER_CONFIG = server_config
#     queue_handler = QueueHandler(log_queue)
#     root_logger = logging.getLogger()
#     if root_logger.hasHandlers(): root_logger.handlers.clear()
#     root_logger.addHandler(queue_handler); root_logger.setLevel(logging.INFO)
#     from waitress import serve
#     serve(app, host=host, port=port)


import os
from flask import Flask, render_template, request, send_from_directory, Response, jsonify, abort, session, redirect, url_for
import ffmpeg
import secrets
from functools import wraps
import logging
from logging.handlers import QueueHandler
import subprocess
import sys

# --- Configuration ---
BASE_DIR = os.path.expanduser('~')
FFMPEG_PATH = 'ffmpeg'
FFPROBE_PATH = 'ffprobe'
SERVER_CONFIG = {}

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

def set_ffmpeg_path(ffmpeg_exec, ffprobe_exec):
    global FFMPEG_PATH, FFPROBE_PATH
    FFMPEG_PATH = ffmpeg_exec
    FFPROBE_PATH = ffprobe_exec

# --- Authentication and Path Validation ---
def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('username'):
            if SERVER_CONFIG.get('mode') == 'users':
                return redirect(url_for('login'))
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def get_real_path_from_virtual(virtual_path):
    if not virtual_path: return None
    parts = virtual_path.replace('/', os.sep).split(os.sep)
    root_folder_name = parts[0]
    sub_path = os.path.join(*parts[1:]) if len(parts) > 1 else ""
    folder_map = session.get('folder_map', {})
    real_base_path = folder_map.get(root_folder_name)
    if not real_base_path: return None
    full_path = os.path.abspath(os.path.join(real_base_path, sub_path))
    if os.path.commonpath([full_path, real_base_path]) != os.path.normpath(real_base_path):
        logging.error(f"SECURITY ALERT: Path traversal attempt by '{session.get('username')}' to '{full_path}'")
        return None
    return full_path

# --- Helper Functions ---
def get_directory_contents(path):
    items = {'folders': [], 'files': []}
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path): items['folders'].append(item)
            else: items['files'].append(item)
    except PermissionError:
        logging.warning(f"Permission denied for directory: {path}"); return "ACCESS_DENIED"
    except OSError as e: 
        logging.error(f"Could not read directory {path}: {e}"); return None
    items['folders'].sort(); items['files'].sort()
    return items

def get_breadcrumbs(virtual_path):
    if not virtual_path: return []
    breadcrumbs, current_path = [], ''
    parts = virtual_path.split('/')
    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part
        breadcrumbs.append({'name': part, 'path': current_path})
    return breadcrumbs

def get_creation_flags():
    """Returns flags to prevent console window pop-ups on Windows."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if SERVER_CONFIG.get('mode') != 'users':
        return "Login is not enabled in the current server mode.", 404
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        user_data = SERVER_CONFIG.get('permissions', {}).get('users', {}).get(username)
        if user_data and user_data.get('password') == password:
            session['username'] = username
            session['folder_map'] = {os.path.basename(p): p for p in user_data.get('allowed_folders', [])}
            logging.info(f"User '{username}' logged in successfully.")
            return redirect(url_for('index'))
        else:
            logging.warning(f"Failed login attempt for user '{username}'.")
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    if SERVER_CONFIG.get('mode') == 'users':
        return redirect(url_for('login'))
    return "You have been logged out."

@app.route('/auth/<token>')
def auth(token):
    server_token = SERVER_CONFIG.get('token')
    if SERVER_CONFIG.get('mode') == 'full_access' and token == server_token:
        session['username'] = 'admin (Full Access)'
        session['folder_map'] = {os.path.basename(BASE_DIR): BASE_DIR}
        return redirect(url_for('index'))
    else:
        abort(401)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
@auth_required
def index(path=""):
    if not path:
        virtual_folders = list(session.get('folder_map', {}).keys())
        return render_template('index_v2.html', path="", folders=virtual_folders, files=[], base_dir_name="My Shared Folders", breadcrumbs=[])

    full_path = get_real_path_from_virtual(path)
    if not full_path: abort(403)
    
    contents = get_directory_contents(full_path)
    if contents == "ACCESS_DENIED":
        error_message = f"Access is denied to the directory: {path}"
        return render_template('index_v2.html', path=path, folders=[], files=[], base_dir_name="My Shared Folders", breadcrumbs=get_breadcrumbs(path), error_message=error_message)
    if contents is None: abort(500)
    
    return render_template('index_v2.html', path=path, **contents, base_dir_name="My Shared Folders", breadcrumbs=get_breadcrumbs(path))

@app.route('/media_info/<path:filepath>')
@auth_required
def media_info(filepath):
    full_path = get_real_path_from_virtual(filepath)
    if not full_path or not os.path.isfile(full_path): abort(404)
    try:
        probe = ffmpeg.probe(full_path, cmd=FFPROBE_PATH); audio_streams, subtitle_streams = [], []
        for stream in probe.get('streams', []):
            tags = stream.get('tags', {}); lang = tags.get('language', 'und'); title = tags.get('title', f"Track {stream['index']}")
            if stream.get('codec_type') == 'audio': audio_streams.append({'index': stream['index'], 'language': lang, 'title': title})
            elif stream.get('codec_type') == 'subtitle':
                codec = stream.get('codec_name', 'unknown'); is_text_based = codec in ['subrip', 'srt', 'ass', 'webvtt', 'mov_text']
                subtitle_streams.append({'index': stream['index'], 'language': lang, 'title': title, 'codec': codec, 'is_text_based': is_text_based})
        return jsonify({'audio': audio_streams, 'subtitles': subtitle_streams})
    except ffmpeg.Error as e:
        logging.error(f"FFPROBE ERROR: {e.stderr.decode()}"); return jsonify({'error': 'Could not probe file.'}), 500

@app.route('/stream/<path:filepath>')
@auth_required
def stream_video(filepath):
    full_path = get_real_path_from_virtual(filepath)
    if not full_path or not os.path.isfile(full_path): abort(404)
    audio_track_index = request.args.get('audio_track', None)
    if not audio_track_index: return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
    try:
        probe = ffmpeg.probe(full_path, cmd=FFPROBE_PATH); streams = probe['streams']
        video_stream = next((s for s in streams if s['codec_type'] == 'video'), None)
        audio_stream = next((s for s in streams if s['codec_type'] == 'audio' and str(s['index']) == audio_track_index), None)
        if not video_stream or not audio_stream: abort(500)
        
        # --- FIX: Use subprocess.Popen directly to control creation flags ---
        args = (
            ffmpeg
            .input(full_path)
            .output(
                'pipe:', 
                map=[f"0:{video_stream['index']}", f"0:{audio_stream['index']}"],
                f='mp4', 
                vcodec='copy', 
                acodec='copy', 
                movflags='frag_keyframe+empty_moov'
            )
            .compile(cmd=FFMPEG_PATH, overwrite_output=True)
        )
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=get_creation_flags())
        
        def generate():
            for chunk in iter(lambda: process.stdout.read(8192), b''):
                yield chunk
        return Response(generate(), mimetype='video/mp4')
    except ffmpeg.Error as e:
        logging.error(f"FFMPEG STREAMING ERROR: {e.stderr.decode()}"); return abort(500)

@app.route('/subtitle/<int:track_index>/<path:filepath>')
@auth_required
def serve_subtitle(track_index, filepath):
    full_path = get_real_path_from_virtual(filepath)
    if not full_path or not os.path.isfile(full_path): abort(404)
    try:
        # --- FIX: Use subprocess.run directly to control creation flags ---
        args = (
            ffmpeg
            .input(full_path)
            .output('pipe:', f='webvtt', map=f'0:{track_index}')
            .compile(cmd=FFMPEG_PATH, overwrite_output=True)
        )
        result = subprocess.run(args, capture_output=True, creationflags=get_creation_flags())
        
        if result.stderr: logging.warning(f"FFMPEG SUBTITLE WARNING: {result.stderr.decode()}")
        return Response(result.stdout, mimetype='text/vtt')
    except ffmpeg.Error as e:
        logging.error(f"FFMPEG SUBTITLE FATAL ERROR: {e.stderr.decode()}"); abort(500)


@app.route('/download/<path:filepath>')
@auth_required
def download_file(filepath):
    full_path = get_real_path_from_virtual(filepath)
    if not full_path or not os.path.isfile(full_path): abort(404)
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), as_attachment=True)

@app.route('/view/<path:filepath>')
@auth_required
def view_file(filepath):
    full_path = get_real_path_from_virtual(filepath)
    if not full_path or not os.path.isfile(full_path): abort(404)
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

@app.route('/open', methods=['POST'])
@auth_required
def open_file():
    filepath = request.get_json().get('path')
    full_path = get_real_path_from_virtual(filepath)
    if not full_path: return jsonify({'status': 'error', 'message': 'Access Denied.'}), 403
    try:
        if sys.platform == "win32": os.startfile(full_path)
        else: subprocess.call(["open" if sys.platform == "darwin" else "xdg-open", full_path])
        return jsonify({'status': 'success', 'message': f'Launched {os.path.basename(full_path)}'})
    except Exception as e: 
        logging.error(f"Failed to open file {full_path}: {e}"); return jsonify({'status': 'error', 'message': f'Failed to open file: {str(e)}'}), 500

def start_server_process(log_queue, host, port, server_config):
    global SERVER_CONFIG
    SERVER_CONFIG = server_config
    queue_handler = QueueHandler(log_queue)
    root_logger = logging.getLogger()
    if root_logger.hasHandlers(): root_logger.handlers.clear()
    root_logger.addHandler(queue_handler); root_logger.setLevel(logging.INFO)
    from waitress import serve
    serve(app, host=host, port=port)
