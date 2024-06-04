from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import pymongo
from boilerpy3 import extractors
from datetime import datetime, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import MongoDBVectorStore
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
import os

load_dotenv()

app = Flask(__name__)

# MongoDB Configuration
MONGO_URI = "mongodb://localhost:27017/"
client = pymongo.MongoClient(MONGO_URI)
db = client["finollama"]
content_collection = db["content"]

# Google Gemini API Key
google_api_key = os.getenv("GOOGLE_API_KEY")

if google_api_key is None:
    raise ValueError("GOOGLE_API_KEY not found in the environment variables.")

# Initialize LLM and embeddings
llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=google_api_key, temperature=0.2)
embeddings = OpenAIEmbeddings()

# Initialize MongoDB Vector Store
vectordb = MongoDBVectorStore(client, db_name="finollama", collection_name="vectors", embedding_model=embeddings)

def get_qa_chain():
    # Create a retriever for querying the vector database
    retriever = vectordb.as_retriever(score_threshold=0.7)

    prompt_template = """Extract all the fact sentences from the following content into an array of objects. Each object should have the properties: sentence, type (set to "fact"), and source (set to "gemini" for the Gemini API or "local" for the local retriever).

    CONTENT: {context}"""

    PROMPT = PromptTemplate(
        template=prompt_template, input_variables=["context"]
    )

    chain = RetrievalQA.from_chain_type(llm=llm,
                                        chain_type="stuff",
                                        retriever=retriever,
                                        input_key="query",
                                        return_source_documents=True,
                                        chain_type_kwargs={"prompt": PROMPT})

    return chain

def extract_facts_from_gemini(content):
    question = "Extract all fact sentences."
    chain = RetrievalQA.from_llm(llm=llm, prompt=question)
    response = chain({"context": content})
    facts = []

    for line in response["text"].split('\n'):
        facts.append({
            "sentence": line.strip(),
            "type": "fact",
            "source": "gemini"
        })

    return facts

def extract_facts(content):
    # Extract facts using the local retriever
    chain = get_qa_chain()
    local_response = chain({"query": content})
    local_facts = []

    for doc in local_response["source_documents"]:
        local_facts.append({
            "sentence": doc.page_content.strip(),
            "type": "fact",
            "source": "local"
        })

    # Extract facts using Google Gemini
    gemini_facts = extract_facts_from_gemini(content)

    # Combine facts from both sources
    combined_facts = local_facts + gemini_facts

    return combined_facts

@app.route('/explore', methods=['GET', 'POST'])
def explore():
    data = None
    url = ""

    if request.method == 'POST':
        url = request.form['url']
        cached_content = content_collection.find_one({"url": url})
        if cached_content and (datetime.now() - cached_content["timestamp"]) < timedelta(minutes=5):
            content = cached_content["content"]
            facts = cached_content["facts"]
        else:
            # Fetch new content
            extractor = extractors.ArticleExtractor()
            content = extractor.get_content_from_url(url)
            
            # Extract facts using Google Gemini and local retriever
            facts = extract_facts(content)
            
            # Save new content and facts to MongoDB with a timestamp
            content_document = {
                "url": url,
                "content": content,
                "facts": facts,
                "timestamp": datetime.now()
            }
            
            # Update or insert the document
            content_collection.update_one({"url": url}, {"$set": content_document}, upsert=True)
        
        # Format data for JSON response
        safe_count = sum(1 for fact in facts if 'safe' in fact["sentence"].lower())
        context_required_count = sum(1 for fact in facts if 'context required' in fact["sentence"].lower())
        misleading_count = sum(1 for fact in facts if 'misleading' in fact["sentence"].lower())
        unverified_count = sum(1 for fact in facts if 'unverified' in fact["sentence"].lower())
        
        data = {
            "outline": {
                "url": url,
                "safe_count": safe_count,
                "context_required_count": context_required_count,
                "misleading_count": misleading_count,
                "unverified_count": unverified_count
            },
            "analysis": facts,
            "text": content,
        }

    return jsonify(data)

@app.route('/')
def index():
    return render_template('pages/help/home.html')

if __name__ == "__main__":
    app.run(debug=True)
