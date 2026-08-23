"""Tests for DataForSEO client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dataforseo.client import DataForSEOClient

# ─── Configuration ───────────────────────────────────


class TestIsConfigured:
    def test_not_configured_empty(self):
        client = DataForSEOClient()
        assert client.is_configured is False

    def test_not_configured_partial(self):
        client = DataForSEOClient(login="user")
        assert client.is_configured is False

    def test_configured(self):
        client = DataForSEOClient(login="user", password="pass")
        assert client.is_configured is True


# ─── Auth header ─────────────────────────────────────


class TestAuthHeader:
    def test_basic_auth_encoding(self):
        client = DataForSEOClient(login="user@test.com", password="s3cret")
        header = client._get_auth_header()
        assert header.startswith("Basic ")
        # Decode and verify
        import base64

        decoded = base64.b64decode(header.split(" ")[1]).decode()
        assert decoded == "user@test.com:s3cret"


# ─── Unconfigured returns helpful error ──────────────


class TestUnconfiguredMethods:
    @pytest.mark.asyncio
    async def test_search_volume_unconfigured(self):
        client = DataForSEOClient()
        result = await client.get_search_volume(["seo"])
        assert "error" in result
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_serp_results_unconfigured(self):
        client = DataForSEOClient()
        result = await client.get_serp_results("seo")
        assert "error" in result
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_keyword_suggestions_unconfigured(self):
        client = DataForSEOClient()
        result = await client.get_keyword_suggestions("seo")
        assert "error" in result
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_request_unconfigured(self):
        client = DataForSEOClient()
        result = await client._request("/v3/test", [{}])
        assert "error" in result


# ─── Mock helpers ────────────────────────────────────


def _mock_response(json_data, status_code=200):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _dataforseo_response(result_items):
    """Wrap items in DataForSEO task envelope."""
    return {
        "tasks": [
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "result": result_items,
            }
        ]
    }


# ─── Search volume with mock ─────────────────────────


class TestSearchVolume:
    @pytest.mark.asyncio
    async def test_search_volume_success(self):
        client = DataForSEOClient(login="u", password="p")
        api_result = [
            {
                "keyword": "seo",
                "search_volume": 12000,
                "competition": 0.8,
                "cpc": 2.5,
                "monthly_searches": [
                    {"search_volume": 11000},
                    {"search_volume": 13000},
                ],
            },
            {
                "keyword": "seo audit",
                "search_volume": 3200,
                "competition": 0.5,
                "cpc": 1.8,
                "monthly_searches": [],
            },
        ]
        mock_resp = _mock_response(_dataforseo_response(api_result))

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client.get_search_volume(["seo", "seo audit"])

        assert result["source"] == "dataforseo"
        assert len(result["keywords"]) == 2
        assert result["keywords"][0]["keyword"] == "seo"
        assert result["keywords"][0]["search_volume"] == 12000
        assert result["keywords"][0]["trend"] == [11000, 13000]


# ─── SERP results with mock ─────────────────────────


class TestSerpResults:
    @pytest.mark.asyncio
    async def test_serp_results_success(self):
        client = DataForSEOClient(login="u", password="p")
        api_result = [
            {
                "items": [
                    {
                        "type": "organic",
                        "rank_group": 1,
                        "url": "https://example.com/seo",
                        "title": "SEO Guide",
                        "description": "A guide to SEO",
                        "domain": "example.com",
                    },
                    {
                        "type": "featured_snippet",
                        "rank_group": 0,
                        "title": "Snippet",
                    },
                    {
                        "type": "people_also_ask",
                    },
                ]
            }
        ]
        mock_resp = _mock_response(_dataforseo_response(api_result))

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client.get_serp_results("seo")

        assert result["source"] == "dataforseo"
        assert result["keyword"] == "seo"
        assert len(result["results"]) == 1
        assert result["results"][0]["position"] == 1
        assert result["results"][0]["url"] == "https://example.com/seo"
        assert "featured_snippet" in result["serp_features"]
        assert "people_also_ask" in result["serp_features"]


# ─── Keyword suggestions with mock ──────────────────


class TestKeywordSuggestions:
    @pytest.mark.asyncio
    async def test_keyword_suggestions_success(self):
        client = DataForSEOClient(login="u", password="p")
        api_result = [
            {
                "items": [
                    {
                        "keyword_data": {
                            "keyword": "seo tools",
                            "keyword_info": {
                                "search_volume": 5000,
                                "competition": 0.6,
                            },
                            "keyword_properties": {
                                "keyword_difficulty": 45,
                            },
                        }
                    },
                    {
                        "keyword_data": {
                            "keyword": "seo strategy",
                            "keyword_info": {
                                "search_volume": 2200,
                                "competition": 0.4,
                            },
                            "keyword_properties": {
                                "keyword_difficulty": 38,
                            },
                        }
                    },
                ]
            }
        ]
        mock_resp = _mock_response(_dataforseo_response(api_result))

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client.get_keyword_suggestions("seo")

        assert result["source"] == "dataforseo"
        assert result["seed"] == "seo"
        assert len(result["suggestions"]) == 2
        assert result["suggestions"][0]["keyword"] == "seo tools"
        assert result["suggestions"][0]["search_volume"] == 5000
        assert result["suggestions"][0]["difficulty"] == 45


# ─── Error handling ──────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_network_timeout(self):
        import httpx as _httpx

        client = DataForSEOClient(login="u", password="p")

        mock_client = AsyncMock()
        mock_client.post.side_effect = _httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client._request("/v3/test", [{}])

        assert "error" in result
        assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error(self):
        import httpx as _httpx

        client = DataForSEOClient(login="u", password="p")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_resp
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client._request("/v3/test", [{}])

        assert "error" in result
        assert "403" in result["error"]

    @pytest.mark.asyncio
    async def test_api_task_error(self):
        client = DataForSEOClient(login="u", password="p")
        error_response = {
            "tasks": [
                {
                    "status_code": 40000,
                    "status_message": "Invalid request",
                    "result": None,
                }
            ]
        }
        mock_resp = _mock_response(error_response)

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client._request("/v3/test", [{}])

        assert "error" in result
        assert "Invalid request" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_tasks(self):
        client = DataForSEOClient(login="u", password="p")
        mock_resp = _mock_response({"tasks": []})

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataforseo.client.httpx.AsyncClient", return_value=mock_client):
            result = await client._request("/v3/test", [{}])

        assert "error" in result
        assert "No tasks" in result["error"]
