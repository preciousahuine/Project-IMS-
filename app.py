


from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from decimal import Decimal, InvalidOperation

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

                return redirect(url_for("dashboard"))

            return "Invalid email or password.", 401

        except mysql.connector.Error:
            return "Database error. Please try again.", 500

        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    return render_template("login.html")


@app.route("/products/add", methods=["GET", "POST"])
def add_product():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in [
        "OWNER", "MANAGER", "STOREKEEPER"
    ]:
        return "Access denied.", 403

    if request.method == "POST":

        names = request.form.getlist("product_name")
        skus = request.form.getlist("sku")
        categories = request.form.getlist("category")
        descriptions = request.form.getlist("description")
        prices = request.form.getlist("unit_price")
        quantities = request.form.getlist("quantity_in_stock")
        reorder_levels = request.form.getlist("reorder_level")

        save_action = request.form.get("save_action")

        if save_action not in ("continue", "finish"):
            return "Invalid save action.", 400

        count = len(names)

        if count == 0 or count > 100:
            return "Invalid number of products.", 400

        fields = [
            skus, categories, descriptions,
            prices, quantities, reorder_levels
        ]

        if any(len(field) != count for field in fields):
            return "Incomplete product information.", 400

        products = []
        seen_skus = set()

        for i in range(count):

            name = names[i].strip()
            sku = skus[i].strip()
            category = categories[i].strip()
            description = descriptions[i].strip()

            if not name or not sku:
                return (
                    f"Product {i + 1}: "
                    "Name and SKU are required.", 400
                )

            if (
                len(name) > 150
                or len(sku) > 50
                or len(category) > 100
            ):
                return (
                    f"Product {i + 1}: "
                    "A text field is too long.", 400
                )

            sku_key = sku.lower()

            if sku_key in seen_skus:
                return (
                    f"Product {i + 1}: "
                    "Duplicate SKU in this batch.", 409
                )

            seen_skus.add(sku_key)

            try:
                price = Decimal(prices[i])
                quantity = int(quantities[i])
                reorder_level = int(reorder_levels[i])

            except (InvalidOperation, ValueError):
                return (
                    f"Product {i + 1}: "
                    "Invalid price or quantity.", 400
                )

            if (
                not price.is_finite()
                or price < 0
                or price > Decimal("99999999.99")
                or price.as_tuple().exponent < -2
                or quantity < 0
                or reorder_level < 0
                or quantity > 2147483647
                or reorder_level > 2147483647
            ):
                return (
                    f"Product {i + 1}: "
                    "Invalid product values.", 400
                )

            products.append((
                name,
                sku,
                category,
                description,
                price,
                quantity,
                reorder_level
            ))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            query = """
                INSERT INTO products
                (product_name, sku, category, description,
                 unit_price, quantity_in_stock, reorder_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            # Save the batch as one transaction.
            connection.start_transaction()

            cursor.executemany(query, products)

            connection.commit()

        
        except mysql.connector.IntegrityError:
            if connection is not None:
                connection.rollback()

            flash(
                "A product with this SKU already exists. "
                "No products were saved. Please use a different SKU.",
                "error"
            )

            return redirect(url_for("add_product"))

            

        except mysql.connector.Error:
            if connection is not None:
                connection.rollback()

            return (
                "Database error. No products in this "
                "batch were saved.", 500
            )

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        flash(
            f"{count} product(s) saved successfully!",
            "success"
        )

        if save_action == "continue":
            return redirect(url_for("add_product"))

        return redirect(url_for("dashboard"))

    return render_template("add_product.html")




@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)

