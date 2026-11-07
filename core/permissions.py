# core/permissions.py

from __future__ import annotations

import fnmatch
import posixpath
import sys

from dataclasses import dataclass
from enum import IntEnum, IntFlag, auto
from pathlib import Path
from typing import Any, Mapping, Protocol

import yaml


# =====================================================
# Capability
# =====================================================


class Capability(IntFlag):
    """
    Cosa un'operazione (o una risorsa) può fare.

    Le capability si combinano con ``|`` per dichiararle, ma la verifica
    è sempre di sottoinsieme: ``required & ~granted == 0``.
    """

    NONE = 0
    FILESYSTEM_READ = auto()
    FILESYSTEM_WRITE = auto()
    FILESYSTEM_CREATE = auto()
    FILESYSTEM_DELETE = auto()
    FILESYSTEM_EXEC = auto()
    MEMORY_READ = auto()
    MEMORY_WRITE = auto()
    NETWORK = auto()
    MCP_CALL = auto()
    COMPUTE = auto()
    AGENT_SPAWN = auto()
    AGENT_DATA = auto()


ALL_CAPABILITIES = Capability.NONE

for _capability in Capability:

    if _capability is not Capability.NONE:
        ALL_CAPABILITIES |= _capability


_CAPABILITIES_BY_NAME = {
    capability.name.lower(): capability
    for capability in Capability
    if capability is not Capability.NONE
}


def capability_names(
    mask: Capability,
) -> list[str]:
    """Nomi leggibili delle capability presenti nella maschera."""

    return [
        capability.name
        for capability in Capability
        if (
            capability is not Capability.NONE
            and mask & capability
        )
    ]


def _iter_capabilities(
    mask: Capability,
):

    for capability in Capability:

        if (
            capability is not Capability.NONE
            and mask & capability
        ):
            yield capability


def capabilities_from_permissions(
    read: bool,
    write: bool,
    shell: bool,
    network: bool = False,
    agents: bool = False,
) -> Capability:
    """
    Tetto di sistema derivato dalla configurazione attuale.

    ``permissions.write`` copre scrittura, creazione e cancellazione,
    come già fa la sandbox. La memoria segue gli stessi flag finché non
    avrà una configurazione propria. ``permissions.network`` abilita i
    tool che escono dalla macchina (feed, future API).
    """

    capabilities = Capability.NONE

    if read:
        capabilities |= (
            Capability.FILESYSTEM_READ
            | Capability.MEMORY_READ
        )

    if write:
        capabilities |= (
            Capability.FILESYSTEM_WRITE
            | Capability.FILESYSTEM_CREATE
            | Capability.FILESYSTEM_DELETE
            | Capability.MEMORY_WRITE
        )

    if shell:
        capabilities |= Capability.FILESYSTEM_EXEC

    if network:
        capabilities |= Capability.NETWORK

    #
    # I calcoli locali non escono dalla macchina e non toccano il
    # filesystem: sono sempre disponibili, ma la policy può comunque
    # negarli per singolo tool.
    #

    capabilities |= Capability.COMPUTE

    #
    # I tool MCP esistono solo se configurati; la capability serve alla
    # policy per concederli o negarli.
    #

    capabilities |= Capability.MCP_CALL

    if agents:
        capabilities |= (
            Capability.AGENT_SPAWN
            | Capability.AGENT_DATA
        )

    return capabilities


# =====================================================
# Effect
# =====================================================


class Effect(IntEnum):
    """
    Esito di una regola. L'ordine è significativo: in caso di conflitto
    vince il valore più alto, quindi ``DENY > ASK > ALLOW``.
    """

    ALLOW = 1
    ASK = 2
    DENY = 3


# =====================================================
# Scope
# =====================================================


def normalize_path(
    value: str | None,
) -> str:
    """
    Normalizza un percorso per il confronto con le policy.

    I percorsi assoluti restano assoluti: una regola relativa non li
    intercetta, quindi il risultato è negato (fail closed).
    """

    if value is None:
        return ""

    text = str(value).strip().replace("\\", "/")

    if not text:
        return ""

    text = posixpath.normpath(text)

    if text == ".":
        return ""

    if text.startswith("./"):
        text = text[2:]

    return text


def _path_matches(
    prefix: str,
    path: str,
) -> bool:

    prefix = normalize_path(prefix)
    path = normalize_path(path)

    if not prefix:
        return True

    return (
        path == prefix
        or path.startswith(prefix + "/")
    )


