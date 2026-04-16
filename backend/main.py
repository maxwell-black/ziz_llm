# /backend/main.py
import os
import textwrap
import logging # Use logging instead of print for Cloud Run
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from langchain.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate
from google.cloud import secretmanager # To get API key

# --- Configuration ---
logging.basicConfig(level=logging.INFO) # Configure logging

# Get API Key from Secret Manager
# !!! IMPORTANT: Replace YOUR_PROJECT_ID with your actual Google Cloud Project ID !!!
GCP_PROJECT_ID = "ziz-llm" # <--- CHANGE THIS
SECRET_ID = "zizek-google-api-key" # The name you gave the secret in Secret Manager
SECRET_VERSION = "latest" # Usually 'latest' or a specific version number like '1'

try:
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_ID}/versions/{SECRET_VERSION}"
    response = client.access_secret_version(request={"name": secret_name})
    os.environ["GOOGLE_API_KEY"] = response.payload.data.decode("UTF-8")
    logging.info(f"GOOGLE_API_KEY loaded from Secret Manager: {SECRET_ID}")
except Exception as e:
    logging.error(f"Failed to load GOOGLE_API_KEY ({SECRET_ID}) from Secret Manager: {e}")
    # The application will continue, but Langchain/Gemini calls will likely fail later.

# --- Paths (Relative to Docker container's working directory /app) ---
# Assumes FAISS index files are copied into '/app/faiss_index' inside the container
index_cache_dir = "faiss_index"
# Assumes React build files are copied into '/app/react_build' inside the container
react_build_dir = "react_build"

# --- Initialize Langchain Components ---
llm = None
qa = None
try:
    # Check only if the directory exists; embeddings handle file loading checks
    if not os.path.isdir(index_cache_dir):
         logging.error(f"FAISS index directory not found at expected location: {index_cache_dir}")
    else:
        logging.info("Initializing Langchain components...")
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        # Allow dangerous deserialization as we trust the index we're packaging
        db = FAISS.load_local(index_cache_dir, embeddings, allow_dangerous_deserialization=True)
        llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-pro-latest", temperature=0.7)
        memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5) # k=5 history window
        custom_template = """ You are embodying the persona of the AUTHOR (the AUTHOR's name is "Ž") of the texts provided in the Context. Feel free to engage in a disquisition, but this disquisition should treat, explicitly, the topic and themes in the QUESTION. Your response should be in the style of the AUTHOR, mimic the way that he writes. Context: {context} Question: {question} Answer (as the AUTHOR): """
        qa_prompt = PromptTemplate(template=custom_template, input_variables=["question", "context"])
        qa = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=db.as_retriever(),
            memory=memory,
            combine_docs_chain_kwargs={"prompt": qa_prompt}
        )
        logging.info("Langchain components initialized successfully.")
except Exception as e:
    # Log the full error during initialization for debugging
    logging.exception(f"CRITICAL Error during Langchain/FAISS initialization: {e}")
    # llm and qa remain None, the /chat endpoint will return an error

# --- Flask Application ---
# Serve static files from the react_build_dir relative to the app's root
app = Flask(__name__, static_folder=react_build_dir, static_url_path='/')
CORS(app) # Enable CORS, useful if you ever separate frontend/backend URLs

# --- API Endpoint ---
@app.route('/chat', methods=['POST'])
def chat():
    # Check if Langchain components initialized correctly
    if not llm or not qa:
         logging.error("Chat endpoint called but LLM/QA chain not initialized. Check initialization logs.")
         return jsonify({"error": "Chat service is not ready due to initialization failure."}), 503 # Service Unavailable

    if not request.is_json:
        logging.warning("Received non-JSON request to /chat")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    query = data.get('query')
    if not query:
        logging.warning("Received empty query in /chat request")
        return jsonify({"error": "Missing 'query' in request body"}), 400

    logging.info(f"Received query: {query[:50]}...") # Log snippet
    try:
        # Ensure qa object is valid before calling
        if not qa: raise RuntimeError("QA chain is not available.")

        result = qa({"question": query})
        answer = result.get("answer", "Sorry, I encountered an issue generating a response.").strip()
        logging.info(f"Generated answer: {answer[:100]}...")
        return jsonify({"answer": answer})
    except Exception as e:
        # Log the full error for debugging backend issues
        logging.exception(f"Error processing chat query '{query[:50]}...': {e}")
        return jsonify({"error": "An internal server error occurred while processing the chat request."}), 500

# --- Serve React App ---
# Serve 'index.html' for the root URL and any other path not matching a static file
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    # If path exists in static folder (e.g., CSS, JS), serve it
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        # Otherwise, serve index.html for client-side routing
        # Check if index.html exists first
        index_path = os.path.join(app.static_folder, 'index.html')
        if not os.path.exists(index_path):
            logging.error(f"index.html not found in static folder: {app.static_folder}")
            return jsonify({"error": "Frontend index.html not found."}), 404
        return send_from_directory(app.static_folder, 'index.html')

# --- Run Server (for Cloud Run) ---
if __name__ == '__main__':
    # Cloud Run provides the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    # Gunicorn will run this Flask app instance
    # The host must be '0.0.0.0' to accept connections from Cloud Run's proxy
    logging.info(f"Starting Flask server on host 0.0.0.0 port {port}")
    # Turn off Flask's development server reloader when run by Gunicorn
    app.run(host='0.0.0.0', port=port, debug=False)