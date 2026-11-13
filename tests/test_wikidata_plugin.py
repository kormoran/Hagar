"""Test del plugin Wikidata, senza accesso di rete reale."""

from __future__ import annotations

import json
import tomllib

from pathlib import Path

import pytest

import core.plugins as plugins

from core.permissions import Capability
from core.plugins import (
    PluginContext,
    ToolPlugin,
    load_tool_plugins,
)
from core.tool_registry import ToolRegistry

from hagar_wikidata import (
    PLUGIN,
    WikidataClient,
    WikidataToolProvider,
)
from hagar_wikidata.client import WikidataError


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event, **fields):
        self.events.append((event, fields))


class FakeResponse:
    def __init__(
        self,
        payload=None,
        status: int = 200,
        raw: bytes | None = None,
    ):
        self.status_code = status
        self.headers = {}
        self.content = (
            raw
            if raw is not None
            else json.dumps(payload).encode("utf-8")
        )


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(
        self,
        url,
        params=None,
        timeout=None,
        headers=None,
        allow_redirects=False,
    ):
        params = dict(params or {})
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
                "headers": dict(headers or {}),
                "allow_redirects": allow_redirects,
            }
        )
        result = self.handler(url, params)
        if isinstance(result, FakeResponse):
            return result
        return FakeResponse(result)


def test_plugin_registers_network_tools():
    registry = ToolRegistry()

    PLUGIN.register(registry, PluginContext())

    assert registry.tool_names() == [
        "wikidata.article",
        "wikidata.entity",
        "wikidata.query",
        "wikidata.search",
    ]

    for name in registry.tool_names():
        tool = registry.get(name)
        assert tool.capabilities == Capability.NETWORK
        assert tool.origin == "plugin.wikidata"
        assert tool.category == "wikidata"
        assert tool.enabled is True


def test_entry_point_discovery(monkeypatch):
    class Entry:
        name = "wikidata"

        def load(self):
            return PLUGIN

    monkeypatch.setattr(
        plugins,
        "_entry_points",
        lambda group: [Entry()]
        if group == plugins.TOOL_GROUP
        else [],
    )

    registry = ToolRegistry()
    audit = Audit()

    failures = load_tool_plugins(
        [],
        registry,
        PluginContext(),
        audit=audit,
    )

    assert failures == []
    assert "wikidata.search" in registry.tool_names()
    assert audit.events[0][0] == "plugin.loaded"
    assert audit.events[0][1]["plugin"] == "wikidata"


def test_pyproject_declares_entry_point():
    root = Path(__file__).resolve().parents[1]
    path = root / "plugins" / "wikidata" / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    assert (
        data["project"]["entry-points"]["hagar.tools"][
            "wikidata"
        ]
        == "hagar_wikidata:PLUGIN"
    )


def test_search_returns_compact_results():
    def handler(url, params):
        assert url == "https://www.wikidata.org/w/api.php"
        assert params["action"] == "wbsearchentities"
        assert params["language"] == "it"
        assert params["uselang"] == "it"
        assert params["type"] == "item"
        assert params["limit"] == 5
        return {
            "search": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "scrittore britannico",
                    "aliases": ["Douglas Noël Adams"],
                    "url": (
                        "//www.wikidata.org/wiki/Q42"
                    ),
                    "concepturi": (
                        "http://www.wikidata.org/entity/Q42"
                    ),
                }
            ],
            "search-continue": 5,
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.search(
        "Douglas Adams",
        language="it",
        limit=5,
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["has_more"] is True

    item = result["results"][0]
    assert item["id"] == "Q42"
    assert item["label"] == "Douglas Adams"
    assert item["description"] == "scrittore britannico"
    assert item["aliases"] == ["Douglas Noël Adams"]
    assert item["url"] == (
        "https://www.wikidata.org/wiki/Q42"
    )


def test_search_rejects_invalid_input():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    with pytest.raises(ValueError):
        client.search("x", language="../evil")

    with pytest.raises(ValueError):
        client.search("   ")

    with pytest.raises(ValueError):
        client.search("x", entity_type="lexeme")

    with pytest.raises(ValueError):
        client.search("x", limit="many")


def test_api_error_is_raised():
    def handler(url, params):
        return {
            "error": {
                "code": "badsearch",
                "info": "invalid search",
            }
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    with pytest.raises(
        WikidataError,
        match="invalid search",
    ):
        client.search("x")


def entity_payload():
    return {
        "entities": {
            "Q42": {
                "id": "Q42",
                "type": "item",
                "labels": {
                    "it": {
                        "language": "it",
                        "value": "Douglas Adams",
                    },
                    "en": {
                        "language": "en",
                        "value": "Douglas Adams",
                    },
                },
                "descriptions": {
                    "it": {
                        "language": "it",
                        "value": "scrittore britannico",
                    }
                },
                "aliases": {
                    "it": [
                        {"value": "Douglas Noël Adams"}
                    ]
                },
                "claims": {
                    "P31": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datatype": "wikibase-item",
                                "datavalue": {
                                    "type": (
                                        "wikibase-entityid"
                                    ),
                                    "value": {"id": "Q5"},
                                },
                            }
                        }
                    ],
                    "P569": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datatype": "time",
                                "datavalue": {
                                    "type": "time",
                                    "value": {
                                        "time": (
                                            "+1952-03-11T00:00:00Z"
                                        ),
                                        "precision": 11,
                                        "calendarmodel": (
                                            "http://www.wikidata.org"
                                            "/entity/Q1985727"
                                        ),
                                    },
                                },
                            }
                        }
                    ],
                },
                "sitelinks": {
                    "itwiki": {
                        "site": "itwiki",
                        "title": "Douglas Adams",
                    },
                    "enwiki": {
                        "site": "enwiki",
                        "title": "Douglas Adams",
                    },
                },
                "modified": "2026-01-01T00:00:00Z",
            }
        }
    }


