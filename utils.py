import hashlib
import json
import re
from pydantic import BaseModel, HttpUrl, ValidationError
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Environment Variables
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# URL Validation
class URLModel(BaseModel):
    url: HttpUrl

def validate_url(url: str):
    try:
        URLModel(url=url)
        return url
    except ValidationError:
        return None

# JSON Extraction
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

# Generate Content Hash
def generate_content_hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

# Google Gemini Extraction
async def extract_facts_via_google_gemini(content):
    try:
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
    except Exception as e:
        return f"Unexpected error occurred {e} "
