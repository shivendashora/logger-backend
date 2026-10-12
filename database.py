from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base,sessionmaker


DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/logger-db"

engine = create_engine(DB_URL)
sessionLocal  = sessionmaker(bind = engine,autocommit = False,autoflush=True)
Base = declarative_base()
