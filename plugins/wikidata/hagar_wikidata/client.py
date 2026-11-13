"""Client HTTP per Wikidata, Wikipedia e Wikidata Query Service.

Il client parla soltanto con gli endpoint Wikimedia: il modello non può
fornire URL arbitrari, quindi la superficie SSRF resta chiusa. Le
risposte hanno un limite di dimensione e ogni richiesta ha un timeout.
"""

from __future__ import annotations

import json
import os
import re

from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import requests


WIKIDATA_API = "https://www.wikidata.org/w/api.php"

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

WIKIPEDIA_API = (
    "https://{language}.wikipedia.org/w/api.php"
)

DEFAULT_LANGUAGE = "it"

MAX_BYTES = 8_000_000

MAX_LABELS = 200

USER_AGENT = (
    "Hagar-Wikidata/1.0 "
    "(+https://github.com/kormoran/Hagar)"
)

LANGUAGE_PATTERN = re.compile(
    r"^[a-z][a-z0-9-]{0,15}$"
)

ENTITY_ID_PATTERN = re.compile(
    r"^[QPL]\d{1,12}$"
)

SERVICE_PATTERN = re.compile(
    r"\bSERVICE\b",
    re.IGNORECASE,
)

PROLOGUE_PATTERN = re.compile(
    r"(?is)^(?:"
    r"PREFIX\s+[A-Za-z][\w.-]*:\s*<[^>]*>"
    r"|BASE\s*<[^>]*>"
    r")\s*"
)

SELECT_PATTERN = re.compile(
    r"^SELECT\b",
    re.IGNORECASE,
)

#
# Proprietà che un modello cerca di solito per prime. Le claim sono
# ordinate con questa priorità, poi le altre claim non-identificativo,
# infine gli identificativi esterni (spesso centinaia e poco utili).
#

CLAIM_PRIORITY = {
    property_id: index
    for index, property_id in enumerate(
        [
            "P31",
            "P279",
            "P361",
            "P527",
            "P17",
            "P131",
            "P625",
            "P18",
            "P19",
            "P20",
            "P569",
            "P570",
            "P106",
            "P21",
            "P735",
            "P734",
            "P1477",
            "P108",
            "P69",
            "P26",
            "P40",
            "P22",
            "P25",
            "P3373",
            "P39",
            "P102",
            "P27",
            "P103",
            "P1412",
            "P136",
            "P495",
            "P175",
            "P50",
            "P57",
            "P86",
            "P162",
            "P364",
            "P577",
            "P580",
            "P582",
            "P585",
            "P276",
            "P159",
            "P112",
            "P571",
            "P576",
            "P856",
            "P1448",
            "P1705",
            "P1813",
        ]
    )
}


def _is_external_id(
    statements: Any,
) -> bool:

    if not isinstance(statements, list):
        return False

    for statement in statements:

        if not isinstance(statement, dict):
            continue

        snak = statement.get("mainsnak")

        if isinstance(snak, dict):
            return (
                snak.get("datatype")
                == "external-id"
            )

    return False


def _claim_order(
    property_id: str,
    statements: Any,
) -> tuple[int, int, str]:

    priority = CLAIM_PRIORITY.get(property_id)

    if priority is not None:
        return (0, priority, property_id)

    if _is_external_id(statements):
        return (2, 0, property_id)

    return (1, 0, property_id)


class WikidataError(RuntimeError):
    """Errore di rete o di risposta di un endpoint Wikimedia."""


def _env_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:

    raw = os.environ.get(name)

    if raw is None:
        return default

    try:
        value = float(raw)
    except ValueError:
        return default

    if not minimum <= value <= maximum:
        return default

    return value


def default_language() -> str:
    """Lingua predefinita, sovrascrivibile da ambiente."""

    raw = os.environ.get(
        "HAGAR_WIKIDATA_LANGUAGE",
        DEFAULT_LANGUAGE,
    )

    try:
        return validate_language(raw)
    except ValueError:
        return DEFAULT_LANGUAGE


def validate_language(
    value: Any,
) -> str:
    """Valida un codice di lingua e lo normalizza."""

    if not isinstance(value, str):
        raise ValueError(
            "language must be a string"
        )

    language = value.strip().lower()

    if not LANGUAGE_PATTERN.fullmatch(language):
        raise ValueError(
            f"invalid language code: {value!r}"
        )

    return language