def labels_payload():
    return {
        "entities": {
            "P31": {
                "labels": {
                    "it": {"value": "istanza di"}
                }
            },
            "P569": {
                "labels": {
                    "it": {"value": "data di nascita"}
                }
            },
            "Q5": {
                "labels": {
                    "it": {"value": "essere umano"}
                }
            },
        }
    }


def test_entity_returns_compact_claims_and_labels():
    def handler(url, params):
        if params.get("props") == "labels":
            return labels_payload()
        return entity_payload()

    session = FakeSession(handler)
    client = WikidataClient(session=session)

    result = client.entity("q42", language="it")

    assert result["success"] is True
    entity = result["entities"][0]

    assert entity["id"] == "Q42"
    assert entity["label"] == "Douglas Adams"
    assert entity["description"] == "scrittore britannico"
    assert entity["aliases"] == ["Douglas Noël Adams"]
    assert entity["wikipedia"]["it"]["url"] == (
        "https://it.wikipedia.org/wiki/Douglas_Adams"
    )
    assert entity["claim_count"] == 2
    assert entity["claims_returned"] == 2
    assert entity["claims_truncated"] is False

    claims = {
        claim["property"]: claim
        for claim in entity["claims"]
    }

    assert claims["P31"]["property_label"] == "istanza di"
    assert claims["P31"]["values"][0] == {
        "id": "Q5",
        "label": "essere umano",
    }

    assert claims["P569"]["property_label"] == (
        "data di nascita"
    )
    assert claims["P569"]["values"][0]["time"] == (
        "+1952-03-11T00:00:00Z"
    )

    assert len(session.calls) == 2
    main_call, label_call = session.calls
    assert main_call["params"]["sitefilter"] == (
        "itwiki|enwiki"
    )
    assert "claims" in main_call["params"]["props"]
    assert label_call["params"]["props"] == "labels"
    assert label_call["params"]["ids"] == (
        "P31|P569|Q5"
    )


def test_entity_can_skip_claims_and_labels():
    def handler(url, params):
        if params.get("props") == "labels":
            pytest.fail("labels must not be fetched")
        return entity_payload()

    session = FakeSession(handler)
    client = WikidataClient(session=session)

    result = client.entity(
        "Q42",
        include_claims=False,
    )

    entity = result["entities"][0]

    assert entity["claims"] == []
    assert entity["claims_returned"] == 0
    assert entity["claim_count"] == 2
    assert len(session.calls) == 1


def test_entity_uses_mul_label_when_language_is_absent():
    payload = entity_payload()
    payload["entities"]["Q42"]["labels"] = {
        "mul": {
            "language": "mul",
            "value": "Douglas Adams",
        }
    }

    def handler(url, params):
        if params.get("props") == "labels":
            pytest.fail("labels must not be fetched")
        return payload

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.entity(
        "Q42",
        include_claims=False,
    )

    assert result["entities"][0]["label"] == (
        "Douglas Adams"
    )


def test_entity_prioritizes_core_claims_over_external_ids():
    payload = {
        "entities": {
            "Q42": {
                "id": "Q42",
                "type": "item",
                "labels": {
                    "mul": {"value": "Douglas Adams"}
                },
                "claims": {
                    "P1005": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datatype": "external-id",
                                "datavalue": {
                                    "value": "68537"
                                },
                            }
                        }
                    ],
                    "P31": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "datatype": "wikibase-item",
                                "datavalue": {
                                    "value": {"id": "Q5"}
                                },
                            }
                        }
                    ],
                },
                "sitelinks": {},
            }
        }
    }

    def handler(url, params):
        return payload

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.entity(
        "Q42",
        max_claims=1,
        resolve_labels=False,
    )

    entity = result["entities"][0]

    assert entity["claims"][0]["property"] == "P31"
    assert entity["claims_returned"] == 1
    assert entity["claims_truncated"] is True


