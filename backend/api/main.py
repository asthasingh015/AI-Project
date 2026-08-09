from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelligence.discovery import discover_topics
from intelligence.content_generator import generate_article


app = FastAPI(title="AI Content Creator API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "AI Content Creator API is running"
    }


@app.get("/articles")
def generate_articles(limit: int = 1):

    topics = discover_topics(limit=50)

    articles = []

    for topic in topics[:limit]:
        article = generate_article(topic)
        articles.append(article)

    return {
        "count": len(articles),
        "articles": articles
    }