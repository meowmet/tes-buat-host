from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from cryptography.fernet import Fernet, InvalidToken
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Ganti sesuai kebutuhan Anda


# Fungsi untuk membuat database dan tabel jika belum ada
def initialize_database():
    try:
        # Koneksi ke server MySQL tanpa database
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password=''
        )
        cursor = conn.cursor()

        # Buat database jika belum ada
        cursor.execute("CREATE DATABASE IF NOT EXISTS password_manager")

        # Koneksi ke database yang baru dibuat
        conn.database = 'password_manager'

        # Buat tabel users jika belum ada
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hashed VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Buat tabel passwords jika belum ada
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS passwords (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                website VARCHAR(100) NOT NULL,
                password_encrypted TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        print("Database and tables initialized successfully!")
    except mysql.connector.Error as err:
        print(f"Error initializing database: {err}")
    finally:
        cursor.close()
        conn.close()

# Panggil fungsi initialize_database untuk memastikan database dan tabel sudah ada
initialize_database()


# Konfigurasi database MySQL
def get_db_connection():
    try:
        return mysql.connector.connect(
            host='localhost',       # Ganti dengan host Anda
            user='root',            # Ganti dengan username MySQL Anda
            password='',            # Ganti dengan password MySQL Anda
            database='password_manager'  # Nama database
        )
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

# Fungsi untuk menyimpan kunci ke file
def save_key_to_file(key, filename='secret.key'):
    with open(filename, 'wb') as file:
        file.write(key)

# Fungsi untuk membaca kunci dari file
def load_key_from_file(filename='secret.key'):
    if os.path.exists(filename):
        with open(filename, 'rb') as file:
            return file.read()
    else:
        # Jika file kunci belum ada, buat kunci baru dan simpan
        key = Fernet.generate_key()
        save_key_to_file(key, filename)
        return key

# Muat kunci dari file
key = load_key_from_file()

# Buat cipher suite dengan kunci yang dimuat
cipher_suite = Fernet(key)

# Route home
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

# Route untuk halaman register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validasi form
        if not username:
            flash("Username is required.", "error")
            return redirect(url_for('register'))
        
        if not password:
            flash("Password is required.", "error")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for('register'))

        # Validasi panjang password jika diperlukan
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()

        if not conn:
            flash("Database connection error.", "error")
            return redirect(url_for('register'))

        cursor = conn.cursor()
        try:
            # Periksa apakah username sudah ada
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()
            if user:
                flash("Username already exists. Please choose a different username.", "error")
                return redirect(url_for('register'))

            # Simpan data user ke tabel users
            cursor.execute('INSERT INTO users (username, password_hashed) VALUES (%s, %s)', (username, hashed_password))
            conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error: {e}")  # Log error ke console
            flash("An error occurred during registration. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')


# Route untuk halaman login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Validasi form
        if not username:
            flash("Username is required.", "error")
            return redirect(url_for('login'))

        if not password:
            flash("Password is required.", "error")
            return redirect(url_for('login'))

        conn = get_db_connection()

        if not conn:
            flash("Database connection error.", "error")
            return redirect(url_for('login'))

        cursor = conn.cursor(dictionary=True)
        try:
            # Periksa apakah username ada di database
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password_hashed'], password):  # Sesuaikan nama kolom
                session['user_id'] = user['id']
                session['username'] = user['username']  # Menyimpan username di session
                flash("Login successful!", "success")
                return redirect(url_for('dashboard'))

            flash("Invalid username or password.", "error")
            return redirect(url_for('login'))
        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')

# Route untuk halaman dashboard
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db_connection()

    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for("login"))

    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        # Tangkap data dari form
        website = request.form.get("website")
        password = request.form.get("password")

        # Enkripsi password sebelum disimpan
        encrypted_password = cipher_suite.encrypt(password.encode()).decode()

        # Simpan ke database
        try:
            cursor.execute(
                "INSERT INTO passwords (user_id, website, password_encrypted) VALUES (%s, %s, %s)",
                (user_id, website, encrypted_password),
            )
            conn.commit()
            flash("Password saved successfully!", "success")
        except Exception as e:
            print(f"Error saving password: {e}")
            flash("An error occurred while saving the password.", "error")
    
    # Ambil data password untuk ditampilkan
    cursor.execute("SELECT * FROM passwords WHERE user_id = %s", (user_id,))
    rows = cursor.fetchall()
    passwords = []
    for row in rows:
        try:
            decrypted_password = cipher_suite.decrypt(row["password_encrypted"].encode()).decode()
            passwords.append({"website": row["website"], "password": decrypted_password})
        except (InvalidToken, ValueError):
            passwords.append({"website": row["website"], "password": "Error: Cannot decrypt password"})

    cursor.close()
    conn.close()

    return render_template("dashboard.html", passwords=passwords, username=session.get("username"))

# Route untuk logout
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)  # Hapus username dari session saat logout
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
