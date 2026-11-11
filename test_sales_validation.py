
from app import app
from db import get_db_connection
from flask_wtf.csrf import generate_csrf

# Replace this with your actual Manager user ID.
MANAGER_USER_ID = None


# Retrieve a valid Manager account for testing.
manager_connection = get_db_connection()
manager_cursor = manager_connection.cursor(dictionary=True)

try:
    manager_cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE role = 'MANAGER'
        ORDER BY user_id
        LIMIT 1
        """
    )

    manager = manager_cursor.fetchone()

    if manager is None:
        raise RuntimeError("No Manager account found.")

    MANAGER_USER_ID = manager["user_id"]

finally:
    manager_cursor.close()
    manager_connection.close()


with app.test_client() as client:
    # Simulate an authenticated Manager session.
    with client.session_transaction() as sess:
        sess["user_id"] = MANAGER_USER_ID
        sess["role"] = "MANAGER"
        sess["user_name"] = "Test Manager"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT product_id, quantity_in_stock
            FROM products
            WHERE sku = %s AND is_active = TRUE
            """,
            ("HP001",)
        )
        product = cursor.fetchone()

        if product is None:
            raise RuntimeError("HP001 was not found.")

       
        original_stock = product["quantity_in_stock"]
        invalid_quantity = original_stock + 1

        # Count sales before the invalid request.
        cursor.execute(
            "SELECT COUNT(*) AS total FROM sales WHERE product_id = %s",
            (product["product_id"],)
        )
        sales_before = cursor.fetchone()["total"]



        # Obtain a valid CSRF token for the test session.
        with client.session_transaction() as sess:
            with app.test_request_context():
                from flask import session
                for key, value in sess.items():
                    session[key] = value
                csrf_token = generate_csrf()
                sess["csrf_token"] = session["csrf_token"]

        response = client.post(
            "/sales/record",
            data={
                "product_id": product["product_id"],
                "quantity_sold": invalid_quantity,
                "csrf_token": csrf_token
            },
            follow_redirects=False
        )

        print("HTTP status:", response.status_code)
        print("Redirect:", response.headers.get("Location"))

        cursor.execute(
            """
            SELECT quantity_in_stock
            FROM products
            WHERE product_id = %s
            """,
            (product["product_id"],)
        )

        updated_stock = cursor.fetchone()["quantity_in_stock"]
        
        # Count sales after the invalid request.
        cursor.execute(
            "SELECT COUNT(*) AS total FROM sales WHERE product_id = %s",
            (product["product_id"],)
        )
        sales_after = cursor.fetchone()["total"]

        print("Sales before test:", sales_before)
        print("Sales after test:", sales_after)

        assert sales_after == sales_before, (
            "An invalid sale was incorrectly saved!"
        )


        print("Original stock:", original_stock)
        print("Attempted sale:", invalid_quantity)
        print("Stock after test:", updated_stock)

        assert response.status_code == 302, (
            "Expected a redirect after rejecting the sale."
        )
        assert updated_stock == original_stock, (
            "Stock changed after an invalid sale!"
        )

        print("PASS: Invalid sale rejected; stock unchanged.")

    finally:
        cursor.close()
        connection.close()
