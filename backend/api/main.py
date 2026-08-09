from fastapi import FastAPI
from pydantic import BaseModel

from intelligence.discovery import discover_topics
from intelligence.content_generator import generate_article


app = FastAPI(title="AI Content Creator API")


class ArticleRequest(BaseModel):
    limit: int = 1


@app.get("/")
def home():
    return {"message": "AI Content Creator API is running"}


@app.get("/articles")
def generate_articles(limit: int = 1):

    topics = discover_topics(limit=limit)

    articles = []

    for topic in topics:
        article = generate_article(topic)
        articles.append(article)

    return {
        "count": len(articles),
        "articles": articles
    }