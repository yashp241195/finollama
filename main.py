from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
from boilerpy3 import extractors

from utils import validate_url, extract_json_from_content, generate_content_hash, extract_facts_via_google_gemini
import httpx
from datetime import datetime, timedelta
import motor.motor_asyncio

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MONGO_URI = "mongodb://localhost:27017/"

# MongoDB setup
MONGO_URI = os.getenv("MONGODB_URI")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client["finollama"]
content_collection = db["content"]

# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("pages/help/home.html", {"request": request})

@app.get("/explore", response_class=HTMLResponse)
async def explore_get(request: Request):
    return templates.TemplateResponse("pages/content/explore.html", {"request": request})

@app.post("/explore", response_class=HTMLResponse)
async def explore_post(request: Request, url: str = Form(...)):

    content = ""
    facts = ""
    error = None

    url = url.strip()
    url = validate_url(url)

    if not url:
        error = "URL is required"
        return templates.TemplateResponse('pages/content/explore.html', {"request": request, "url": url, "content": content, "facts": facts, "error": error})

    cached_content = await content_collection.find_one({"url": url})
    if cached_content and (datetime.now() - cached_content["timestamp"]) < timedelta(minutes=5):
        content = cached_content["content"]
        facts = cached_content.get("facts", "")
    else:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
                extractor = extractors.ArticleExtractor()
                content = extractor.get_content(html_content)
                new_content_hash = generate_content_hash(content)
                if cached_content and cached_content.get("content_hash") == new_content_hash:
                    content = cached_content["content"]
                    facts = cached_content.get("facts", "")
                else:
                    facts = await extract_facts_via_google_gemini(content)
                    facts = extract_json_from_content(facts)
                    content_document = {
                        "url": url,
                        "content": content,
                        "content_hash": new_content_hash,
                        "facts": facts,
                        "timestamp": datetime.now()
                    }
                    await content_collection.update_one({"url": url}, {"$set": content_document}, upsert=True)
        except httpx.RequestError as e:
            error = f"Error fetching content: {e}"
        except Exception as e:
            error = f"Unexpected error: {e}"
    
    return templates.TemplateResponse('pages/content/explore.html', {"request": request, "url": url, "content": content, "facts": facts, "error": error})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
