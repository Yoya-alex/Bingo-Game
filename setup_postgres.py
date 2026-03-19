"""
PostgreSQL Database Setup Script
This script will help you set up the PostgreSQL database for the Bingo game.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys

def setup_database():
    print("=" * 60)
    print("PostgreSQL Database Setup for Bingo Game")
    print("=" * 60)
    
    # Get PostgreSQL admin credentials
    print("\nEnter PostgreSQL admin credentials:")
    admin_user = input("Admin username (default: postgres): ").strip() or "postgres"
    admin_password = input("Admin password: ").strip()
    
    try:
        # Connect to PostgreSQL as admin
        print("\n[1/4] Connecting to PostgreSQL...")
        conn = psycopg2.connect(
            host='localhost',
            database='postgres',
            user=admin_user,
            password=admin_password,
            port=5432
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        print("✅ Connected successfully!")
        
        # Create user if not exists
        print("\n[2/4] Creating/updating user 'yoadmin'...")
        try:
            cur.execute("DROP USER IF EXISTS yoadmin;")
            cur.execute("CREATE USER yoadmin WITH PASSWORD 'aaeyb';")
            print("✅ User 'yoadmin' created successfully!")
        except Exception as e:
            print(f"⚠️ User creation: {e}")
        
        # Create database if not exists
        print("\n[3/4] Creating database 'bingo_bot'...")
        try:
            cur.execute("DROP DATABASE IF EXISTS bingo_bot;")
            cur.execute("CREATE DATABASE bingo_bot OWNER yoadmin;")
            print("✅ Database 'bingo_bot' created successfully!")
        except Exception as e:
            print(f"⚠️ Database creation: {e}")
        
        # Grant privileges
        print("\n[4/4] Granting privileges...")
        cur.execute("GRANT ALL PRIVILEGES ON DATABASE bingo_bot TO yoadmin;")
        print("✅ Privileges granted!")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ PostgreSQL setup completed successfully!")
        print("=" * 60)
        print("\nYou can now run: python manage.py migrate")
        
    except psycopg2.OperationalError as e:
        print(f"\n❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running")
        print("2. Check your admin password")
        print("3. Verify PostgreSQL is listening on port 5432")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_database()
