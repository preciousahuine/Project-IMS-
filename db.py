
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )

if __name__ == "__main__":
    try:
        connection = get_db_connection()
        print("Successfully connected to MySQL!")
        connection.close()
    except mysql.connector.Error as error:
        print("Database connection failed:", error)
