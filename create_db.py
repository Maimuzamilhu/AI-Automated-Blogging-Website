from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./articles.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Use the newer import location for declarative_base
Base = declarative_base()

class ArticleDB(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    preview = Column(String(250), nullable=True)
    author = Column(String(100), nullable=True)
    date = Column(String(100), nullable=True)
    link = Column(String(500), nullable=True)
    category = Column(String(50), server_default='technology', nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

def init_db():
    try:
        Base.metadata.drop_all(bind=engine)  # Drop existing tables
        Base.metadata.create_all(bind=engine)  # Create new tables
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_db() 