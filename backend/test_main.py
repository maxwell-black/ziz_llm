import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Need to append the path so we can import main
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# We need to mock the Secret Manager client before importing main to prevent it from crashing or hanging
with patch('google.cloud.secretmanager.SecretManagerServiceClient'):
    import main

@pytest.fixture
def client():
    # Configure the app for testing
    main.app.config['TESTING'] = True

    # We must ensure main.llm and main.qa are not None for the validation to pass
    main.llm = MagicMock()
    main.qa = MagicMock()

    with main.app.test_client() as client:
        yield client

def test_chat_missing_query(client):
    response = client.post('/chat', json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "Missing 'query' in request body"}

def test_chat_non_json_request(client):
    response = client.post('/chat', data="Not a json")
    assert response.status_code == 400
    assert response.get_json() == {"error": "Request must be JSON"}

@patch('main.qa')
def test_chat_successful_response(mock_qa, client):
    mock_qa.return_value = {"answer": "Mocked response"}

    main.qa = mock_qa
    main.llm = MagicMock()

    response = client.post('/chat', json={"query": "test query"})
    assert response.status_code == 200
    assert response.get_json() == {"answer": "Mocked response"}

def test_chat_service_unavailable(client):
    main.qa = None
    response = client.post('/chat', json={"query": "test query"})
    assert response.status_code == 503
    assert response.get_json() == {"error": "Chat service is not ready due to initialization failure."}

@patch('main.qa')
def test_chat_internal_error(mock_qa, client):
    mock_qa.side_effect = Exception("Internal Error")

    main.qa = mock_qa
    main.llm = MagicMock()

    response = client.post('/chat', json={"query": "test query"})
    assert response.status_code == 500
    assert response.get_json() == {"error": "An internal server error occurred while processing the chat request."}

@patch('main.os.path.exists')
@patch('main.send_from_directory')
def test_serve_index_html(mock_send, mock_exists, client):
    # When fetching /, path is '', so the code falls back to index.html
    # os.path.exists checks the index.html path
    mock_exists.return_value = True
    mock_send.return_value = "Mocked File Content"

    response = client.get('/')
    assert response.status_code == 200
    mock_send.assert_called_with(main.app.static_folder, 'index.html')

@patch('main.os.path.exists')
def test_serve_index_html_missing(mock_exists, client):
    mock_exists.return_value = False

    response = client.get('/')
    assert response.status_code == 404
    assert response.get_json() == {"error": "Frontend index.html not found."}

def test_serve_function():
    # Test the serve view function directly to bypass Flask's static handler logic
    with patch('main.os.path.exists') as mock_exists, \
         patch('main.send_from_directory') as mock_send:

        # Test 1: File exists
        mock_exists.side_effect = lambda p: p.endswith('main.js')
        mock_send.return_value = "Mocked File"

        response = main.serve('static/js/main.js')
        assert response == "Mocked File"
        mock_send.assert_called_with(main.app.static_folder, 'static/js/main.js')

        # Test 2: File doesn't exist, serve index.html
        mock_exists.side_effect = lambda p: p.endswith('index.html')
        mock_send.return_value = "Mocked Index"

        response = main.serve('missing-page')
        assert response == "Mocked Index"
        mock_send.assert_called_with(main.app.static_folder, 'index.html')

        # Test 3: File doesn't exist, index.html doesn't exist either
        mock_exists.side_effect = lambda p: False

        with main.app.app_context():
            response, status = main.serve('missing-page')
            assert status == 404
            assert response.json == {"error": "Frontend index.html not found."}
