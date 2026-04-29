import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# --- Targeted Mocking to allow importing main in restricted environment ---
# This is necessary because the sandbox lacks standard dependencies like Flask and LangChain.
for module in [
    'flask', 'flask_cors', 'langchain_community.vectorstores',
    'langchain_google_genai', 'langchain.chains', 'langchain.memory',
    'langchain.prompts', 'google', 'google.cloud', 'google.cloud.secretmanager'
]:
    sys.modules[module] = MagicMock()

import flask
# Mock Flask app and its route decorator to allow importing main.py
mock_app = MagicMock()
def mock_route(rule, **options):
    def decorator(f):
        return f
    return decorator
mock_app.route = mock_route
flask.Flask = MagicMock(return_value=mock_app)
flask.request = MagicMock()
flask.jsonify = lambda x: x # Simple identity for mock jsonify

# --- End of Mocking ---

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the module to be tested
import main

class MockResponse:
    """A minimal mock for Flask's Response object."""
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code
    def get_json(self):
        return self.json_data

class TestChatEndpoint(unittest.TestCase):
    def setUp(self):
        # We simulate Flask's test_client.post by calling main.chat() directly
        # while mocking the request context and jsonify.
        self.client = MagicMock()
        main.app.test_client = MagicMock(return_value=self.client)

        def mock_post(path, json=None, data=None, content_type=None):
            if path != '/chat':
                return MockResponse({"error": "Not Found"}, 404)

            with patch('main.request') as mock_request, \
                 patch('main.jsonify') as mock_jsonify:

                # Mock jsonify to return its input data
                mock_jsonify.side_effect = lambda x: x

                mock_request.is_json = (json is not None) or (content_type == 'application/json')
                mock_request.get_json.return_value = json

                result = main.chat()

                if isinstance(result, tuple):
                    return MockResponse(result[0], result[1])
                return MockResponse(result, 200)

        self.client.post = mock_post
        self.app = main.app.test_client()

    def test_chat_returns_503_when_uninitialized(self):
        main.llm = None
        main.qa = None

        response = self.app.post('/chat', json={"query": "hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("Chat service is not ready", response.get_json()["error"])

    def test_chat_returns_200_when_initialized(self):
        main.llm = MagicMock()
        main.qa = MagicMock()
        main.qa.return_value = {"answer": "mock answer"}

        response = self.app.post('/chat', json={"query": "hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["answer"], "mock answer")

    def test_chat_returns_400_when_not_json(self):
        main.llm = MagicMock()
        main.qa = MagicMock()

        response = self.app.post('/chat', content_type='text/plain')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Request must be JSON")

    def test_chat_returns_400_when_query_missing(self):
        main.llm = MagicMock()
        main.qa = MagicMock()

        response = self.app.post('/chat', json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Missing 'query' in request body")

    def test_chat_returns_400_when_query_empty(self):
        main.llm = MagicMock()
        main.qa = MagicMock()

        response = self.app.post('/chat', json={"query": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Missing 'query' in request body")

    def test_chat_returns_400_when_query_too_long(self):
        main.llm = MagicMock()
        main.qa = MagicMock()

        long_query = "a" * 1001
        response = self.app.post('/chat', json={"query": long_query})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Query too long. Maximum length is 1000 characters.")

class TestLangchainInitialization(unittest.TestCase):
    @patch('main.logging.exception')
    @patch('main.logging.error')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_value_error(self, mock_isdir, mock_error, mock_exception):
        import importlib
        with patch('main.GoogleGenerativeAIEmbeddings', side_effect=ValueError("Test ValueError")):
            with patch('main.ConversationalRetrievalChain.from_llm', return_value=None):
                importlib.reload(main)
                self.assertTrue(mock_exception.called or mock_error.called)
                self.assertIsNone(main.qa)

    @patch('main.logging.exception')
    @patch('main.logging.error')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_runtime_error(self, mock_isdir, mock_error, mock_exception):
        import importlib
        with patch('main.GoogleGenerativeAIEmbeddings'):
            with patch('main.FAISS.load_local', side_effect=RuntimeError("Test RuntimeError")):
                with patch('main.ConversationalRetrievalChain.from_llm', return_value=None):
                    importlib.reload(main)
                    self.assertTrue(mock_exception.called or mock_error.called)
                    self.assertIsNone(main.qa)

    @patch('main.logging.exception')
    @patch('main.logging.error')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_file_not_found_error(self, mock_isdir, mock_error, mock_exception):
        import importlib
        with patch('main.GoogleGenerativeAIEmbeddings'):
            with patch('main.FAISS.load_local', side_effect=FileNotFoundError("Test FileNotFoundError")):
                with patch('main.ConversationalRetrievalChain.from_llm', return_value=None):
                    importlib.reload(main)
                    self.assertTrue(mock_exception.called or mock_error.called)
                    self.assertIsNone(main.qa)

    @patch('main.logging.exception')
    @patch('main.logging.error')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_general_exception(self, mock_isdir, mock_error, mock_exception):
        import importlib
        with patch('main.GoogleGenerativeAIEmbeddings'):
            with patch('main.FAISS.load_local', side_effect=Exception("Test Unknown Exception")):
                with patch('main.ConversationalRetrievalChain.from_llm', return_value=None):
                    importlib.reload(main)
                    self.assertTrue(mock_exception.called or mock_error.called)
                    self.assertIsNone(main.qa)

if __name__ == '__main__':
    unittest.main()
