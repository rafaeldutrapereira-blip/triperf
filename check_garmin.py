from api.database import engine
from sqlalchemy import text

with engine.connect() as c:
    row = c.execute(text("SELECT garmin_email, garmin_password FROM users WHERE email='rafael@labx.com'")).fetchone()
    if row:
        print("garmin_email:", row[0])
        print("garmin_password stored:", "YES" if row[1] else "NO")
    else:
        print("Usuario no encontrado")
