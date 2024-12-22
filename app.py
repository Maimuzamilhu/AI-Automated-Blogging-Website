import os
import google.generativeai as genai

# Configure Google Gemini API
GOOGLE_API_KEY = "AIzaSyA_Wkb7YQgw4vY7ECIW5NhoxIiaKb9WvcY"
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
genai.configure(api_key=GOOGLE_API_KEY)

# Rest of your imports
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Dict
import uvicorn
from sqlalchemy import or_
from sqlalchemy import desc

from math import ceil


# Import the database model from create_db.py
from create_db import ArticleDB, Base, engine, SessionLocal

# FastAPI app setup
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, page: int = 1, db: Session = Depends(get_db)):
    # Number of articles per page
    per_page = 3
    
    # Get total number of articles
    total_articles = db.query(ArticleDB).count()
    total_pages = (total_articles + per_page - 1) // per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages))
    
    # Get articles for current page
    articles = db.query(ArticleDB)\
        .order_by(desc(ArticleDB.created_at))\
        .offset((page - 1) * per_page)\
        .limit(per_page)\
        .all()
    
    # Get recent articles for sidebar
    recent_articles = db.query(ArticleDB)\
        .order_by(desc(ArticleDB.created_at))\
        .limit(5)\
        .all()
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "articles": articles,
            "recent_articles": recent_articles,
            "current_page": page,
            "total_pages": total_pages
        }
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/all", response_class=HTMLResponse)
async def all_articles(request: Request, db: Session = Depends(get_db)):
    articles = db.query(ArticleDB).order_by(desc(ArticleDB.created_at)).all()
    return templates.TemplateResponse(
        "all.html",
        {"request": request, "articles": articles}
    )

@app.get("/article/{article_id}", response_class=HTMLResponse)
async def article(request: Request, article_id: int, db: Session = Depends(get_db)):
    article = db.query(ArticleDB).filter(ArticleDB.id == article_id).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Rewrite the article content if it hasn't been processed
    if not article.content.startswith('<h1>') and not article.content.startswith('<h2>'):
        try:
            model = genai.GenerativeModel('gemini-pro')
            
            # Enhanced prompt for better article rewriting
            prompt = f"""
            As an expert AI journalist, rewrite and enhance this article following these guidelines:

            # ... (rest of your prompt)

            Original Article:
            {article.content}

            Please rewrite this as a comprehensive, well-structured article following the above guidelines.
            Format in clean HTML with proper semantic structure.
            """

            response = model.generate_content(prompt)
            if response.text:
                article.content = response.text.strip()
                db.commit()
        except Exception as e:
            print(f"Error rewriting article: {str(e)}")
            # Log the full error details
            import traceback
            print(traceback.format_exc())
    
    return templates.TemplateResponse(
        "article.html",
        {"request": request, "article": article}
    )

@app.get("/api/categories/{category}")
async def get_category_articles(category: str, db: Session = Depends(get_db)):
    articles = db.query(ArticleDB).filter(ArticleDB.category == category).order_by(desc(ArticleDB.created_at)).all()
    return articles

@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = None, db: Session = Depends(get_db)):
    if not q:
        return RedirectResponse(url="/")
        
    try:
        articles = db.query(ArticleDB).filter(
            or_(
                ArticleDB.title.ilike(f"%{q}%"),
                ArticleDB.content.ilike(f"%{q}%")
            )
        ).order_by(desc(ArticleDB.created_at)).all()
        
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request, 
                "articles": articles, 
                "query": q
            }
        )
    except Exception as e:
        print(f"Search error: {str(e)}")
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request, 
                "articles": [], 
                "query": q,
                "error": "An error occurred while searching"
            }
        )

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/category/{category}", response_class=HTMLResponse)
async def category(request: Request, category: str, db: Session = Depends(get_db)):
    # Convert category to lowercase for consistency
    category = category.lower()
    
    # Validate category
    valid_categories = ["technology", "finance", "sports"]
    if category not in valid_categories:
        raise HTTPException(status_code=404, detail="Category not found")
    
    articles = db.query(ArticleDB).filter(ArticleDB.category == category).order_by(desc(ArticleDB.created_at)).all()
    return templates.TemplateResponse(
        "category.html",
        {"request": request, "articles": articles, "category": category}
    )

@app.post("/api/upload")
async def upload_article(article: Dict, db: Session = Depends(get_db)):
    try:
        db_article = ArticleDB(
            title=article['title'],
            content=article['content'],
            preview=article.get('preview', ''),
            author=article.get('author', 'Unknown'),
            date=article.get('date', datetime.now().strftime("%Y-%m-%d")),
            link=article.get('link', ''),
            category=article.get('category', 'technology')
        )
        db.add(db_article)
        db.commit()
        db.refresh(db_article)
        return {"status": "success", "message": "Article uploaded successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)