#!/usr/bin/env python
from app.db.session import engine
from sqlalchemy import text
from app.models.voting import MyFavorites

# Drop the table
with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS my_favorites CASCADE'))
    conn.commit()
    print('✅ Table dropped')

# Recreate the table
MyFavorites.__table__.create(engine, checkfirst=True)
print('✅ Table recreated with new structure')
