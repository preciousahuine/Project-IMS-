


from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from db import get_db_connection
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
import mysql.connector
import os



load_dotenv()

app = Flask(__name__, template_folder="Templates")

app.secret_key = os.environ["FLASK_SECRET_KEY"]
csrf = CSRFProtect(app)

@app.route("/")
def home():
    return "Welcome to the Inventory Management System!"



@app.route("/register", methods=["GET", "POST"])
def register():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT role, is_active FROM users WHERE user_id = %s",
            (user_id,)
        )
        current_user = cursor.fetchone()
    except mysql.connector.Error:
        return "Database error. Please try again.", 500
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    if not current_user or not current_user["is_active"]:
        session.clear()
        return redirect(url_for("login"))

    if current_user["role"] == "OWNER":
        allowed_roles = [
            "MANAGER",
            "SALES_PERSONNEL",
            "STOREKEEPER"
        ]
    elif current_user["role"] == "MANAGER":
        allowed_roles = [
            "SALES_PERSONNEL",
            "STOREKEEPER"
        ]
    else:
        return "Access denied.", 403

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        

        if not name or not email or len(password) < 12:
            return "Invalid registration information.", 400

        if role not in allowed_roles:
            return "Invalid user role.", 400

        password_hash = generate_password_hash(password)

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            query = """
                INSERT INTO users
                (name, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
            """

            cursor.execute(
                query,
                (name, email, password_hash, role)
            )

            connection.commit()
            return "User registered successfully!"

        except mysql.connector.IntegrityError:
            return "This email is already registered.", 409

        except mysql.connector.Error:
            return "Database error. Please try again.", 500

        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()


    return render_template(
        "register.html",
        allowed_roles=allowed_roles
    )




@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            query = """
                SELECT user_id, name, email, password_hash,
                       role, is_active
                FROM users
                WHERE email = %s
            """

            cursor.execute(query, (email,))
            user = cursor.fetchone()

            if (
                user
                and user["is_active"]
                and check_password_hash(
                    user["password_hash"], password
                )
            ):
                session.clear()
                session["user_id"] = user["user_id"]
                session["user_name"] = user["name"]
                session["role"] = user["role"]

                return "Login successful!"

            return "Invalid email or password.", 401

        except mysql.connector.Error:
            return "Database error. Please try again.", 500

        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    return render_template("login.html")



if __name__ == "__main__":
    app.run(debug=True)

