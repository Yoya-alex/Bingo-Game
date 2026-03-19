"""
PostgreSQL Password Reset Script
Run this AFTER you've set pg_hba.conf to 'trust' mode
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys

def reset_password():
    print("=" * 60)
    print("PostgreSQL Password Reset")
    print("=" * 60)
    
    print("\n⚠️  IMPORTANT: Make sure you've set pg_hba.conf to 'trust' mode")
    print("   and restarted PostgreSQL service before running this!\n")
    
    proceed = input("Have you done this? (yes/no): ").strip().lower()
    if proceed != 'yes':
        print("\n❌ Please follow the instructions in reset_postgres_password.md first")
        sys.exit(1)
    
    try:
        # Connect without password (trust mode)
        print("\n[1/5] Connecting to PostgreSQL...")
        conn = psycopg2.connect(
            host='localhost',
            database='postgres',
            user='postgres',
            port=5432
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        print("✅ Connected successfully!")
        
        # Reset postgres user password
        print("\n[2/5] Resetting postgres user password...")
        new_password = "postgres123"
        cur.execute(f"ALTER USER postgres WITH PASSWORD '{new_password}';")
        print(f"✅ postgres password set to: {new_password}")
        
        # Create yoadmin user
        print("\n[3/5] Creating yoadmin user...")
        try:
            cur.execute("DROP USER IF EXISTS yoadmin;")
            cur.execute("CREATE USER yoadmin WITH PASSWORD 'aaeyb';")
            cur.execute("ALTER USER yoadmin CREATEDB;")
            print("✅ User 'yoadmin' created with password: aaeyb")
        except Exception as e:
            print(f"⚠️  User creation: {e}")
        
        # Create database
        print("\n[4/5] Creating bingo_bot database...")
        try:
            cur.execute("SELECT 1 FROM pg_database WHERE datname='bingo_bot'")
            if cur.fetchone():
                print("⚠️  Database 'bingo_bot' already exists")
            else:
                cur.execute("CREATE DATABASE bingo_bot OWNER yoadmin;")
                print("✅ Database 'bingo_bot' created")
        except Exception as e:
            print(f"⚠️  Database creation: {e}")
        
        # Grant privileges
        print("\n[5/5] Granting privileges...")
        cur.execute("GRANT ALL PRIVILEGES ON DATABASE bingo_bot TO yoadmin;")
        print("✅ Privileges granted!")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ Password reset completed successfully!")
        print("=" * 60)
        print("\n📝 IMPORTANT NEXT STEPS:")
        print("1. Change pg_hba.conf back from 'trust' to 'scram-sha-256'")
        print("2. Restart PostgreSQL service")
        print("3. Run: python manage.py migrate")
        print("\n🔑 Credentials:")
        print(f"   postgres user password: {new_password}")
        print("   yoadmin user password: aaeyb")
        print("   Database: bingo_bot")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. PostgreSQL is running")
        print("2. pg_hba.conf is set to 'trust' mode")
        print("3. PostgreSQL service was restarted after changing pg_hba.conf")
        sys.exit(1)

if __name__ == "__main__":
    reset_password()
