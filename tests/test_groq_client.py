import os
import logging
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from blueprints.ai import groq_client
from openai import OpenAI

# ----------------------------------------------------------------------
# Tests for _get_client
# ----------------------------------------------------------------------

def test_get_client_raises_if_no_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
        groq_client._get_client()

def test_get_client_returns_openai_client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    # Setting the env var here doesn't update the module-level constant GROQ_API_BASE_URL
    # because it was already imported. We need to patch the constant or reload.
    # Patching is easier.
    
    with patch("blueprints.ai.groq_client.GROQ_API_BASE_URL", "https://fake.url"):
        with patch("blueprints.ai.groq_client.OpenAI") as mock_openai:
            client = groq_client._get_client()
            mock_openai.assert_called_once_with(base_url="https://fake.url", api_key="fake-key")
            assert client == mock_openai.return_value

# ----------------------------------------------------------------------
# Tests for _build_routes_summary
# ----------------------------------------------------------------------

def test_build_routes_summary_empty():
    assert groq_client._build_routes_summary({}) == ""

def test_build_routes_summary_items():
    routes = {"scheduler_index": "/scheduler", "dashboard": "/"}
    summary = groq_client._build_routes_summary(routes)
    assert "Here are the key pages this user can access:" in summary
    assert "- Scheduler Index: /scheduler" in summary
    assert "- Dashboard: /" in summary

# ----------------------------------------------------------------------
# Tests for _build_pages_summary
# ----------------------------------------------------------------------

def test_build_pages_summary_empty():
    assert groq_client._build_pages_summary({}) == ""

def test_build_pages_summary_items():
    pages = {"dashboard": "Welcome to dashboard", "about": "About page"}
    summary = groq_client._build_pages_summary(pages)
    assert "Here are plain-text snapshots of key pages" in summary
    assert "- Dashboard: Welcome to dashboard" in summary
    assert "- About: About page" in summary

# ----------------------------------------------------------------------
# Tests for _build_system_prompt
# ----------------------------------------------------------------------

def test_build_system_prompt_student():
    context = {"role": "student", "routes": {}, "pages": {}, "current_path": "/home"}
    prompt = groq_client._build_system_prompt(context)
    assert "You are answering questions for a STUDENT user." in prompt
    assert "The current page path is: /home" in prompt

def test_build_system_prompt_admin():
    context = {"role": "admin", "routes": {}, "pages": {}, "current_path": "/admin"}
    prompt = groq_client._build_system_prompt(context)
    assert "You are answering questions for an ADMIN user." in prompt

def test_build_system_prompt_supervisor_default():
    # Role "supervisor" or any unknown role defaults to supervisor template
    context = {"role": "supervisor", "routes": {}, "pages": {}}
    prompt = groq_client._build_system_prompt(context)
    assert "You are answering questions for a SUPERVISOR" in prompt

    context2 = {"role": "unknown", "routes": {}, "pages": {}}
    prompt2 = groq_client._build_system_prompt(context2)
    assert "You are answering questions for a SUPERVISOR" in prompt2

# ----------------------------------------------------------------------
# Tests for _chat_completion_with_model_fallbacks
# ----------------------------------------------------------------------

def test_chat_completion_success_first_try():
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion
    
    # We patch MODELS to a single entry to keep it simple
    with patch("blueprints.ai.groq_client.MODELS", ["model-1"]):
        result = groq_client._chat_completion_with_model_fallbacks(mock_client, [])
        assert result == mock_completion
        mock_client.chat.completions.create.assert_called_once()

def test_chat_completion_fallback():
    mock_client = MagicMock()
    mock_completion = MagicMock()
    
    # First call raises, second succeeds
    mock_client.chat.completions.create.side_effect = [Exception("Fail 1"), mock_completion]
    
    with patch("blueprints.ai.groq_client.MODELS", ["model-1", "model-2"]):
        result = groq_client._chat_completion_with_model_fallbacks(mock_client, [])
        assert result == mock_completion
        assert mock_client.chat.completions.create.call_count == 2

