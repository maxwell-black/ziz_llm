import unittest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Prevent secret manager from attempting network calls
sys.modules['google.cloud.secretmanager'] = MagicMock()

# Import the module to be tested
import main

class TestChatEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = main.app.test_client()

    def test_chat_returns_503_when_uninitialized(self):
        # By default in our mocked environment, main.llm and main.qa will be None
        # because the initialization block will fail (no real API key or mock embeddings that pass)
        main.llm = None
        main.qa = None

        response = self.app.post('/chat', json={"query": "hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("Chat service is not ready", response.get_json()["error"])

    def test_chat_returns_200_when_initialized(self):
        # Mocking initialized state
        main.llm = MagicMock()
        main.qa = MagicMock()
        main.qa.return_value = {"answer": "mock answer"}

        response = self.app.post('/chat', json={"query": "hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["answer"], "mock answer")

class TestLangchainInitialization(unittest.TestCase):
    @patch('main.logging.exception')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_value_error(self, mock_isdir, mock_logging):
        import importlib

        with patch('main.GoogleGenerativeAIEmbeddings', side_effect=ValueError("Test ValueError")):
            importlib.reload(main)
            self.assertIsNone(main.llm)
            self.assertIsNone(main.qa)
            mock_logging.assert_called()

    @patch('main.logging.exception')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_runtime_error(self, mock_isdir, mock_logging):
        import importlib

        with patch('main.GoogleGenerativeAIEmbeddings'):
            with patch('main.FAISS.load_local', side_effect=RuntimeError("Test RuntimeError")):
                importlib.reload(main)
                self.assertIsNone(main.llm)
                self.assertIsNone(main.qa)
                mock_logging.assert_called()

    @patch('main.logging.exception')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_file_not_found_error(self, mock_isdir, mock_logging):
        import importlib

        with patch('main.GoogleGenerativeAIEmbeddings'):
            with patch('main.FAISS.load_local', side_effect=FileNotFoundError("Test FileNotFoundError")):
                importlib.reload(main)
                self.assertIsNone(main.llm)
                self.assertIsNone(main.qa)
                mock_logging.assert_called()

    @patch('main.logging.exception')
    @patch('main.os.path.isdir', return_value=True)
    def test_init_catches_general_exception(self, mock_isdir, mock_logging):
        import importlib

        with patch('main.GoogleGenerativeAIEmbeddings'):
            # Triggering an arbitrary Exception
            with patch('main.FAISS.load_local', side_effect=Exception("Test Unknown Exception")):
                importlib.reload(main)
                self.assertIsNone(main.llm)
                self.assertIsNone(main.qa)
                mock_logging.assert_called()

if __name__ == '__main__':
    unittest.main()