@dataclass(frozen=True, slots=True)
class RequestScope:
    """
    Contesto della richiesta: su cosa viene esercitata la capability.

    ``path`` e ``namespace`` sono opzionali: un tool senza percorso
    (es. ``free_space``) ha scope vuoto.
    """

    tool: str
    path: str | None = None
    namespace: str | None = None

    @classmethod
    def from_call(
        cls,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> "RequestScope":

        path = arguments.get("path")
        namespace = arguments.get("namespace")

        return cls(
            tool=tool,
            path=(
                normalize_path(path)
                if isinstance(path, str)
                else None
            ),
            namespace=(
                normalize_path(namespace)
                if isinstance(namespace, str)
                else None
            ),
        )


# =====================================================
# Regole, soggetti, risorse
# =====================================================


@dataclass(frozen=True, slots=True)
class Rule:
    """
    Una regola di policy: quali capability, con quale effetto, su quale
    scope.

    ``tools`` è una lista di glob sul nome del tool (``filesystem.*``);
    ``paths`` e ``namespaces`` sono prefissi. Un filtro assente vale
    "qualsiasi"; un filtro presente che non matcha rende la regola
    inapplicabile.
    """

    capabilities: Capability
    effect: Effect
    tools: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    namespaces: tuple[str, ...] = ()
    reason: str = ""

    def matches(
        self,
        scope: RequestScope,
    ) -> bool:

        if self.tools and not any(
            fnmatch.fnmatchcase(scope.tool, pattern)
            for pattern in self.tools
        ):
            return False

        if self.paths:

            if scope.path is None:
                return False

            if not any(
                _path_matches(prefix, scope.path)
                for prefix in self.paths
            ):
                return False

        if self.namespaces:

            if scope.namespace is None:
                return False

            if not any(
                _path_matches(prefix, scope.namespace)
                for prefix in self.namespaces
            ):
                return False

        return True

    def specificity(
        self,
        scope: RequestScope,
    ) -> tuple[int, int]:
        """
        Più filtri = più specifica; a parità, vince il prefisso più
        lungo. Serve per permettere eccezioni più precise di una regola
        generica.
        """

        count = sum(
            1
            for filters in (
                self.tools,
                self.paths,
                self.namespaces,
            )
            if filters
        )

        length = 0

        if scope.path is not None:

            for prefix in self.paths:

                if _path_matches(prefix, scope.path):
                    length = max(
                        length,
                        len(normalize_path(prefix)),
                    )

        if scope.namespace is not None:

            for prefix in self.namespaces:

                if _path_matches(prefix, scope.namespace):
                    length = max(
                        length,
                        len(normalize_path(prefix)),
                    )

        return count, length


@dataclass(frozen=True, slots=True)
class Subject:
    """
    Chi chiede il permesso: un agente, un utente, il sistema.

    ``default`` è l'effetto quando nessuna regola matcha. Il default
    sicuro è ``DENY``.
    """

    name: str
    kind: str = "agent"
    rules: tuple[Rule, ...] = ()
    default: Effect = Effect.DENY


@dataclass(frozen=True, slots=True)
class Resource:
    """
    L'oggetto della decisione: un tool con le sue capability.

    In futuro potrà rappresentare anche una nota del Vault, un percorso
    o un endpoint MCP; l'evaluator non cambia.
    """

    kind: str
    identifier: str
    capabilities: Capability

    @classmethod
    def from_tool(
        cls,
        tool: Any,
    ) -> "Resource":

        return cls(
            kind="tool",
            identifier=tool.name,
            capabilities=tool.capabilities,
        )


@dataclass(frozen=True, slots=True)
class Decision:
    effect: Effect
    reason: str
    rule: Rule | None = None


class PermissionDenied(PermissionError):
    """Richiesta negata dalla policy o dalla conferma umana."""

    def __init__(
        self,
        message: str,
        decision: Decision | None = None,
    ) -> None:

        super().__init__(message)

        self.decision = decision


# =====================================================
# Evaluator
# =====================================================


class PermissionEvaluator:
    """
    Incrocia soggetto, risorsa e scope e produce una decisione.

    Ordine delle verifiche:
        1. la risorsa deve offrire tutte le capability richieste;
        2. il tetto di sistema deve concederle;
        3. per ogni capability si applicano le regole del soggetto;
        4. senza regole vale il default del soggetto (DENY).
    """

    def __init__(
        self,
        ceiling: Capability,
    ) -> None:

        self.ceiling = ceiling

    def evaluate(
        self,
        subject: Subject,
        resource: Resource,
        scope: RequestScope,
    ) -> Decision:

        required = resource.capabilities

        if required is Capability.NONE:

            return Decision(
                Effect.ALLOW,
                "no capability required",
            )

        outside = required & ~self.ceiling

        if outside:

            return Decision(
                Effect.DENY,
                "outside system ceiling: "
                + ", ".join(
                    capability_names(outside)
                ),
            )

        results: list[
            tuple[Effect, Rule | None, Capability]
        ] = []

        for capability in _iter_capabilities(required):

            effect, rule = self._effect_for(
                subject,
                capability,
                scope,
            )

            results.append(
                (effect, rule, capability)
            )

        #
        # AND fra le capability richieste: vince l'effetto peggiore.
        #

        effect, rule, capability = max(
            results,
            key=lambda item: item[0].value,
        )

        if rule is not None and rule.reason:

            reason = rule.reason

        else:

            reason = (
                f"{capability.name}: "
                f"{effect.name.lower()}"
            )

            if rule is None:
                reason += " by default"

        return Decision(
            effect=effect,
            reason=reason,
            rule=rule,
        )

    def _effect_for(
        self,
        subject: Subject,
        capability: Capability,
        scope: RequestScope,
    ) -> tuple[Effect, Rule | None]:

        matching = [
            rule
            for rule in subject.rules
            if (
                rule.capabilities & capability
                and rule.matches(scope)
            )
        ]

        if not matching:
            return subject.default, None

        best = max(
            rule.specificity(scope)
            for rule in matching
        )

        top = [
            rule
            for rule in matching
            if rule.specificity(scope) == best
        ]

        #
        # A parità di specificità vince l'effetto più restrittivo.
        #

        rule = max(
            top,
            key=lambda item: item.effect.value,
        )

        return rule.effect, rule


# =====================================================
# Policy su file
# =====================================================


class PolicyError(RuntimeError):
    pass


@dataclass(slots=True)
class PolicySet:
    """Insieme delle policy caricate, per nome di soggetto."""

    subjects: dict[str, Subject]

    def get(
        self,
        name: str,
    ) -> Subject:
        """
        Restituisce il soggetto richiesto o un soggetto DENY totale.

        Un nome assente non è un errore fatale: si degrada a "nega
        tutto", che è il comportamento sicuro.
        """

        subject = self.subjects.get(name)

        if subject is not None:
            return subject

        return Subject(
            name=name,
            kind="agent",
            rules=(),
            default=Effect.DENY,
        )

    @classmethod
    def deny_all(cls) -> "PolicySet":

        return cls(subjects={})


def _parse_effect(
    value: Any,
    where: str,
) -> Effect:

    if not isinstance(value, str):

        raise PolicyError(
            f"{where} must be a string"
        )

    try:

        return Effect[value.strip().upper()]

    except KeyError as exc:

        raise PolicyError(
            f"{where}: unknown effect '{value}'. "
            f"Allowed: allow, ask, deny"
        ) from exc


def _parse_capabilities(
    value: Any,
    where: str,
) -> Capability:

    if not isinstance(value, list) or not value:

        raise PolicyError(
            f"{where} must be a non-empty list "
            f"of capabilities"
        )

    mask = Capability.NONE

    for item in value:

        if not isinstance(item, str):

            raise PolicyError(
                f"{where} entries must be strings"
            )

        capability = _CAPABILITIES_BY_NAME.get(
            item.strip().lower()
        )

        if capability is None:

            raise PolicyError(
                f"{where}: unknown capability '{item}'"
            )

        mask |= capability

    return mask


def _parse_string_list(
    value: Any,
    where: str,
) -> tuple[str, ...]:

    if not isinstance(value, list):

        raise PolicyError(
            f"{where} must be a list of strings"
        )

    result: list[str] = []

    for item in value:

        if not isinstance(item, str) or not item.strip():

            raise PolicyError(
                f"{where} entries must be "
                f"non-empty strings"
            )

        result.append(item)

    return tuple(result)


def _parse_rule(
    data: Any,
    where: str,
) -> Rule:

    if not isinstance(data, dict):

        raise PolicyError(
            f"{where} must be a mapping"
        )

    unknown = set(data) - {
        "capabilities",
        "effect",
        "tools",
        "paths",
        "namespaces",
        "reason",
    }

    if unknown:

        raise PolicyError(
            f"{where}: unknown keys "
            f"{sorted(unknown)}"
        )

    if "capabilities" not in data:

        raise PolicyError(
            f"{where}.capabilities is required"
        )

    if "effect" not in data:

        raise PolicyError(
            f"{where}.effect is required"
        )

    reason = data.get("reason", "")

    if not isinstance(reason, str):

        raise PolicyError(
            f"{where}.reason must be a string"
        )

    return Rule(
        capabilities=_parse_capabilities(
            data["capabilities"],
            f"{where}.capabilities",
        ),
        effect=_parse_effect(
            data["effect"],
            f"{where}.effect",
        ),
        tools=_parse_string_list(
            data.get("tools", []),
            f"{where}.tools",
        ),
        paths=_parse_string_list(
            data.get("paths", []),
            f"{where}.paths",
        ),
        namespaces=_parse_string_list(
            data.get("namespaces", []),
            f"{where}.namespaces",
        ),
        reason=reason,
    )


def _parse_subject(
    name: str,
    data: Any,
) -> Subject:

    where = f"subjects.{name}"

    if not isinstance(data, dict):

        raise PolicyError(
            f"{where} must be a mapping"
        )

    unknown = set(data) - {
        "kind",
        "default",
        "rules",
    }

    if unknown:

        raise PolicyError(
            f"{where}: unknown keys {sorted(unknown)}"
        )

    kind = data.get("kind", "agent")

    if kind not in {"agent", "user", "system"}:

        raise PolicyError(
            f"{where}.kind must be agent, user or system"
        )

    default = _parse_effect(
        data.get("default", "deny"),
        f"{where}.default",
    )

    raw_rules = data.get("rules", [])

    if not isinstance(raw_rules, list):

        raise PolicyError(
            f"{where}.rules must be a list"
        )

    rules = tuple(
        _parse_rule(
            rule,
            f"{where}.rules[{index}]",
        )
        for index, rule in enumerate(raw_rules)
    )

    return Subject(
        name=name,
        kind=kind,
        rules=rules,
        default=default,
    )


def load_policies(
    filename: str | Path,
) -> PolicySet:
    """
    Carica ``policy.yaml``.

    Qualunque problema solleva ``PolicyError``: chi chiama deve degradare
    a DENY totale (fail closed), non proseguire con permessi impliciti.
    """

    path = Path(filename)

    if not path.exists():

        raise PolicyError(
            f"Policy file not found: {path}"
        )

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as handle:

            data = yaml.safe_load(handle)

    except yaml.YAMLError as exc:

        raise PolicyError(
            f"Invalid YAML in {path}: {exc}"
        ) from exc

    except OSError as exc:

        raise PolicyError(
            f"Cannot read policy {path}: {exc}"
        ) from exc

    if data is None:

        raise PolicyError(
            f"Policy file is empty: {path}"
        )

    if not isinstance(data, dict):

        raise PolicyError(
            "Policy root must be a mapping"
        )

    unknown = set(data) - {"version", "subjects"}

    if unknown:

        raise PolicyError(
            f"Unknown policy keys: {sorted(unknown)}"
        )

    version = data.get("version", 1)

    if version != 1:

        raise PolicyError(
            f"Unsupported policy version: {version}"
        )

    raw_subjects = data.get("subjects", {})

    if not isinstance(raw_subjects, dict):

        raise PolicyError(
            "'subjects' must be a mapping"
        )

    subjects: dict[str, Subject] = {}

    for name, body in raw_subjects.items():

        if not isinstance(name, str) or not name.strip():

            raise PolicyError(
                "Subject names must be non-empty strings"
            )

        subjects[name] = _parse_subject(name, body)

    return PolicySet(subjects=subjects)


# =====================================================
# Conferma umana (ASK)
# =====================================================


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    subject: str
    tool: str
    capabilities: Capability
    arguments: Mapping[str, Any]
    reason: str
    agent_id: str | None = None
    parent_id: str | None = None


class ConfirmationProvider(Protocol):
    """
    Canale di consenso per l'effetto ASK.

    La CLI legge da stdin; una GUI potrà implementare lo stesso
    protocollo con un dialog modale, senza toccare l'harness.
    """

    def confirm(
        self,
        request: ConfirmationRequest,
    ) -> bool:
        ...


class DenyAllConfirmation:
    """Provider predefinito: senza canale umano, ASK vale DENY."""

    def confirm(
        self,
        request: ConfirmationRequest,
    ) -> bool:

        return False


class ConsoleConfirmation:
    """Consenso da console: default N, EOF e Ctrl-C valgono N."""

    ACCEPTED = {"y", "yes", "s", "si", "sì"}

    def __init__(
        self,
        stream=None,
    ) -> None:

        self.stream = stream or sys.stdout

    def confirm(
        self,
        request: ConfirmationRequest,
    ) -> bool:

        print(file=self.stream)
        print(
            f"Permesso richiesto: {request.tool}",
            file=self.stream,
        )

        if request.arguments:

            details = ", ".join(
                f"{key}={value!r}"
                for key, value in request.arguments.items()
            )

            print(
                f"Argomenti: {details}",
                file=self.stream,
            )

        if request.reason:

            print(
                f"Motivo: {request.reason}",
                file=self.stream,
            )

        try:

            answer = input("lo faccio? (y/N) ")

        except (EOFError, KeyboardInterrupt):

            print(file=self.stream)
            return False

        return answer.strip().lower() in self.ACCEPTED