def test_chat_completion_all_fail():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("All failed")
    
    with patch("blueprints.ai.groq_client.MODELS", ["model-1", "model-2"]):
        with pytest.raises(Exception, match="All failed"):
            groq_client._chat_completion_with_model_fallbacks(mock_client, [])

def test_chat_completion_no_models():
    mock_client = MagicMock()
    with patch("blueprints.ai.groq_client.MODELS", []):
        with pytest.raises(RuntimeError, match="No Groq models are configured"):
            groq_client._chat_completion_with_model_fallbacks(mock_client, [])

# ----------------------------------------------------------------------
# Tests for get_navigation_help
# ----------------------------------------------------------------------

@patch("blueprints.ai.groq_client._get_client")
@patch("blueprints.ai.groq_client._chat_completion_with_model_fallbacks")
def test_get_navigation_help_success(mock_chat, mock_get_client):
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = " Use the sidebar. "
    mock_chat.return_value = mock_completion
    
    answer = groq_client.get_navigation_help("How do I navigate?", {})
    assert answer == "Use the sidebar."

@patch("blueprints.ai.groq_client._get_client")
@patch("blueprints.ai.groq_client._chat_completion_with_model_fallbacks")
def test_get_navigation_help_empty_content(mock_chat, mock_get_client):
    # Case where model returns empty string or None
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "" 
    mock_chat.return_value = mock_completion
    
    answer = groq_client.get_navigation_help("Question", {})
    assert "I wasn't able to generate a helpful answer" in answer

@patch("blueprints.ai.groq_client._get_client")
@patch("blueprints.ai.groq_client._chat_completion_with_model_fallbacks")
def test_get_navigation_help_malformed_response(mock_chat, mock_get_client):
    # Case where accessing choices fails
    mock_chat.return_value = MagicMock()
    # Force an attribute error or similar when accessing content
    type(mock_chat.return_value).choices = PropertyMock(side_effect=Exception("Bad structure"))
    
    # We need to mock PropertyMock if not using unittest.mock directly for properties,
    # but simplest is to just make it raise when accessed.
    # Actually, let's just make the completion object raise on access
    mock_completion = MagicMock()
    # This setup for property access raising exception:
    p = PropertyMock(side_effect=Exception("Bad structure"))
    type(mock_completion).choices = p
    mock_chat.return_value = mock_completion
    
    answer = groq_client.get_navigation_help("Question", {})
    assert "I wasn't able to generate a helpful answer" in answer

# ----------------------------------------------------------------------
# Tests for model selection logic (module level code)
# ----------------------------------------------------------------------
# We can't easily test the module-level execution without reloading,
# but we can verify the logic by inspecting the variables if we manipulate env.
# However, since the module is already imported, we might check what MODELS is.

def test_models_variable_logic(monkeypatch):
    # We can simulate the logic by running it manually
    import importlib
    
    # Case 1: No env var
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    importlib.reload(groq_client)
    assert groq_client.MODELS == groq_client._DEFAULT_MODELS
    
    # Case 2: With env var
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    importlib.reload(groq_client)
    assert groq_client.MODELS[0] == "custom-model"
    assert "custom-model" not in groq_client.MODELS[1:]

def test_load_dotenv_permission_error(monkeypatch, caplog):
    import importlib
    import logging
    # We need to ensure we are patching the load_dotenv that is used. 
    # Since groq_client does 'from dotenv import load_dotenv', patching 'dotenv.load_dotenv'
    # works if we reload.

    def mock_raise(*args, **kwargs):
        raise PermissionError("Access denied")

    monkeypatch.setattr("dotenv.load_dotenv", mock_raise)

    with caplog.at_level(logging.WARNING):
        importlib.reload(groq_client)
    
    assert "AI assistant: unable to read .env; continuing without it." in caplog.text
