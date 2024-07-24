from flask import Flask, render_template, request
from dotenv import load_dotenv
import pymongo
import hashlib
import os
import requests
from datetime import datetime, timedelta
from pydantic import BaseModel, HttpUrl, ValidationError
from boilerpy3 import extractors
import json
import google.generativeai as genai
import re

load_dotenv()

app = Flask(__name__)


# MONGO_URI = "mongodb://localhost:27017/"

MONGO_PWD = os.getenv("MONGO_PWD")
MONGO_URI = "mongodb+srv://alpha2244:"+MONGO_PWD+"@cluster0.trsdg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client["finollama"]
    content_collection = db["content"]
except pymongo.errors.ConnectionError as e:
    print(f"Connection Error: {e}")
except pymongo.errors.ConfigurationError as e:
    print(f"Configuration Error: {e}")
except Exception as e:
    print(f"Unexpected Error: {e}")

class URLModel(BaseModel):
    url: HttpUrl

def validate_url(url: str) -> str | None:
    try:
        URLModel(url=url)
        return url
    except ValidationError:
        return None

def extract_json_from_content(content):
    try:
        match = re.search(r'```json(.*?)```', content, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            json_obj = json.loads(json_str)
            return json_obj
        else:
            raise ValueError("No JSON found in the content.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON: {e}")


def generate_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def extract_facts_via_google_gemini(content: str) -> str:
    try:
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            f"""  
                {content}

                I wish to get return a json object with 
                following property
                
                1. "50_words_summary" : summary in 50 words

                2. "list_of_facts" : list of facts where each fact has following properties
                  (i) "fact" : the fact string 
                  (ii) "accurate" : accurate, accurate but context required, misleading 
                  (iii) "explanation" : explanation if not accurate/misleading or context required

                sort list of facts in descending order means more misleading 
                should be on top and more accurate on bottom  
                
                strictly return only a json object of all this nothing else.

                please make sure json object you return is valid.

            """
        )
        return response.text
    except genai.GenerativeAIException as e:
        return "Error fetching facts from Google Generative AI"
    except Exception as e:
        return "Unexpected error occurred"

@app.route('/explore', methods=['GET', 'POST'])
def explore():
    url = ""
    content = ""
    facts = ""
    error = None

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url:
            error = "URL is required"
            return render_template('pages/content/explore.html', url=url, content=content, facts=facts, error=error)
        
        url = validate_url(url)
        if url is None:
            error = "Invalid URL format"
            return render_template('pages/content/explore.html', url=url, content=content, facts=facts, error=error)
        cached_content = content_collection.find_one({"url": url})
        if cached_content and (datetime.now() - cached_content["timestamp"]) < timedelta(minutes=5):
            content = cached_content["content"]
            facts = cached_content.get("facts", "")
        else:
            try:
                response = requests.get(url)
                response.raise_for_status()
                html_content = response.text
                extractor = extractors.ArticleExtractor()
                content = extractor.get_content(html_content)
                new_content_hash = generate_content_hash(content)
                
                if cached_content and cached_content.get("content_hash") == new_content_hash:
                    content = cached_content["content"]
                    facts = cached_content.get("facts", "")
                else:
                    facts = extract_facts_via_google_gemini(content)
                    facts = extract_json_from_content(facts)
                    content_document = {
                        "url": url,
                        "content": content,
                        "content_hash": new_content_hash,
                        "facts": facts,
                        "timestamp": datetime.now()
                    }
                    content_collection.update_one({"url": url}, {"$set": content_document}, upsert=True)
            except requests.RequestException as e:
                error = f"Error fetching content: {e}"
            except Exception as e:
                error = f"Unexpected error: {e}"
    
    return render_template('pages/content/explore.html', url=url, content=content, facts=facts, error=error)

@app.route('/')
def index():
    return render_template('pages/help/home.html')

if __name__ == "__main__":
    app.run(debug=True)