def test_entity_truncates_claims():
    def handler(url, params):
        if params.get("props") == "labels":
            return labels_payload()
        return entity_payload()

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.entity(
        "Q42",
        max_claims=1,
        resolve_labels=False,
    )

    entity = result["entities"][0]

    assert entity["claims_returned"] == 1
    assert entity["claims_truncated"] is True
    assert entity["claims_omitted_properties"] == 1
    assert len(entity["claims"]) == 1


def test_entity_rejects_invalid_ids():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    with pytest.raises(ValueError):
        client.entity("Q42; DROP TABLE")

    with pytest.raises(ValueError):
        client.entity(" ")


def test_article_by_title():
    def handler(url, params):
        assert url == (
            "https://it.wikipedia.org/w/api.php"
        )
        assert params["titles"] == "Douglas Adams"
        assert params["exintro"] == 1
        assert params["explaintext"] == 1
        return {
            "query": {
                "pages": [
                    {
                        "pageid": 7,
                        "title": "Douglas Adams",
                        "extract": "A" * 300,
                        "fullurl": (
                            "https://it.wikipedia.org"
                            "/wiki/Douglas_Adams"
                        ),
                        "thumbnail": {
                            "source": (
                                "https://upload.wikimedia.org"
                                "/thumb.jpg"
                            )
                        },
                    }
                ]
            }
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.article(
        title="Douglas Adams",
        language="it",
        intro_only=True,
        max_chars=200,
    )

    assert result["success"] is True
    assert result["title"] == "Douglas Adams"
    assert result["pageid"] == 7
    assert result["intro_only"] is True
    assert result["total_chars"] == 300
    assert result["returned_chars"] == 200
    assert result["truncated"] is True
    assert result["extract"] == "A" * 200
    assert "entity_id" not in result


def test_article_by_entity_resolves_sitelink():
    def handler(url, params):
        if params.get("action") == "wbgetentities":
            assert params["ids"] == "Q42"
            assert params["sitefilter"] == "itwiki|enwiki"
            return {
                "entities": {
                    "Q42": {
                        "sitelinks": {
                            "itwiki": {
                                "title": "Douglas Adams"
                            },
                            "enwiki": {
                                "title": "Douglas Adams"
                            },
                        }
                    }
                }
            }
        assert url == (
            "https://it.wikipedia.org/w/api.php"
        )
        assert "exintro" not in params
        return {
            "query": {
                "pages": [
                    {
                        "pageid": 7,
                        "title": "Douglas Adams",
                        "extract": "Testo",
                        "fullurl": (
                            "https://it.wikipedia.org"
                            "/wiki/Douglas_Adams"
                        ),
                    }
                ]
            }
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.article(
        entity_id="q42",
        language="it",
    )

    assert result["entity_id"] == "Q42"
    assert result["extract"] == "Testo"
    assert set(
        result["available_sitelinks"]
    ) == {"it", "en"}


def test_article_reports_all_available_sitelinks():
    def handler(url, params):
        if "sitefilter" in params:
            return {
                "entities": {
                    "Q42": {
                        "sitelinks": {
                            "enwiki": {
                                "title": "Douglas Adams"
                            }
                        }
                    }
                }
            }
        return {
            "entities": {
                "Q42": {
                    "sitelinks": {
                        "dewiki": {
                            "title": "Douglas Adams"
                        },
                        "itwiki": {
                            "title": "Douglas Adams"
                        },
                    }
                }
            }
        }

    session = FakeSession(handler)
    client = WikidataClient(session=session)

    with pytest.raises(
        ValueError,
        match="available: de, it",
    ):
        client.article(
            entity_id="Q42",
            language="fr",
        )

    assert len(session.calls) == 2


def test_article_rejects_mul_language():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    with pytest.raises(
        ValueError,
        match="not a Wikipedia edition",
    ):
        client.article(
            title="Douglas Adams",
            language="mul",
        )


def test_article_requires_exactly_one_source():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    with pytest.raises(ValueError):
        client.article()

    with pytest.raises(ValueError):
        client.article(
            entity_id="Q42",
            title="Douglas Adams",
        )


def test_query_returns_rows_and_truncates():
    seen = {}

    def handler(url, params):
        seen["url"] = url
        seen["params"] = dict(params)
        return {
            "head": {
                "vars": ["item", "itemLabel"]
            },
            "results": {
                "bindings": [
                    {
                        "item": {
                            "type": "uri",
                            "value": (
                                "http://www.wikidata.org"
                                "/entity/Q42"
                            ),
                        },
                        "itemLabel": {
                            "type": "literal",
                            "value": "Douglas Adams",
                        },
                    },
                    {
                        "item": {
                            "type": "uri",
                            "value": (
                                "http://www.wikidata.org"
                                "/entity/Q1"
                            ),
                        },
                        "itemLabel": {
                            "type": "literal",
                            "value": "Universo",
                        },
                    },
                    {
                        "item": {
                            "type": "uri",
                            "value": (
                                "http://www.wikidata.org"
                                "/entity/Q2"
                            ),
                        },
                        "itemLabel": {
                            "type": "literal",
                            "value": "Terra",
                        },
                    },
                ]
            },
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.query(
        "PREFIX wd: <http://www.wikidata.org/entity/>\n"
        "SELECT ?item ?itemLabel WHERE { "
        "?item wdt:P31 wd:Q5 }",
        max_results=2,
    )

    assert seen["url"] == (
        "https://query.wikidata.org/sparql"
    )
    assert seen["params"]["format"] == "json"
    assert result["vars"] == ["item", "itemLabel"]
    assert result["row_count"] == 2
    assert result["total_rows"] == 3
    assert result["truncated"] is True
    assert result["rows"][0]["itemLabel"] == (
        "Douglas Adams"
    )


def test_query_allows_wikibase_label_service():
    def handler(url, params):
        return {
            "head": {"vars": []},
            "results": {"bindings": []},
        }

    client = WikidataClient(
        session=FakeSession(handler)
    )

    result = client.query(
        "SELECT ?item ?itemLabel WHERE { "
        "?item wdt:P31 wd:Q5 . "
        "SERVICE wikibase:label { "
        'bd:serviceParam wikibase:language "it". '
        "} }"
    )

    assert result["success"] is True
    assert result["row_count"] == 0


def test_query_rejects_write_and_federation():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    with pytest.raises(ValueError):
        client.query("ASK { ?s ?p ?o }")

    with pytest.raises(ValueError):
        client.query(
            "DELETE WHERE { ?s ?p ?o }"
        )

    with pytest.raises(ValueError):
        client.query(
            "SELECT * WHERE { "
            "SERVICE <https://example.com/sparql> "
            "{ ?s ?p ?o } }"
        )

    with pytest.raises(ValueError):
        client.query(
            "SELECT * WHERE { "
            "SERVICE ?service "
            "{ ?s ?p ?o } }"
        )

    with pytest.raises(ValueError):
        client.query(
            "SELECT * FROM <https://example.com/x> "
            "WHERE { ?s ?p ?o }"
        )


def test_http_error_is_reported():
    def handler(url, params):
        return FakeResponse(
            {"error": {"info": "server down"}},
            status=500,
        )

    client = WikidataClient(
        session=FakeSession(handler)
    )

    provider = WikidataToolProvider(client)
    payload = json.loads(provider.search("x"))

    assert payload["success"] is False
    assert "server down" in payload["error"]


def test_redirect_is_rejected():
    def handler(url, params):
        return FakeResponse({}, status=302)

    client = WikidataClient(
        session=FakeSession(handler)
    )

    with pytest.raises(
        WikidataError,
        match="redirect",
    ):
        client.search("x")


def test_oversized_response_is_rejected():
    def handler(url, params):
        return FakeResponse(
            raw=b'{"search": "' + b"A" * 100 + b'"}'
        )

    client = WikidataClient(
        session=FakeSession(handler),
        max_bytes=10,
    )

    with pytest.raises(
        WikidataError,
        match="larger than",
    ):
        client.search("x")


def test_invalid_json_is_reported():
    def handler(url, params):
        return FakeResponse(raw=b"not json")

    client = WikidataClient(
        session=FakeSession(handler)
    )

    with pytest.raises(
        WikidataError,
        match="invalid JSON",
    ):
        client.search("x")


def test_provider_returns_error_json():
    client = WikidataClient(
        session=FakeSession(
            lambda url, params: pytest.fail(
                "no request expected"
            )
        )
    )

    provider = WikidataToolProvider(client)

    payload = json.loads(provider.search(""))

    assert payload["success"] is False
    assert "empty" in payload["error"]


def test_tool_plugin_metadata():
    assert isinstance(PLUGIN, ToolPlugin)
    assert PLUGIN.name == "wikidata"
    assert PLUGIN.version == "1.0.0"
    assert PLUGIN.builtin is False
