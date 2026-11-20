import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
class Base(DeclarativeBase):
    pass
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
if engine.dialect.name == 'sqlite':
    from sqlalchemy import event

    @event.listens_for(engine, 'connect')
    def _sqlite_foreign_keys(dbapi_connection, _record):
        # SQLite only enforces FKs when enabled per connection; production uses PostgreSQL.
        cur = dbapi_connection.cursor(); cur.execute('PRAGMA foreign_keys=ON'); cur.close()
Session = sessionmaker(bind=engine, expire_on_commit=False)
def get_db():
    with Session() as db:
        yield db