def _bounded_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:

    if value is None:
        return default

    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be an integer"
        )

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be an integer"
        ) from exc

    return max(minimum, min(number, maximum))


def _as_bool(
    value: Any,
    default: bool,
) -> bool:

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):

        normalized = value.strip().lower()

        if normalized in {
            "1",
            "true",
            "yes",
            "y",
            "si",
            "sì",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "n",
        }:
            return False

    raise ValueError("value must be a boolean")


def _pick_language(
    mapping: Any,
    language: str,
) -> str:
    """Etichetta nella lingua richiesta, con fallback inglese."""

    if not isinstance(mapping, dict):
        return ""

    for code in (language, "en", "mul"):

        entry = mapping.get(code)

        if isinstance(entry, dict):

            value = entry.get("value")

            if isinstance(value, str) and value:
                return value

    for code in sorted(mapping):

        entry = mapping[code]

        if isinstance(entry, dict):

            value = entry.get("value")

            if isinstance(value, str) and value:
                return value

    return ""


def _pick_aliases(
    mapping: Any,
    language: str,
) -> list[str]:

    if not isinstance(mapping, dict):
        return []

    entries = mapping.get(language)

    if not entries:
        entries = mapping.get("en")

    if not entries:
        entries = mapping.get("mul")

    if not entries:

        for code in sorted(mapping):

            if mapping.get(code):
                entries = mapping[code]
                break

    aliases = []

    for entry in entries or []:

        if not isinstance(entry, dict):
            continue

        value = entry.get("value")

        if isinstance(value, str) and value:
            aliases.append(value)

    return aliases[:20]


def _normalize_url(
    value: Any,
) -> str | None:

    if not isinstance(value, str) or not value:
        return None

    if value.startswith("//"):
        return "https:" + value

    return value


def _wikipedia_url(
    language: str,
    title: str | None,
) -> str | None:

    if not title:
        return None

    slug = quote(
        title.replace(" ", "_"),
        safe="",
    )

    return (
        f"https://{language}.wikipedia.org"
        f"/wiki/{slug}"
    )


def _compact_unit(
    unit: Any,
) -> Any:

    if not isinstance(unit, str):
        return unit

    if unit == "1":
        return unit

    marker = "/entity/"

    if marker in unit:
        return unit.rsplit(marker, 1)[-1]

    return unit


def _snak_value(
    snak: Any,
) -> Any:
    """Riduce un mainsnak a un valore JSON compatto."""

    if not isinstance(snak, dict):
        return None

    if snak.get("snaktype") != "value":
        return {
            "snaktype": snak.get(
                "snaktype",
                "novalue",
            )
        }

    datavalue = snak.get("datavalue")

    if not isinstance(datavalue, dict):
        return None

    value = datavalue.get("value")

    datatype = snak.get("datatype")

    if datatype in {
        "wikibase-item",
        "wikibase-property",
        "wikibase-lexeme",
        "wikibase-form",
        "wikibase-sense",
    }:

        if isinstance(value, dict):

            identifier = value.get("id")

            if isinstance(identifier, str):
                return {"id": identifier}

        return value

    if datatype == "monolingualtext":

        if isinstance(value, dict):
            return {
                "text": value.get("text"),
                "language": value.get("language"),
            }

        return value

    if datatype == "time":

        if isinstance(value, dict):
            return {
                "time": value.get("time"),
                "precision": value.get("precision"),
                "calendarmodel":
                    value.get("calendarmodel"),
            }

        return value

    if datatype == "quantity":

        if isinstance(value, dict):
            return {
                "amount": value.get("amount"),
                "unit": _compact_unit(
                    value.get("unit")
                ),
                "lower": value.get(
                    "lowerBound"
                ),
                "upper": value.get(
                    "upperBound"
                ),
            }

        return value

    if datatype == "globecoordinate":

        if isinstance(value, dict):
            return {
                "latitude": value.get("latitude"),
                "longitude": value.get("longitude"),
                "precision": value.get("precision"),
                "globe": _compact_unit(
                    value.get("globe")
                ),
            }

        return value

    return value


def _strip_comments_and_space(
    text: str,
) -> str:

    while True:

        text = text.lstrip()

        if not text.startswith("#"):
            return text

        newline = text.find("\n")

        if newline < 0:
            return ""

        text = text[newline + 1:]


