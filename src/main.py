import sys
import os
import socket
import qrcode
import logging
from logging.handlers import QueueHandler
import multiprocessing
import secrets
import json
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTextEdit, QGroupBox, QRadioButton, QLineEdit,
                             QListWidget, QListWidgetItem, QFileDialog, QMessageBox)
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

# --- Import server components ---
from server import set_ffmpeg_path, start_server_process

HOST = '0.0.0.0'
PORT = 8000
PERMISSIONS_FILE = 'permissions.json'

# --- Log Reader Thread ---
class LogReader(QThread):
    new_log_record = pyqtSignal(str)
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    def run(self):
        self.setTerminationEnabled(True)
        while True:
            try:
                record = self.log_queue.get();
                if record is None: break
                msg = self.formatter.format(record)
                self.new_log_record.emit(msg)
            except (EOFError, BrokenPipeError): break
            except Exception as e: print(f"Log reader error: {e}")

# --- Main Application Window ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Local File Streamer')
        self.setGeometry(100, 100, 700, 750)
        self.server_process = None
        self.log_thread = None
        
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
        else:
            icon_path = 'icon.ico'
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        self.layout = QVBoxLayout()
        self.status_label = QLabel('Server is stopped.'); self.status_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.qr_label = QLabel(); self.qr_label.setFixedSize(250, 250)
        self.start_button = QPushButton('Start Server'); self.stop_button = QPushButton('Stop Server'); self.stop_button.setEnabled(False)
        self.console = QTextEdit(); self.console.setReadOnly(True); self.console.setStyleSheet("background-color: #1E1E1E; color: #DCDCDC; font-family: Consolas, Courier New, monospace;")
        
        users_group = QGroupBox("User Management (for User Accounts Mode)")
        users_layout = QVBoxLayout()
        self.users_list = QListWidget()
        self.username_input = QLineEdit(); self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit(); self.password_input.setPlaceholderText("Password"); self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.add_user_button = QPushButton("Add User")
        self.remove_user_button = QPushButton("Remove Selected User")
        self.add_folder_button = QPushButton("Add Folder to Selected User")
        users_layout.addWidget(QLabel("Users and Allowed Folders:")); users_layout.addWidget(self.users_list)
        users_layout.addWidget(self.username_input); users_layout.addWidget(self.password_input)
        users_layout.addWidget(self.add_user_button); users_layout.addWidget(self.remove_user_button)
        users_layout.addWidget(self.add_folder_button)
        users_group.setLayout(users_layout)
        
        # --- NEW: Restored and redesigned Access Control UI ---
        access_group = QGroupBox("Access Mode")
        access_layout = QVBoxLayout()
        self.user_mode_radio = QRadioButton("User Accounts (Login Required)")
        self.full_access_radio = QRadioButton("Full Access (Admin)")
        self.user_mode_radio.setChecked(True)
        
        self.full_access_options_group = QGroupBox("Full Access Options")
        full_access_layout = QVBoxLayout()
        self.secure_qr_radio = QRadioButton("Secure QR (Recommended)")
        self.custom_code_radio = QRadioButton("Custom Code")
        self.open_radio = QRadioButton("Open for All (Public on LAN)")
        self.custom_code_input = QLineEdit()
        self.custom_code_input.setPlaceholderText("Enter a simple code (e.g., 1234)")
        self.secure_qr_radio.setChecked(True)
        full_access_layout.addWidget(self.secure_qr_radio)
        full_access_layout.addWidget(self.custom_code_radio)
        full_access_layout.addWidget(self.custom_code_input)
        full_access_layout.addWidget(self.open_radio)
        self.full_access_options_group.setLayout(full_access_layout)
        
        access_layout.addWidget(self.user_mode_radio)
        access_layout.addWidget(self.full_access_radio)
        access_layout.addWidget(self.full_access_options_group)
        access_group.setLayout(access_layout)
        
        top_layout = QHBoxLayout(); top_layout.addWidget(self.qr_label); top_layout.addWidget(users_group)
        self.layout.addWidget(self.status_label); self.layout.addLayout(top_layout)
        self.layout.addWidget(access_group)
        self.layout.addWidget(self.start_button); self.layout.addWidget(self.stop_button)
        self.layout.addWidget(QLabel("Server Log:")); self.layout.addWidget(self.console)
        self.setLayout(self.layout)

        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.add_user_button.clicked.connect(self.add_user)
        self.remove_user_button.clicked.connect(self.remove_user)
        self.add_folder_button.clicked.connect(self.add_folder)
        self.custom_code_radio.toggled.connect(self.custom_code_input.setEnabled)
        self.user_mode_radio.toggled.connect(self.toggle_access_modes)
        
        self.toggle_access_modes(True)
        self.load_permissions()

    def toggle_access_modes(self, is_user_mode):
        self.full_access_options_group.setEnabled(not is_user_mode)
        self.users_list.setEnabled(is_user_mode)
        self.add_user_button.setEnabled(is_user_mode)
        self.remove_user_button.setEnabled(is_user_mode)
        self.add_folder_button.setEnabled(is_user_mode)
        self.username_input.setEnabled(is_user_mode)
        self.password_input.setEnabled(is_user_mode)

    def load_permissions(self):
        if not os.path.exists(PERMISSIONS_FILE): self.permissions = {"users": {}}; return
        try:
            with open(PERMISSIONS_FILE, 'r') as f: self.permissions = json.load(f)
            self.refresh_user_list()
        except json.JSONDecodeError:
            self.permissions = {"users": {}}; QMessageBox.warning(self, "Warning", "Could not read permissions.json.")

    def save_permissions(self):
        try:
            with open(PERMISSIONS_FILE, 'w') as f: json.dump(self.permissions, f, indent=4)
        except Exception as e: QMessageBox.critical(self, "Error", f"Could not save permissions file: {e}")

    def refresh_user_list(self):
        self.users_list.clear()
        for username, data in self.permissions.get("users", {}).items():
            item = QListWidgetItem(f"👤 {username}"); self.users_list.addItem(item)
            for folder in data.get("allowed_folders", []):
                sub_item = QListWidgetItem(f"    📁 {folder}"); self.users_list.addItem(sub_item)

    def add_user(self):
        username = self.username_input.text().strip(); password = self.password_input.text()
        if not username or not password: QMessageBox.warning(self, "Input Error", "Username and password cannot be empty."); return
        if username in self.permissions["users"]: QMessageBox.warning(self, "Input Error", "User already exists."); return
        self.permissions["users"][username] = {"password": password, "allowed_folders": []}
        self.save_permissions(); self.refresh_user_list(); self.username_input.clear(); self.password_input.clear()

    def remove_user(self):
        current_item = self.users_list.currentItem()
        if not current_item or not current_item.text().startswith("👤"): QMessageBox.warning(self, "Selection Error", "Please select a user to remove."); return
        username = current_item.text().split(" ")[1]
        if QMessageBox.question(self, "Confirm", f"Remove user '{username}'?") == QMessageBox.StandardButton.Yes:
            del self.permissions["users"][username]; self.save_permissions(); self.refresh_user_list()

    def add_folder(self):
        current_item = self.users_list.currentItem()
        if not current_item: QMessageBox.warning(self, "Selection Error", "Please select a user first."); return
        row = self.users_list.row(current_item)
        while row >= 0:
            user_item = self.users_list.item(row)
            if user_item.text().startswith("👤"):
                username = user_item.text().split(" ")[1]
                folder = QFileDialog.getExistingDirectory(self, "Select Folder to Share")
                if folder and folder not in self.permissions["users"][username]["allowed_folders"]:
                    self.permissions["users"][username]["allowed_folders"].append(folder); self.save_permissions(); self.refresh_user_list()
                return
            row -= 1
        QMessageBox.warning(self, "Selection Error", "Please select a user (with the 👤 icon) before adding a folder.")

    def start_server(self):
        self.start_button.setEnabled(False); self.status_label.setText('Starting server...')
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS; ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg.exe'); ffprobe_path = os.path.join(bundle_dir, 'ffprobe.exe')
            set_ffmpeg_path(ffmpeg_path, ffprobe_path)
        log_queue = multiprocessing.Queue()
        self.log_thread = LogReader(log_queue); self.log_thread.new_log_record.connect(self.update_console); self.log_thread.start()
        ip = self.get_ip_address(); server_config = {}; url = ""
        if self.user_mode_radio.isChecked():
            server_config['mode'] = 'users'; server_config['permissions'] = self.permissions
            url = f"http://{ip}:{PORT}/login"
        else:
            server_config['mode'] = 'full_access'
            if self.secure_qr_radio.isChecked(): server_config['token'] = secrets.token_urlsafe(16)
            elif self.custom_code_radio.isChecked(): server_config['token'] = self.custom_code_input.text()
            else: server_config['token'] = "_public_"
            if not server_config['token'] and self.custom_code_radio.isChecked():
                self.update_console("ERROR: Custom code cannot be empty."); self.start_button.setEnabled(True); return
            url = f"http://{ip}:{PORT}/auth/{server_config['token']}"
        self.server_process = multiprocessing.Process(target=start_server_process, args=(log_queue, HOST, PORT, server_config))
        self.server_process.start()
        self.stop_button.setEnabled(True); self.status_label.setText('Server is running.')
        self.generate_qr_code(url)
        self.update_console(f"INFO: Server started. Access URL: {url}")
        
    def stop_server(self):
        if self.server_process and self.server_process.is_alive():
            self.update_console("INFO: Terminating server process..."); self.server_process.terminate(); self.server_process.join(5)
            self.update_console("INFO: Server process terminated.")
        if self.log_thread and self.log_thread.isRunning():
            self.log_thread.log_queue.put(None); self.log_thread.quit(); self.log_thread.wait()
        self.status_label.setText('Server is stopped.'); self.start_button.setEnabled(True); self.stop_button.setEnabled(False)

    def closeEvent(self, event): self.stop_server(); event.accept()
    @pyqtSlot(str)
    def update_console(self, text): self.console.append(text)
    def get_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM);
        try: s.connect(('10.255.255.255', 1)); IP = s.getsockname()[0]
        except Exception: IP = '127.0.0.1'
        finally: s.close()
        return IP
    def generate_qr_code(self, url):
        qr = qrcode.QRCode(version=1, box_size=10, border=4); qr.add_data(url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
        data = img.tobytes("raw", "RGBA"); qimage = QImage(data, img.size[0], img.size[1], QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage); self.qr_label.setPixmap(pixmap.scaled(250, 250))

if __name__ == '__main__':
    multiprocessing.freeze_support()
    app_gui = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app_gui.exec())

