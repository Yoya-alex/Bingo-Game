# Reset PostgreSQL Password on Windows

## Step 1: Backup pg_hba.conf
1. Open File Explorer
2. Navigate to: `C:\Program Files\PostgreSQL\18\data\`
3. Find `pg_hba.conf` file
4. Right-click and copy it to create a backup (name it `pg_hba.conf.backup`)

## Step 2: Edit pg_hba.conf (Requires Admin Rights)
1. Right-click on `pg_hba.conf` and select "Open with Notepad" (as Administrator)
2. Find all lines that say `md5` or `scram-sha-256` 
3. Change them to `trust` temporarily

Example - Change FROM:
```
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256
# IPv6 local connections:
host    all             all             ::1/128                 scram-sha-256
```

TO:
```
# IPv4 local connections:
host    all             all             127.0.0.1/32            trust
# IPv6 local connections:
host    all             all             ::1/128                 trust
```

4. Save the file

## Step 3: Restart PostgreSQL Service
Open PowerShell as Administrator and run:
```powershell
Restart-Service postgresql-x64-18
```

## Step 4: Reset Password
After the service restarts, run this in your project folder:
```bash
python reset_postgres_password.py
```

## Step 5: Restore pg_hba.conf Security
1. Open `pg_hba.conf` again as Administrator
2. Change `trust` back to `scram-sha-256`
3. Save the file
4. Restart PostgreSQL service again:
```powershell
Restart-Service postgresql-x64-18
```

## Done!
Your PostgreSQL password is now reset and you can use the database.
