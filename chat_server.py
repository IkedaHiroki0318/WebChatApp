from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, send
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import random
import datetime
import os

# --- アプリ設定 ---
app = Flask(__name__)
app.secret_key = "secret123"
socketio = SocketIO(app, manage_session=True)
UPLOAD_FOLDER = "static/icons"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --- データベース初期化 ---
conn = sqlite3.connect("users.db")
cursor = conn.cursor()

# users（最初からicon入れる）
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    icon TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    message TEXT,
    time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS friends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1 TEXT,
    user2 TEXT,
    status TEXT
)
""")

conn.commit()
conn.close()

# --- ユーザー登録 ---
def register(username, password):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    hashed_password = generate_password_hash(password)

    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_password)
        )
        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()

# --- ログイン判定 ---
def login(username, password):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT password FROM users WHERE username=?",
        (username,)
    )

    result = cursor.fetchone()
    conn.close()

    if result is None:
        return False

    return check_password_hash(result[0], password)

# --- ルーティング ---

@app.route("/")
def index():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT username, message, time FROM messages")
    messages = cursor.fetchall()

    conn.close()

    return render_template(
        "index.html",
        username=session.get("username"),
        messages=messages
    )

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if login(username, password):
            session["username"] = username
            return redirect("/")
        else:
            return "ログイン失敗"

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        success = register(username, password)

        if success:
            return redirect("/login")
        else:
            return "このユーザー名は使われています"

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect("/login")

@app.route("/mypage", methods=["GET", "POST"])
def mypage():
    username = session.get("username")

    if not username:
        return redirect("/login")

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    if request.method == "POST":
        file = request.files["icon"]

        if file:
            filename = f"{username}.png"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            cursor.execute(
                "UPDATE users SET icon=? WHERE username=?",
                (filename, username)
            )
            conn.commit()

    # --- アイコン取得 ---
    cursor.execute(
        "SELECT icon FROM users WHERE username=?",
        (username,)
    )
    icon = cursor.fetchone()

    # --- フレンド取得（これ追加） ---
    cursor.execute(
        "SELECT user2 FROM friends WHERE user1=?",
        (username,)
    )
    friends = cursor.fetchall()

    # --- 申請一覧 ---
    cursor.execute(
        "SELECT user1 FROM friends WHERE user2=? AND status='pending'",
        (username,)
    )
    requests = cursor.fetchall()

    # --- フレンド一覧 ---
    cursor.execute(
        "SELECT user2 FROM friends WHERE user1=? AND status='accepted'",
        (username,)
    )
    friends = cursor.fetchall()

    conn.close()

    return render_template(
        "mypage.html",
        icon=icon,
        friends=friends,
        requests=requests
)

@app.route("/add_friend", methods=["POST"])
def add_friend():
    user1 = session.get("username")
    user2 = request.form["friend_name"]

    if not user1:
        return redirect("/login")

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # 存在チェック
    cursor.execute("SELECT * FROM users WHERE username=?", (user2,))
    if cursor.fetchone() is None:
        conn.close()
        return "ユーザーが存在しません"

    # 自分防止
    if user1 == user2:
        conn.close()
        return "自分は追加できません"

    # 既存チェック
    cursor.execute(
        "SELECT * FROM friends WHERE user1=? AND user2=?",
        (user1, user2)
    )
    if cursor.fetchone():
        conn.close()
        return "すでに申請済み"

    # 申請として追加
    cursor.execute(
        "INSERT INTO friends (user1, user2, status) VALUES (?, ?, ?)",
        (user1, user2, "pending")
    )

    conn.commit()
    conn.close()

    return redirect("/mypage")

@app.route("/accept_friend", methods=["POST"])
def accept_friend():
    username = session.get("username")
    requester = request.form["requester"]

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # --- pendingをacceptedに変更 ---
    cursor.execute(
        "UPDATE friends SET status='accepted' WHERE user1=? AND user2=?",
        (requester, username)
    )

    # --- 逆方向が存在しない場合のみ追加 ---
    cursor.execute(
        "SELECT * FROM friends WHERE user1=? AND user2=?",
        (username, requester)
    )

    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO friends (user1, user2, status) VALUES (?, ?, 'accepted')",
            (username, requester)
        )

    conn.commit()
    conn.close()

    return redirect("/mypage")

@app.route("/remove_friend", methods=["POST"])
def remove_friend():
        user1 = session.get("username")
        user2 = request.form["friend_name"]

        if not user1:
         return redirect("/login")

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        # 双方向削除
        cursor.execute(
            "DELETE FROM friends WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)",
            (user1, user2, user2, user1)
        )

        conn.commit()
        conn.close()

        return redirect("/mypage")

# --- チャット処理 ---
from flask import request  # ← これ絶対必要

@socketio.on("message")
def handle_message(msg):
    username = session.get("username")

    if not username:
        if "guest_name" not in session:
            session["guest_name"] = f"ゲスト{random.randint(1000,9999)}"
        username = session["guest_name"]

    time = datetime.datetime.now().strftime("%H:%M")

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT icon FROM users WHERE username=?",
        (username,)
    )
    result = cursor.fetchone()
    conn.close()

    icon = result[0] if result and result[0] else "default.png"

    send({
        "username": username,
        "message": msg,
        "sid": request.sid,
        "time": time,
        "icon": icon   
    }, broadcast=True)

@socketio.on("connect")
def handle_connect():
    username = session.get("username")

    if not username:
        if "guest_name" not in session:
            session["guest_name"] = f"ゲスト{random.randint(1000,9999)}"
        username = session["guest_name"]

    send({
        "type": "system",
        "message": f"{username} が参加しました"
    }, broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():
    username = session.get("username") or session.get("guest_name", "誰か")

    send({
        "type": "system",
        "message": f"{username} が退出しました"
    }, broadcast=True)

# --- 起動（必ず一番下） ---
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)