def _is_select_query(
    text: str,
) -> bool:
    """Solo SELECT, con prologo PREFIX/BASE e commenti."""

    remaining = _strip_comments_and_space(
        text
    )

    while True:

        match = PROLOGUE_PATTERN.match(
            remaining
        )

        if match is None:
            break

        remaining = _strip_comments_and_space(
            remaining[match.end():]
        )

    return bool(
        SELECT_PATTERN.match(remaining)
    )


def _extract_error(
    content: bytes,
) -> str:

    try:
        data = json.loads(
            content.decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError):
        text = content.decode(
            "utf-8",
            errors="replace",
        )
        return " ".join(text.split())[:300]

    if isinstance(data, dict):

        error = data.get("error")

        if isinstance(error, dict):
            return str(
                error.get("info")
                or error.get("code")
                or error
            )

        if isinstance(error, str):
            return error

        for key in ("message", "exception"):

            if data.get(key):
                return str(data[key])

    return "request failed"


class WikidataClient:
    """Chiamate sincrone e in sola lettura ai servizi Wikimedia."""

    def __init__(
        self,
        session: Any = None,
        timeout: float | None = None,
        query_timeout: float | None = None,
        user_agent: str | None = None,
        max_bytes: int = MAX_BYTES,
    ) -> None:

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

        self.timeout = (
            timeout
            if timeout is not None
            else _env_float(
                "HAGAR_WIKIDATA_TIMEOUT",
                15.0,
                2.0,
                120.0,
            )
        )

        self.query_timeout = (
            query_timeout
            if query_timeout is not None
            else _env_float(
                "HAGAR_WIKIDATA_QUERY_TIMEOUT",
                60.0,
                2.0,
                180.0,
            )
        )

        self.user_agent = (
            user_agent
            if user_agent is not None
            else os.environ.get(
                "HAGAR_WIKIDATA_USER_AGENT",
                USER_AGENT,
            )
        )

        self.max_bytes = int(max_bytes)

    # ==========================================================
    # HTTP
    # ==========================================================

    @staticmethod
    def _validate_url(
        url: str,
    ) -> None:

        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise WikidataError(
                "only https URLs are allowed"
            )

        host = (parsed.hostname or "").lower()

        if host in {
            "www.wikidata.org",
            "query.wikidata.org",
        }:
            return

        suffix = ".wikipedia.org"

        if host.endswith(suffix):

            language = host[:-len(suffix)]

            if (
                language != "www"
                and LANGUAGE_PATTERN.fullmatch(
                    language
                )
            ):
                return

        raise WikidataError(
            f"refusing non-Wikimedia URL: {host}"
        )

    def _get_json(
        self,
        url: str,
        params: dict[str, Any],
        timeout: float | None = None,
        accept: str = "application/json",
    ) -> Any:

        self._validate_url(url)

        try:

            response = self.session.get(
                url,
                params=params,
                timeout=(
                    5,
                    timeout
                    if timeout is not None
                    else self.timeout,
                ),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": accept,
                },
                allow_redirects=False,
            )

        except Exception as exc:  # noqa: BLE001

            raise WikidataError(
                f"network error: {exc}"
            ) from exc

        status = int(
            getattr(response, "status_code", 0)
        )

        headers = (
            getattr(response, "headers", None)
            or {}
        )

        declared = headers.get("Content-Length")

        if declared:

            try:
                declared_bytes = int(declared)
            except ValueError:
                declared_bytes = 0

            if declared_bytes > self.max_bytes:

                raise WikidataError(
                    "response is larger than "
                    f"{self.max_bytes} bytes"
                )

        content = getattr(
            response,
            "content",
            b"",
        )

        if isinstance(content, str):
            content = content.encode("utf-8")

        content = content or b""

        if len(content) > self.max_bytes:

            raise WikidataError(
                "response is larger than "
                f"{self.max_bytes} bytes"
            )

        if status in {301, 302, 303, 307, 308}:

            raise WikidataError(
                "unexpected HTTP redirect from"
                f" {urlparse(url).hostname}"
            )

        if status == 429:

            raise WikidataError(
                "rate limited by Wikimedia; "
                "retry later"
            )

        if status >= 400:

            raise WikidataError(
                f"HTTP {status}: "
                f"{_extract_error(content)}"
            )

        try:

            data = json.loads(
                content.decode("utf-8")
            )

        except (UnicodeDecodeError, ValueError) as exc:

            raise WikidataError(
                "invalid JSON response"
            ) from exc

        if isinstance(data, dict) and data.get("error"):

            raise WikidataError(
                _extract_error(content)
            )

        return data

    # ==========================================================
    # Ricerca
    # ==========================================================

    def search(
        self,
        query: str,
        language: str | None = None,
        limit: int = 10,
        entity_type: str = "item",
    ) -> dict[str, Any]:

        if not isinstance(query, str):
            raise ValueError(
                "query must be a string"
            )

        query = query.strip()

        if not query:
            raise ValueError(
                "query must not be empty"
            )

        if len(query) > 300:
            raise ValueError(
                "query is too long (max 300 characters)"
            )

        language = validate_language(
            language
            if language is not None
            else default_language()
        )

        if entity_type not in {
            "item",
            "property",
        }:
            raise ValueError(
                "entity_type must be 'item' or "
                "'property'"
            )

        limit = _bounded_int(
            limit,
            10,
            1,
            50,
            "limit",
        )

        data = self._get_json(
            WIKIDATA_API,
            {
                "action": "wbsearchentities",
                "search": query,
                "language": language,
                "uselang": language,
                "type": entity_type,
                "limit": limit,
                "format": "json",
            },
        )

        results = []

        for item in data.get("search") or []:

            if not isinstance(item, dict):
                continue

            identifier = item.get("id")

            results.append(
                {
                    "id": identifier,
                    "label": (
                        item.get("label")
                        or item.get("title")
                        or ""
                    ),
                    "description": (
                        item.get("description")
                        or ""
                    ),
                    "aliases": (
                        item.get("aliases")
                        or []
                    ),
                    "url": (
                        _normalize_url(
                            item.get("url")
                        )
                        or (
                            "https://www.wikidata.org"
                            f"/wiki/{identifier}"
                        )
                    ),
                    "concept_uri": item.get(
                        "concepturi"
                    ),
                }
            )

        return {
            "success": True,
            "query": query,
            "language": language,
            "type": entity_type,
            "count": len(results),
            "has_more": bool(
                data.get("search-continue")
            ),
            "results": results,
        }

    # ==========================================================
    # Entità
    # ==========================================================

    @staticmethod
    def _normalize_ids(
        ids: Any,
        maximum: int = 10,
    ) -> list[str]:

        if isinstance(ids, str):

            parts = re.split(
                r"[\s,|]+",
                ids.strip(),
            )

        elif isinstance(ids, list):

            parts = [str(item) for item in ids]

        else:

            raise ValueError(
                "ids must be a string of Wikidata "
                "IDs separated by commas"
            )

        normalized = []

        for part in parts:

            if not part:
                continue

            identifier = part.strip().upper()

            if not ENTITY_ID_PATTERN.fullmatch(
                identifier
            ):

                raise ValueError(
                    "invalid Wikidata entity id: "
                    f"{part!r}"
                )

            if identifier not in normalized:
                normalized.append(identifier)

        if not normalized:

            raise ValueError(
                "ids must contain at least one "
                "entity id"
            )

        if len(normalized) > maximum:

            raise ValueError(
                f"at most {maximum} entity ids "
                "are allowed"
            )

        return normalized

    def _fetch_labels(
        self,
        ids: list[str],
        language: str,
    ) -> dict[str, str]:
        """Etichette per ID di entità e proprietà, a blocchi."""

        unique = sorted(
            {
                identifier
                for identifier in ids
                if (
                    isinstance(identifier, str)
                    and ENTITY_ID_PATTERN.fullmatch(
                        identifier
                    )
                )
            }
        )[:MAX_LABELS]

        labels: dict[str, str] = {}

        for start in range(
            0,
            len(unique),
            50,
        ):

            chunk = unique[start:start + 50]

            data = self._get_json(
                WIKIDATA_API,
                {
                    "action": "wbgetentities",
                    "ids": "|".join(chunk),
                    "props": "labels",
                    "languages": "|".join(
                        dict.fromkeys(
                            [language, "en", "mul"]
                        )
                    ),
                    "format": "json",
                },
            )

            entities = data.get("entities") or {}

            if not isinstance(entities, dict):
                continue

            for identifier, raw in entities.items():

                if not isinstance(raw, dict):
                    continue

                if raw.get("missing") is not None:
                    continue

                label = _pick_language(
                    raw.get("labels"),
                    language,
                )

                if label:
                    labels[identifier] = label

        return labels

    def entity(
        self,
        ids: str | list[str],
        language: str | None = None,
        include_claims: bool = True,
        max_claims: int = 50,
        resolve_labels: bool = True,
    ) -> dict[str, Any]:

        language = validate_language(
            language
            if language is not None
            else default_language()
        )

        identifiers = self._normalize_ids(ids)

        include_claims = _as_bool(
            include_claims,
            True,
        )

        resolve_labels = _as_bool(
            resolve_labels,
            True,
        )

        max_claims = _bounded_int(
            max_claims,
            50,
            1,
            300,
            "max_claims",
        )

        sites = "|".join(
            dict.fromkeys(
                [f"{language}wiki", "enwiki"]
            )
        )

        data = self._get_json(
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(identifiers),
                "props": (
                    "labels|descriptions|aliases|"
                    "claims|sitelinks|info"
                ),
                "languages": "|".join(
                    dict.fromkeys(
                        [language, "en", "mul"]
                    )
                ),
                "sitefilter": sites,
                "format": "json",
            },
        )

        entities = data.get("entities") or {}

        if not isinstance(entities, dict):

            raise WikidataError(
                "malformed wbgetentities response"
            )

        output = []

        for identifier in identifiers:

            raw = entities.get(identifier)

            if not isinstance(raw, dict):

                output.append(
                    {
                        "id": identifier,
                        "missing": True,
                    }
                )
                continue

            if raw.get("missing") is not None:

                output.append(
                    {
                        "id": identifier,
                        "missing": True,
                    }
                )
                continue

            label = _pick_language(
                raw.get("labels"),
                language,
            )

            description = _pick_language(
                raw.get("descriptions"),
                language,
            )

            aliases = _pick_aliases(
                raw.get("aliases"),
                language,
            )

            wikipedia = self._wikipedia_sitelinks(
                raw
            )

            claims_raw = raw.get("claims") or {}

            claim_count = 0
            claims = []
            emitted = 0
            truncated_claims = False
            remaining_properties = 0

            if isinstance(claims_raw, dict):

                ordered = sorted(
                    claims_raw.items(),
                    key=lambda item: _claim_order(
                        item[0],
                        item[1],
                    ),
                )

                for property_id, statements in ordered:

                    if not isinstance(
                        statements,
                        list,
                    ):
                        continue

                    claim_count += len(statements)

                    if not include_claims:
                        continue

                    if emitted >= max_claims:
                        remaining_properties += 1
                        truncated_claims = True
                        continue

                    values = []

                    for statement in statements:

                        if emitted >= max_claims:
                            truncated_claims = True
                            break

                        if not isinstance(
                            statement,
                            dict,
                        ):
                            continue

                        values.append(
                            _snak_value(
                                statement.get(
                                    "mainsnak"
                                )
                            )
                        )

                        emitted += 1

                    if values:
                        claims.append(
                            {
                                "property":
                                    property_id,
                                "property_label":
                                    None,
                                "count":
                                    len(statements),
                                "values": values,
                                "truncated": (
                                    len(values)
                                    < len(statements)
                                ),
                            }
                        )

            if (
                resolve_labels
                and include_claims
                and claims
            ):

                referenced = [
                    claim["property"]
                    for claim in claims
                ]

                for claim in claims:

                    for value in claim["values"]:

                        if (
                            isinstance(value, dict)
                            and "id" in value
                        ):
                            referenced.append(
                                value["id"]
                            )

                labels = self._fetch_labels(
                    referenced,
                    language,
                )

                for claim in claims:

                    claim["property_label"] = (
                        labels.get(
                            claim["property"]
                        )
                    )

                    for value in claim["values"]:

                        if (
                            isinstance(value, dict)
                            and "id" in value
                        ):
                            value["label"] = (
                                labels.get(
                                    value["id"]
                                )
                            )

            output.append(
                {
                    "id": identifier,
                    "type": raw.get(
                        "type",
                        "item",
                    ),
                    "label": label or identifier,
                    "description": description,
                    "aliases": aliases,
                    "url": (
                        "https://www.wikidata.org"
                        f"/wiki/{identifier}"
                    ),
                    "modified": raw.get("modified"),
                    "wikipedia": wikipedia,
                    "claim_count": claim_count,
                    "claims_returned": emitted,
                    "claims_truncated":
                        truncated_claims,
                    "claims_omitted_properties":
                        remaining_properties,
                    "claims": claims,
                }
            )

        return {
            "success": True,
            "language": language,
            "entities": output,
        }

    # ==========================================================
    # Articoli Wikipedia
    # ==========================================================

    @staticmethod
    def _wikipedia_sitelinks(
        raw: dict[str, Any],
    ) -> dict[str, Any]:

        available = {}

        for site, body in (
            raw.get("sitelinks") or {}
        ).items():

            if not site.endswith("wiki"):
                continue

            site_language = site[:-4]

            if not LANGUAGE_PATTERN.fullmatch(
                site_language
            ):
                continue

            if not isinstance(body, dict):
                continue

            title = body.get("title")

            available[site_language] = {
                "title": title,
                "url": _wikipedia_url(
                    site_language,
                    title,
                ),
            }

        return available

    def _entity_sitelink(
        self,
        entity_id: str,
        language: str,
    ) -> dict[str, Any]:

        request = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "sitelinks",
            "format": "json",
        }

        data = self._get_json(
            WIKIDATA_API,
            {
                **request,
                "sitefilter": "|".join(
                    dict.fromkeys(
                        [
                            f"{language}wiki",
                            "enwiki",
                        ]
                    )
                ),
            },
        )

        raw = (
            data.get("entities") or {}
        ).get(entity_id)

        if not isinstance(raw, dict):

            raise WikidataError(
                f"unknown Wikidata entity: "
                f"{entity_id}"
            )

        if raw.get("missing") is not None:

            raise ValueError(
                f"unknown Wikidata entity: "
                f"{entity_id}"
            )

        available = self._wikipedia_sitelinks(
            raw
        )

        if language not in available:

            #
            # Il primo filtro copre solo la lingua richiesta e
            # l'inglese. Se manca il sitelink, una seconda richiesta
            # senza filtro permette di elencare tutte le lingue
            # disponibili nell'errore.
            #

            data = self._get_json(
                WIKIDATA_API,
                request,
            )

            raw = (
                data.get("entities") or {}
            ).get(entity_id)

            if not isinstance(raw, dict):

                raise WikidataError(
                    f"unknown Wikidata entity: "
                    f"{entity_id}"
                )

            available = self._wikipedia_sitelinks(
                raw
            )

        chosen = available.get(language)

        return {
            "title": (
                chosen.get("title")
                if chosen
                else None
            ),
            "available": available,
        }

    def article(
        self,
        entity_id: str | None = None,
        title: str | None = None,
        language: str | None = None,
        intro_only: bool = False,
        max_chars: int = 4000,
    ) -> dict[str, Any]:

        language = validate_language(
            language
            if language is not None
            else default_language()
        )

        if language == "mul":

            raise ValueError(
                "'mul' is a Wikidata label language, "
                "not a Wikipedia edition"
            )

        intro_only = _as_bool(
            intro_only,
            False,
        )

        max_chars = _bounded_int(
            max_chars,
            4000,
            200,
            20000,
            "max_chars",
        )

        entity_id = (
            entity_id.strip().upper()
            if isinstance(entity_id, str)
            and entity_id.strip()
            else None
        )

        if entity_id is not None:

            if not ENTITY_ID_PATTERN.fullmatch(
                entity_id
            ):

                raise ValueError(
                    "invalid Wikidata entity id: "
                    f"{entity_id!r}"
                )

        title = (
            title.strip()
            if isinstance(title, str)
            and title.strip()
            else None
        )

        if title is not None:

            if "\n" in title or "\r" in title:

                raise ValueError(
                    "title must be a single line"
                )

            if len(title) > 300:

                raise ValueError(
                    "title is too long "
                    "(max 300 characters)"
                )

        if (entity_id is None) == (title is None):

            raise ValueError(
                "provide exactly one of entity_id "
                "or title"
            )

        available: dict[str, Any] = {}

        if entity_id is not None:

            site = self._entity_sitelink(
                entity_id,
                language,
            )

            available = site["available"]
            title = site["title"]

            if title is None:

                languages = ", ".join(
                    sorted(available)
                ) or "none"

                raise ValueError(
                    f"{entity_id} has no Wikipedia "
                    f"sitelink in '{language}'; "
                    f"available: {languages}"
                )

        params = {
            "action": "query",
            "prop": "extracts|info|pageimages",
            "inprop": "url",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "pithumbsize": 320,
            "format": "json",
            "formatversion": 2,
        }

        if intro_only:
            params["exintro"] = 1

        data = self._get_json(
            WIKIPEDIA_API.format(
                language=language
            ),
            params,
        )

        pages = (
            (data.get("query") or {}).get(
                "pages"
            )
            or []
        )

        if not isinstance(pages, list) or not pages:

            raise WikidataError(
                "Wikipedia returned no page"
            )

        page = pages[0]

        if not isinstance(page, dict):

            raise WikidataError(
                "malformed Wikipedia response"
            )

        if page.get("missing"):

            raise ValueError(
                f"Wikipedia page not found: "
                f"{title}"
            )

        extract = page.get("extract") or ""

        if not isinstance(extract, str):
            extract = str(extract)

        total_chars = len(extract)

        text = extract[:max_chars]

        result = {
            "success": True,
            "language": language,
            "title": page.get("title") or title,
            "pageid": page.get("pageid"),
            "url": page.get("fullurl"),
            "thumbnail": (
                (page.get("thumbnail") or {}).get(
                    "source"
                )
            ),
            "intro_only": intro_only,
            "total_chars": total_chars,
            "returned_chars": len(text),
            "truncated": (
                total_chars > len(text)
            ),
            "extract": text,
        }

        if entity_id is not None:
            result["entity_id"] = entity_id
            result["available_sitelinks"] = (
                available
            )

        return result

    # ==========================================================
    # SPARQL
    # ==========================================================

    def query(
        self,
        query: str,
        max_results: int = 100,
    ) -> dict[str, Any]:

        if not isinstance(query, str):

            raise ValueError(
                "query must be a string"
            )

        sparql = query.strip()

        if not sparql:
            raise ValueError(
                "query must not be empty"
            )

        if len(sparql) > 8000:

            raise ValueError(
                "query is too long "
                "(max 8000 characters)"
            )

        if not _is_select_query(sparql):

            raise ValueError(
                "only read-only SELECT queries "
                "are allowed"
            )

        for match in SERVICE_PATTERN.finditer(
            sparql
        ):

            rest = sparql[match.end():].lstrip()

            rest = re.sub(
                r"(?is)^SILENT\s+",
                "",
                rest,
            )

            if not re.match(
                r"(?i)^wikibase:label\b",
                rest,
            ):

                raise ValueError(
                    "SPARQL federation via SERVICE "
                    "is not allowed"
                )

        if re.search(
            r"(?i)\bFROM\s+<",
            sparql,
        ):

            raise ValueError(
                "FROM clauses are not allowed"
            )

        max_results = _bounded_int(
            max_results,
            100,
            1,
            500,
            "max_results",
        )

        data = self._get_json(
            WIKIDATA_SPARQL,
            {
                "query": sparql,
                "format": "json",
            },
            timeout=self.query_timeout,
            accept=(
                "application/"
                "sparql-results+json"
            ),
        )

        head = data.get("head") or {}

        variables = (
            head.get("vars")
            if isinstance(head, dict)
            else None
        ) or []

        bindings = (
            (data.get("results") or {}).get(
                "bindings"
            )
            or []
        )

        if not isinstance(bindings, list):
            bindings = []

        rows = []

        for binding in bindings[:max_results]:

            if not isinstance(binding, dict):
                continue

            row = {}

            for variable, value in binding.items():

                if isinstance(value, dict):
                    row[variable] = value.get(
                        "value"
                    )
                else:
                    row[variable] = value

            rows.append(row)

        return {
            "success": True,
            "vars": variables,
            "row_count": len(rows),
            "total_rows": len(bindings),
            "truncated": (
                len(bindings) > len(rows)
            ),
            "rows": rows,
        }
