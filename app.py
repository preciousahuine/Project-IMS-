


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

from io import BytesIO, StringIO
import csv
from flask import send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from xml.sax.saxutils import escape

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from db import get_db_connection
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
import mysql.connector
import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email.message import EmailMessage
import smtplib



load_dotenv()


app = Flask(
    __name__,
    template_folder="Templates",
    static_folder="Static"
)


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


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("forgot_password"))

        # Email delivery will be implemented in the next step.
        flash(
            "The password reset email service is not configured yet.",
            "info"
        )
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")



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

    inventory_stats = None
    attention_products = []

    if session.get("role") in ("OWNER", "MANAGER"):
        conn = get_db_connection()
        cursor = None

        try:
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    COUNT(*) AS total_products,

                    COALESCE(
                        SUM(unit_price * quantity_in_stock), 0
                    ) AS stock_value,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN quantity_in_stock > 0
                                 AND quantity_in_stock <= reorder_level
                                THEN 1 ELSE 0
                            END
                        ), 0
                    ) AS low_stock,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN quantity_in_stock = 0
                                THEN 1 ELSE 0
                            END
                        ), 0
                    ) AS out_of_stock

                FROM products
                WHERE is_active = TRUE
            """)

            inventory_stats = cursor.fetchone()
            inventory_stats["healthy_stock"] = (
    inventory_stats["total_products"]
    - inventory_stats["low_stock"]
    - inventory_stats["out_of_stock"]
)

             
            # Retrieve products that need restocking
            cursor.execute("""
                SELECT
                    product_id,
                    product_name,
                    sku,
                    quantity_in_stock,
                    reorder_level,
                    CASE
                        WHEN quantity_in_stock = 0
                        THEN 'Out of Stock'
                        ELSE 'Low Stock'
                    END AS stock_status
                FROM products
                WHERE is_active = TRUE
                  AND (
                      quantity_in_stock = 0
                      OR (
                          quantity_in_stock > 0
                          AND quantity_in_stock <= reorder_level
                      )
                  )
                ORDER BY
                    CASE
                        WHEN quantity_in_stock = 0 THEN 0
                        ELSE 1
                    END,
                    quantity_in_stock ASC,
                    product_name ASC
            """)

            attention_products = cursor.fetchall()



        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

    return render_template(
    "dashboard.html",
    inventory_stats=inventory_stats,
    attention_products=attention_products
)




# User Story 13 - Sales and Inventory Reports

def generate_report_pdf(title, period, summary, headers, rows):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=35,
        leftMargin=35,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elements = []

    navy = colors.HexColor("#19375b")
    light_blue = colors.HexColor("#f0f4f9")

    # Company heading
    elements.append(
        Paragraph(
            "<b>Inventory Management System (IMS)</b>",
            styles["Title"]
        )
    )

    elements.append(Spacer(1, 10))

    # Report title
    elements.append(
        Paragraph(
            escape(title),
            styles["Heading1"]
        )
    )

    elements.append(
        Paragraph(
            escape(period),
            styles["Normal"]
        )
    )

    from datetime import datetime

    generated_at = datetime.now().strftime(
        "%Y-%m-%d %I:%M %p"
    )

    generated_by = session.get("user_name", "Unknown")

    elements.append(
        Paragraph(
            f"Generated on: {generated_at}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Generated by: {escape(str(generated_by))}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 20))

    # Report summary
    elements.append(
        Paragraph("Report Summary", styles["Heading2"])
    )

    summary_rows = [
        [
            Paragraph(escape(str(label)), styles["Normal"]),
            Paragraph(escape(str(value)), styles["Normal"])
        ]
        for label, value in summary.items()
    ]

    summary_table = Table(
        summary_rows,
        colWidths=[230, 230],
        hAlign="LEFT"
    )

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), light_blue),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Detailed report
    elements.append(
        Paragraph("Report Details", styles["Heading2"])
    )

    if rows:
        table_data = [headers]

        for row in rows:
            table_data.append([
                Paragraph(
                    escape(str(value)),
                    styles["Normal"]
                )
                for value in row
            ])

        column_width = document.width / len(headers)

        report_table = Table(
            table_data,
            colWidths=[column_width] * len(headers),
            repeatRows=1
        )

        report_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, light_blue]),
            ("GRID", (0, 0), (-1, -1), 0.5,
             colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
        ]))

        elements.append(report_table)

    else:
        elements.append(
            Paragraph(
                "No records found for this report.",
                styles["Normal"]
            )
        )

    # Page footer
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.grey)

        canvas.drawString(
            35, 20,
            "IMS | Inventory Management System"
        )

        canvas.drawRightString(
            landscape(A4)[0] - 35,
            20,
            f"Page {doc.page}"
        )

        canvas.restoreState()

    document.build(
        elements,
        onFirstPage=add_footer,
        onLaterPages=add_footer
    )

    buffer.seek(0)

    return buffer




@app.route("/reports")
def reports():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in ("OWNER", "MANAGER"):
        return redirect(url_for("dashboard"))

    from datetime import date, timedelta

    report_type = request.args.get("report_type", "sales")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    sales_data = []
    sales_summary = None

    purchase_data = []
    purchase_summary = None

    stock_data = []
    stock_summary = None

    error = None

    try:
        if report_type not in ("sales", "purchases", "stock"):
            raise ValueError("Invalid report type.")

        # STOCK LEVEL REPORT
        if report_type == "stock":
            conn = get_db_connection()
            cursor = None

            try:
                cursor = conn.cursor(dictionary=True)

                cursor.execute("""
                    SELECT
                        product_name,
                        sku,
                        category,
                        unit_price,
                        quantity_in_stock,
                        reorder_level,
                        unit_price * quantity_in_stock
                            AS stock_value,
                        CASE
                            WHEN quantity_in_stock = 0
                                THEN 'Out of Stock'
                            WHEN quantity_in_stock <= reorder_level
                                THEN 'Low Stock'
                            ELSE 'Healthy'
                        END AS stock_status
                    FROM products
                    WHERE is_active = TRUE
                    ORDER BY product_name
                """)

                stock_data = cursor.fetchall()

                stock_summary = {
                    "total_products": len(stock_data),

                    "total_units": sum(
                        row["quantity_in_stock"]
                        for row in stock_data
                    ),

                    "stock_value": sum(
                        (
                            row["stock_value"]
                            for row in stock_data
                        ),
                        Decimal("0.00")
                    ),

                    "healthy_stock": sum(
                        1 for row in stock_data
                        if row["stock_status"] == "Healthy"
                    ),

                    "low_stock": sum(
                        1 for row in stock_data
                        if row["stock_status"] == "Low Stock"
                    ),

                    "out_of_stock": sum(
                        1 for row in stock_data
                        if row["stock_status"] == "Out of Stock"
                    )
                }

            finally:
                if cursor is not None:
                    cursor.close()
                conn.close()

        elif start_date or end_date:

            if not start_date or not end_date:
                raise ValueError("Both dates are required.")

            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)

            if start > end:
                raise ValueError(
                    "Start date cannot be after end date."
                )

            # SALES REPORT
            if report_type == "sales":
                conn = get_db_connection()
                cursor = None

                try:
                    cursor = conn.cursor(dictionary=True)

                    cursor.execute("""
                        SELECT
                            s.sale_id,
                            p.product_name,
                            s.quantity_sold,
                            s.unit_price,
                            s.total_amount,
                            s.sale_date
                        FROM sales AS s
                        JOIN products AS p
                            ON s.product_id = p.product_id
                        WHERE s.sale_date >= %s
                          AND s.sale_date < %s
                        ORDER BY s.sale_date DESC
                    """, (start, end + timedelta(days=1)))

                    sales_data = cursor.fetchall()

                    sales_summary = {
                        "transactions": len(sales_data),

                        "units_sold": sum(
                            row["quantity_sold"]
                            for row in sales_data
                        ),

                        "revenue": sum(
                            (
                                row["total_amount"]
                                for row in sales_data
                            ),
                            Decimal("0.00")
                        )
                    }

                finally:
                    if cursor is not None:
                        cursor.close()
                    conn.close()

            # PURCHASE REPORT
            elif report_type == "purchases":
                conn = get_db_connection()
                cursor = None

                try:
                    cursor = conn.cursor(dictionary=True)

                    cursor.execute("""
                        SELECT
                            i.stock_id,
                            p.product_name,
                            i.supplier_name,
                            i.quantity_received,
                            i.received_date,
                            u.name AS received_by
                        FROM incoming_stock AS i
                        JOIN products AS p
                            ON i.product_id = p.product_id
                        LEFT JOIN users AS u
                            ON i.received_by = u.user_id
                        WHERE i.is_active = TRUE
                          AND i.received_date >= %s
                          AND i.received_date < %s
                        ORDER BY i.received_date DESC
                    """, (start, end + timedelta(days=1)))

                    purchase_data = cursor.fetchall()

                    purchase_summary = {
                        "receipts": len(purchase_data),

                        "units_received": sum(
                            row["quantity_received"]
                            for row in purchase_data
                        ),

                        "suppliers": len({
                            row["supplier_name"]
                            for row in purchase_data
                        })
                    }

                finally:
                    if cursor is not None:
                        cursor.close()
                    conn.close()

    except (ValueError, OverflowError) as exc:
        error = str(exc)


        # DOWNLOAD PDF OR CSV REPORT
    download_type = request.args.get("download")

    if download_type in ("pdf", "csv") and not error:

        if report_type == "sales" and sales_summary is not None:

            title = "Sales Report"
            period = f"Report Period: {start_date} to {end_date}"

            summary = {
                "Total Revenue": f"${sales_summary['revenue']:,.2f}",
                "Units Sold": sales_summary["units_sold"],
                "Total Transactions": sales_summary["transactions"]
            }

            headers = [
                "Date",
                "Product",
                "Quantity",
                "Unit Price",
                "Total Amount"
            ]

            rows = [
                [
                    sale["sale_date"].strftime("%Y-%m-%d"),
                    sale["product_name"],
                    sale["quantity_sold"],
                    f"${sale['unit_price']:,.2f}",
                    f"${sale['total_amount']:,.2f}"
                ]
                for sale in sales_data
            ]

            filename = "sales_report.pdf"

        elif report_type == "purchases" and purchase_summary is not None:

            title = "Purchase Report"
            period = f"Report Period: {start_date} to {end_date}"

            summary = {
                "Total Receipts": purchase_summary["receipts"],
                "Units Received": purchase_summary["units_received"],
                "Unique Suppliers": purchase_summary["suppliers"]
            }

            headers = [
                "Date",
                "Product",
                "Supplier",
                "Quantity Received",
                "Received By"
            ]

            rows = [
                [
                    purchase["received_date"].strftime("%Y-%m-%d"),
                    purchase["product_name"],
                    purchase["supplier_name"],
                    purchase["quantity_received"],
                    purchase["received_by"] or "Unknown"
                ]
                for purchase in purchase_data
            ]

            filename = "purchase_report.pdf"

        elif report_type == "stock" and stock_summary is not None:

            title = "Stock Level Report"
            period = (
                f"Current Inventory Snapshot: {date.today().isoformat()}"
                " | Valued at selling price"
            )

            summary = {
                "Total Products": stock_summary["total_products"],
                "Total Units": stock_summary["total_units"],
                "Total Stock Value": f"${stock_summary['stock_value']:,.2f}",
                "Healthy Stock": stock_summary["healthy_stock"],
                "Low Stock": stock_summary["low_stock"],
                "Out of Stock": stock_summary["out_of_stock"]
            }

            headers = [
                "Product",
                "SKU",
                "Category",
                "Unit Price",
                "Quantity",
                "Reorder Level",
                "Stock Value",
                "Status"
            ]

            rows = [
                [
                    stock["product_name"],
                    stock["sku"],
                    stock["category"] or "Uncategorized",
                    f"${stock['unit_price']:,.2f}",
                    stock["quantity_in_stock"],
                    stock["reorder_level"],
                    f"${stock['stock_value']:,.2f}",
                    stock["stock_status"]
                ]
                for stock in stock_data
            ]

            filename = "stock_level_report.pdf"

        else:
            return redirect(url_for(
                "reports",
                report_type=report_type,
                start_date=start_date,
                end_date=end_date
            ))


        # GENERATE CSV FILE
        if download_type == "csv":

            output = StringIO()
            writer = csv.writer(output)

            # Protect against spreadsheet formula injection
            def safe_csv_value(value):
                if isinstance(value, str):
                    if value.lstrip().startswith(
                        ("=", "+", "-", "@", "\t", "\r", "\n")
                    ):
                        return "'" + value
                return value

            # Write column headings
            writer.writerow(headers)

            # Write report records
            for row in rows:
                writer.writerow([
                    safe_csv_value(value)
                    for value in row
                ])

            csv_buffer = BytesIO(
                output.getvalue().encode("utf-8-sig")
            )

            output.close()
            csv_buffer.seek(0)

            return send_file(
                csv_buffer,
                mimetype="text/csv",
                as_attachment=True,
                download_name=filename.replace(".pdf", ".csv")
            )



        pdf_buffer = generate_report_pdf(
            title,
            period,
            summary,
            headers,
            rows
        )

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )



    return render_template(
        "reports.html",
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        sales_data=sales_data,
        sales_summary=sales_summary,
        purchase_data=purchase_data,
        purchase_summary=purchase_summary,
        stock_data=stock_data,
        stock_summary=stock_summary,
        report_date=date.today().isoformat(),
        error=error
    )

@app.route("/products/search", methods=["GET"])
def search_product():
    if "user_id" not in session:
        return redirect(url_for("login"))

    search_query = request.args.get("q", "").strip()
    products = []

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if search_query:
            search_term = f"%{search_query}%"

            cursor.execute(
                """
                SELECT product_id, product_name, sku,
                       category, unit_price,
                       quantity_in_stock, reorder_level
                FROM products
                WHERE is_active = TRUE
                  AND (
                      product_name LIKE %s
                      OR sku LIKE %s
                      OR category LIKE %s
                  )
                ORDER BY product_name
                """,
                (search_term, search_term, search_term)
            )
        else:
            cursor.execute(
                """
                SELECT product_id, product_name, sku,
                       category, unit_price,
                       quantity_in_stock, reorder_level
                FROM products
                WHERE is_active = TRUE
                ORDER BY product_name
                """
            )

        products = cursor.fetchall()

    except mysql.connector.Error:
        return "Unable to load products. Please try again.", 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return render_template(
        "search_product.html",
        products=products,
        search_query=search_query
    )

@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product(product_id):

    # Only logged-in authorized users can edit products
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in ["OWNER", "MANAGER", "STOREKEEPER"]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the existing product
        cursor.execute(
            "SELECT * FROM products WHERE product_id = %s AND is_active = TRUE",
            (product_id,)
        )
        product = cursor.fetchone()

        if product is None:
            return "Product not found.", 404

        if request.method == "POST":
            product_name = request.form.get("product_name", "").strip()
            sku = request.form.get("sku", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()

            try:
                unit_price = Decimal(request.form.get("unit_price", ""))
                quantity = int(request.form.get("quantity_in_stock", ""))
                reorder_level = int(request.form.get("reorder_level", ""))
            except (InvalidOperation, ValueError):
                return "Invalid price or quantity.", 400

            if not product_name or not sku:
                return "Product name and SKU are required.", 400

            if (
                not unit_price.is_finite()
                or unit_price < 0
                or unit_price > Decimal("99999999.99")
                or unit_price.as_tuple().exponent < -2
                or quantity < 0
                or reorder_level < 0
            ):
                return "Invalid product values.", 400

            query = """
                UPDATE products
                SET product_name = %s,
                    sku = %s,
                    category = %s,
                    description = %s,
                    unit_price = %s,
                    quantity_in_stock = %s,
                    reorder_level = %s
                WHERE product_id = %s
                  AND is_active = TRUE
            """

            cursor.execute(
                query,
                (
                    product_name,
                    sku,
                    category,
                    description,
                    unit_price,
                    quantity,
                    reorder_level,
                    product_id
                )
            )

            connection.commit()

            flash("Product updated successfully!", "success")
            return redirect(url_for("search_product"))

        return render_template(
            "edit_product.html",
            product=product
        )

    
    except mysql.connector.IntegrityError:
        if connection is not None:
            connection.rollback()

        flash(
            "This SKU already exists. Please enter a different SKU.",
            "error"
        )

        return redirect(url_for("edit_product", product_id=product_id))

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()

        return "Database error. Please try again.", 500


    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


@app.route("/products/<int:product_id>/delete", methods=["GET", "POST"])
def delete_product(product_id):
    # Check whether the user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only authorized users can delete products
    if session.get("role") not in ["OWNER", "MANAGER", "STOREKEEPER"]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Find the active product
        cursor.execute(
            """
            SELECT * FROM products
            WHERE product_id = %s AND is_active = TRUE
            """,
            (product_id,)
        )

        product = cursor.fetchone()

        if product is None:
            return "Product not found.", 404

        # Display confirmation page
        if request.method == "GET":
            return render_template(
                "delete_product.html",
                product=product
            )

        # Soft delete the product after confirmation
        cursor.execute(
            """
            UPDATE products
            SET is_active = FALSE
            WHERE product_id = %s AND is_active = TRUE
            """,
            (product_id,)
        )

        connection.commit()

        flash("Product deleted successfully!", "success")
        return redirect(url_for("search_product"))

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        return "Database error. Please try again.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


@app.route("/sales/record", methods=["GET", "POST"])
def record_sale():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in [
        "OWNER", "MANAGER", "SALES_PERSONNEL"
    ]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id", ""))
                quantity_sold = int(
                    request.form.get("quantity_sold", "")
                )
            except (ValueError, TypeError):
                flash("Please enter valid sale details.", "error")
                return redirect(url_for("record_sale"))

            if quantity_sold <= 0:
                flash("Quantity sold must be greater than zero.", "error")
                return redirect(url_for("record_sale"))

            # Lock the product row while processing the sale.
            cursor.execute(
                """
                SELECT product_id, product_name,
                       unit_price, quantity_in_stock
                FROM products
                WHERE product_id = %s AND is_active = TRUE
                FOR UPDATE
                """,
                (product_id,)
            )

            product = cursor.fetchone()

            if product is None:
                connection.rollback()
                flash("Product not found or inactive.", "error")
                return redirect(url_for("record_sale"))

            if quantity_sold > product["quantity_in_stock"]:
                connection.rollback()
                flash(
                    "Insufficient stock. Available quantity: "
                    + str(product["quantity_in_stock"]),
                    "error"
                )
                return redirect(url_for("record_sale"))

            # Always calculate the total on the server.
            unit_price = Decimal(str(product["unit_price"]))
            total_amount = unit_price * quantity_sold

            # Record the sale.
            cursor.execute(
                """
                INSERT INTO sales (
                    product_id, quantity_sold, unit_price,
                    total_amount, sold_by
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    product_id,
                    quantity_sold,
                    unit_price,
                    total_amount,
                    session["user_id"]
                )
            )

            # Automatically reduce inventory.
            cursor.execute(
                """
                UPDATE products
                SET quantity_in_stock = quantity_in_stock - %s
                WHERE product_id = %s
                """,
                (quantity_sold, product_id)
            )


       
            # User Story #10: Log stock changes after a sale
            previous_quantity = product["quantity_in_stock"]
            new_quantity = previous_quantity - quantity_sold

            cursor.execute(
                """
                INSERT INTO stock_audit_log (
                    product_id,
                    action_type,
                    previous_quantity,
                    new_quantity,
                    quantity_change,
                    changed_by,
                    description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    product_id,
                    "SALE_RECORDED",
                    previous_quantity,
                    new_quantity,
                    -quantity_sold,
                    session["user_id"],
                    f"Sale recorded: {quantity_sold} unit(s) sold."
                )
            )

            # Save sale, inventory update, and audit log together
            connection.commit()


            flash(
                f"Sale recorded successfully! "
                f"{quantity_sold} unit(s) of "
                f"{product['product_name']} sold. "
                f"Total: ${total_amount:.2f}",
                "success"
            )

            return redirect(url_for("record_sale"))

        # GET: Show only active products.
        cursor.execute(
            """
            SELECT product_id, product_name, sku,
                   unit_price, quantity_in_stock
            FROM products
            WHERE is_active = TRUE
            ORDER BY product_name, product_id
            """
        )

        products = cursor.fetchall()

        return render_template(
            "record_sale.html",
            products=products
        )

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()

        flash("Database error. Please try again.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()



# User Story #9: Record Incoming Stock

@app.route("/stock/incoming", methods=["GET", "POST"])
def record_incoming_stock():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in [
        "OWNER", "MANAGER", "STOREKEEPER"
    ]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":

            try:
                product_id = int(
                    request.form.get("product_id", "")
                )
                quantity_received = int(
                    request.form.get("quantity_received", "")
                )
            except (ValueError, TypeError):
                flash("Enter valid stock details.", "error")
                return redirect(url_for("record_incoming_stock"))

            supplier_name = request.form.get(
                "supplier_name", ""
            ).strip()

            if not supplier_name or len(supplier_name) > 150:
                flash("Enter a valid supplier name.", "error")
                return redirect(url_for("record_incoming_stock"))

            if quantity_received <= 0:
                flash("Quantity must be greater than zero.", "error")
                return redirect(url_for("record_incoming_stock"))

            # Lock product during inventory update
            cursor.execute(
                """
                SELECT product_id, quantity_in_stock
                FROM products
                WHERE product_id = %s AND is_active = TRUE
                FOR UPDATE
                """,
                (product_id,)
            )

            product = cursor.fetchone()

            if product is None:
                connection.rollback()
                flash("Product not found.", "error")
                return redirect(url_for("record_incoming_stock"))

            new_stock = (
                product["quantity_in_stock"] + quantity_received
            )

            if new_stock > 2147483647:
                connection.rollback()
                flash("Stock quantity exceeds the allowed limit.", "error")
                return redirect(url_for("record_incoming_stock"))

            cursor.execute(
                """
                INSERT INTO incoming_stock
                    (product_id, supplier_name,
                     quantity_received, received_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    product_id,
                    supplier_name,
                    quantity_received,
                    session["user_id"]
                )
            )

            cursor.execute(
                """
                UPDATE products
                SET quantity_in_stock = %s
                WHERE product_id = %s AND is_active = TRUE
                """,
                (new_stock, product_id)
            )


            # User Story #10: Log incoming stock changes
            previous_quantity = product["quantity_in_stock"]

            cursor.execute(
                """
                INSERT INTO stock_audit_log (
                    product_id,
                    action_type,
                    previous_quantity,
                    new_quantity,
                    quantity_change,
                    changed_by,
                    description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    product_id,
                    "STOCK_RECEIVED",
                    previous_quantity,
                    new_stock,
                    quantity_received,
                    session["user_id"],
                    f"Received {quantity_received} unit(s) "
                    f"from {supplier_name}."
                )
            )


            connection.commit()

            flash(
                "Incoming stock recorded successfully!",
                "success"
            )

            return redirect(url_for("record_incoming_stock"))

        # Products available for receiving
        cursor.execute(
            """
            SELECT product_id, product_name, sku,
                   quantity_in_stock
            FROM products
            WHERE is_active = TRUE
            ORDER BY product_name
            """
        )
        products = cursor.fetchall()

        # Incoming stock history
        cursor.execute(
            """
            SELECT
                s.stock_id,
                p.product_name,
                s.supplier_name,
                s.quantity_received,
                s.received_date
           
    FROM incoming_stock s
    JOIN products p
    ON s.product_id = p.product_id
    WHERE s.is_active = TRUE
    ORDER BY s.received_date DESC, s.stock_id DESC
     """
        )
        stock_records = cursor.fetchall()

        return render_template(
            "record_incoming_stock.html",
            products=products,
            stock_records=stock_records
        )

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()

        flash("Database error. Please try again.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# User Story #9: Edit Incoming Stock

@app.route("/stock/incoming/<int:stock_id>/edit",
           methods=["GET", "POST"])
def edit_incoming_stock(stock_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in [
        "OWNER", "MANAGER", "STOREKEEPER"
    ]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Lock the receipt first, then its product.
        
        cursor.execute(
        """
    SELECT stock_id, product_id, supplier_name,
           quantity_received
    FROM incoming_stock
    WHERE stock_id = %s AND is_active = TRUE
    FOR UPDATE
    """,
    (stock_id,)
)


        stock = cursor.fetchone()

        if stock is None:
            connection.rollback()
            return "Incoming stock record not found.", 404

        cursor.execute(
            """
            SELECT product_name, sku, quantity_in_stock
            FROM products
            WHERE product_id = %s AND is_active = TRUE
            FOR UPDATE
            """,
            (stock["product_id"],)
        )

        product = cursor.fetchone()

        if product is None:
            connection.rollback()
            return "Product not found or inactive.", 404

        stock.update(product)

        if request.method == "POST":

            supplier_name = request.form.get(
                "supplier_name", ""
            ).strip()

            try:
                corrected_quantity = int(
                    request.form.get("quantity_received", "")
                )
            except (ValueError, TypeError):
                flash("Enter a valid quantity.", "error")
                return redirect(url_for(
                    "edit_incoming_stock", stock_id=stock_id
                ))

            if not supplier_name or len(supplier_name) > 150:
                flash("Enter a valid supplier name.", "error")
                return redirect(url_for(
                    "edit_incoming_stock", stock_id=stock_id
                ))

            if corrected_quantity <= 0:
                flash(
                    "Quantity must be greater than zero.",
                    "error"
                )
                return redirect(url_for(
                    "edit_incoming_stock", stock_id=stock_id
                ))

            difference = (
                corrected_quantity - stock["quantity_received"]
            )

            new_stock = stock["quantity_in_stock"] + difference

            if new_stock < 0 or new_stock > 2147483647:
                connection.rollback()
                flash(
                    "Correction cannot be applied to current inventory.",
                    "error"
                )
                return redirect(url_for(
                    "edit_incoming_stock", stock_id=stock_id
                ))

            cursor.execute(
                """
                UPDATE incoming_stock
                SET supplier_name = %s,
                    quantity_received = %s
                WHERE stock_id = %s
                """,
                (supplier_name, corrected_quantity, stock_id)
            )

            cursor.execute(
                """
                UPDATE products
                SET quantity_in_stock = %s
                WHERE product_id = %s
                """,
                (new_stock, stock["product_id"])
            )


            # User Story #10: Log incoming stock corrections
            previous_quantity = stock["quantity_in_stock"]

            cursor.execute(
                """
                INSERT INTO stock_audit_log (
                    product_id,
                    action_type,
                    previous_quantity,
                    new_quantity,
                    quantity_change,
                    changed_by,
                    description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    stock["product_id"],
                    "STOCK_RECEIPT_EDITED",
                    previous_quantity,
                    new_stock,
                    difference,
                    session["user_id"],
                    f"Incoming stock receipt #{stock_id} corrected "
                    f"from {stock['quantity_received']} "
                    f"to {corrected_quantity} unit(s)."
                )
            )


            connection.commit()

            flash(
                "Incoming stock updated successfully!",
                "success"
            )

            return redirect(url_for("record_incoming_stock"))

        connection.rollback()

        return render_template(
            "edit_incoming_stock.html",
            stock=stock
        )

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()

        flash("Database error. Please try again.", "error")
        return redirect(url_for("record_incoming_stock"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()



# User Story #9: Soft Delete Incoming Stock

@app.route("/stock/incoming/<int:stock_id>/delete",
           methods=["POST"])
def delete_incoming_stock(stock_id):

    # Require login
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Restrict access to authorized roles
    if session.get("role") not in [
        "OWNER", "MANAGER", "STOREKEEPER"
    ]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Lock the incoming stock record
        cursor.execute(
            """
            SELECT stock_id, product_id, quantity_received
            FROM incoming_stock
            WHERE stock_id = %s AND is_active = TRUE
            FOR UPDATE
            """,
            (stock_id,)
        )

        stock = cursor.fetchone()

        if stock is None:
            connection.rollback()
            flash(
                "Incoming stock record not found or already deleted.",
                "error"
            )
            return redirect(url_for("record_incoming_stock"))

        # Lock the corresponding product
        cursor.execute(
            """
            SELECT quantity_in_stock
            FROM products
            WHERE product_id = %s
            FOR UPDATE
            """,
            (stock["product_id"],)
        )

        product = cursor.fetchone()

        if product is None:
            connection.rollback()
            flash("Product not found.", "error")
            return redirect(url_for("record_incoming_stock"))

        # Calculate inventory after removing this receipt
        new_stock = (
            product["quantity_in_stock"]
            - stock["quantity_received"]
        )

        # Prevent negative inventory
        if new_stock < 0:
            connection.rollback()
            flash(
                "Cannot delete this receipt because "
                "there is insufficient stock remaining.",
                "error"
            )
            return redirect(url_for("record_incoming_stock"))

        # Soft delete: preserve the record in the database
        cursor.execute(
            """
            UPDATE incoming_stock
            SET is_active = FALSE
            WHERE stock_id = %s AND is_active = TRUE
            """,
            (stock_id,)
        )

        # Adjust the product's inventory
        cursor.execute(
            """
            UPDATE products
            SET quantity_in_stock = %s
            WHERE product_id = %s
            """,
            (new_stock, stock["product_id"])
        )


        # User Story #10: Log deleted incoming stock
        previous_quantity = product["quantity_in_stock"]

        cursor.execute(
            """
            INSERT INTO stock_audit_log (
                product_id,
                action_type,
                previous_quantity,
                new_quantity,
                quantity_change,
                changed_by,
                description
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                stock["product_id"],
                "STOCK_RECEIPT_DELETED",
                previous_quantity,
                new_stock,
                -stock["quantity_received"],
                session["user_id"],
                f"Incoming stock receipt #{stock_id} deleted. "
                f"Reversed {stock['quantity_received']} unit(s)."
            )
        )


        # Save both changes together
        connection.commit()

        flash(
            "Incoming stock record deleted successfully. "
            "Inventory has been adjusted.",
            "success"
        )

        return redirect(url_for("record_incoming_stock"))

    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()

        flash(
            "Database error. Please try again.",
            "error"
        )
        return redirect(url_for("record_incoming_stock"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# User Story #10: View Stock Audit Log
@app.route("/stock/audit-log", methods=["GET"])
def view_stock_audit_log():

    # User must be logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only Owners and Managers can view audit records
    if session.get("role") not in ["OWNER", "MANAGER"]:
        return "Access denied.", 403

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

       
        cursor.execute(
            """
            SELECT
                a.log_id,
                a.product_id,
                p.product_name,
                a.action_type,
                a.previous_quantity,
                a.new_quantity,
                a.quantity_change,
                u.name AS changed_by_name,
                a.change_date,
                a.description
            FROM stock_audit_log AS a
            JOIN products AS p
                ON a.product_id = p.product_id
            JOIN users AS u
                ON a.changed_by = u.user_id
            ORDER BY a.change_date DESC, a.log_id DESC
            """
        )


        audit_logs = cursor.fetchall()

        return render_template(
            "stock_audit_log.html",
            audit_logs=audit_logs
        )

    except mysql.connector.Error as error:
        print("Stock Audit Log database error:", error)
        flash("Unable to load stock audit records.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# Logout and Switch Account
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))




if __name__ == "__main__":
    app.run(debug=True)

