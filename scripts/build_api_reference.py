#!/usr/bin/env python3
"""Build the v2 API reference and the Postman downloads from the live API.

Everything this writes is GENERATED. Do not edit it by hand:

    api-reference/openapi.json         the OpenAPI file behind the API reference tab
    files/postman/mirai-voice-postman.zip   the Postman collection and its two environments
    docs.json                          only the endpoint groups of the "API reference" tab

Two sources, both published by the API itself:

* The Postman collection the console ships. Its CI refuses a release when a
  public /v2 route has no request in it, so it is the list of endpoints, with
  a name, a description, a worked request and real response examples each.
* The product contract, GET /v2/schema. It gives the request schemas (every
  field, its type, limits and meaning) and the response schemas it has.

Run it from the repository root:

    python3 scripts/build_api_reference.py            # rewrite the files
    python3 scripts/build_api_reference.py --check    # exit 1 if they are stale

`--sources DIR` reads the source files from a directory instead of the network
(the same file names as SOURCES below), which makes a build reproducible.
Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_FILE = ROOT / "api-reference" / "openapi.json"
DOCS_JSON = ROOT / "docs.json"
TAB = "API reference"

CONSOLE = "https://console.voice.miraiminds.co/static/postman/"
SOURCES = {
    "mirai-voice.postman_collection.json": CONSOLE + "mirai-voice.postman_collection.json",
    "sandbox.postman_environment.json": CONSOLE + "sandbox.postman_environment.json",
    "production.postman_environment.json": CONSOLE + "production.postman_environment.json",
    "mira-tts.postman_collection.json": CONSOLE + "mira-tts.postman_collection.json",
    "schema.json": "https://sandbox.voice.miraiminds.co/v2/schema",
}
#: Zipped unchanged into POSTMAN_ZIP for download. Mintlify serves .zip but not
#: .json as a static file, so the three JSON files ship as one archive.
POSTMAN_ZIP = ROOT / "files" / "postman" / "mirai-voice-postman.zip"
POSTMAN_DOWNLOADS = (
    "mirai-voice.postman_collection.json",
    "sandbox.postman_environment.json",
    "production.postman_environment.json",
)

SERVERS = [
    {"url": "https://sandbox.voice.miraiminds.co",
     "description": "Sandbox: trial workspaces, before your company goes live"},
    {"url": "https://prod.voice.miraiminds.co",
     "description": "Production: workspaces that have gone live"},
]

#: Hand-written pages at the top of the tab, and pages slotted in after an
#: endpoint ("METHOD /path" -> page).
LEAD_GROUP = {"group": "Get started", "pages": ["api-reference/introduction", "api-reference/postman"]}
INSERT_AFTER = {"POST /v2/calls": ["api-reference/calls/start-a-browser-call"]}
#: Group order in the tab. A group not named here goes before "Reference".
TAG_ORDER = ("Agents", "Calls", "Flows", "Tools and secrets", "Campaigns", "Do-not-call list",
             "Phone numbers", "Phone pools", "Telephony", "Transcriptions", "Speech to text",
             "Text to speech", "Wallet", "Reference")

#: Endpoints that exist in the contract but are not served on the public hosts
#: (probed without a key: 404), or that are not v2 paths.
SKIP_CONTRACT = {
    ("POST", "/v2/telephony/test-calls"): "not served on the public hosts",
    ("GET", "/v2/whatsapp/numbers"): "not served on the public hosts",
    ("POST", "/v2/whatsapp/numbers"): "not served on the public hosts",
    ("GET", "/v2/whatsapp/numbers/{id}"): "not served on the public hosts",
    ("PATCH", "/v2/whatsapp/numbers/{id}"): "not served on the public hosts",
    ("DELETE", "/v2/whatsapp/numbers/{id}"): "not served on the public hosts",
}

#: Postman requests left out of the reference, with the reason. Each was
#: checked live: these answer 503 shared_test_unavailable on every public host.
SKIP_POSTMAN = {
    ("POST", "/v2/telephony/phone-verifications"): "no shared test number on this deployment",
    ("POST", "/v2/telephony/phone-verifications/{}/verify"): "no shared test number on this deployment",
}

#: Contract operations with no Postman request: their page title, tag and
#: path-parameter names. The contract's own summary becomes the description.
CONTRACT_ONLY = {
    ("POST", "/v2/tts/stream/tokens"): ("Mint stream tokens", "Text to speech", {}),
}

#: Short descriptions for path parameters, by the name used in the path.
PARAM_DOCS = {
    "agent_id": "The agent's id (`agt_…`).",
    "call_id": "The call's id (`call_…`), from the `202` that created it.",
    "control_id": "The control's id (`ctl_…`), from the `202` that accepted it.",
    "refine_id": "The flow test's id (`frf_…`).",
    "tool_name": "The tool's name on the agent: lowercase letters, digits and underscores.",
    "secret_name": "The secret's name: lowercase letters, digits and underscores.",
    "callback_id": "The scheduled callback's id (`cbk_…`).",
    "campaign_id": "The campaign's id (`cmp_…`).",
    "contact_id": "The contact's `id`: yours if you sent one, otherwise the one the campaign assigned.",
    "phone": "The number in E.164, URL-encoded: `+` is sent as `%2B`.",
    "phone_number_id": "The phone number's id (`phn_…`).",
    "pool_id": "The pool's id (`ppl_…`).",
    "onboarding_id": "The business verification's id (`tbo_…`).",
    "rental_id": "The rental's id (`rent_…`), from *Quote a number*.",
    "connection_id": "The Plivo connection's id (`tcn_…`).",
    "verification_id": "The verification call's id (`verify_…`).",
    "transcription_id": "The transcription's id (`trn_…`).",
    "stt_request_id": "The request's id: the `X-Request-Id` the transcription answered with.",
    "tts_request_id": "The request's id: the `X-Request-Id` the synthesis answered with.",
    "revision": "The revision number, from *List revisions*.",
    "id": "The resource id.",
}
#: Postman variable -> path-parameter name, where the variable name reads badly.
PARAM_RENAME = {"dnc_phone": "phone"}

#: Values for Postman variables the collection leaves as placeholders.
VAR_OVERRIDES = {
    "test_number": "+919876543210",
    "$guid": "8f2c41a7-5b3e-4d19-9c6a-2e7f0b1d4c58",
    "tts_request_id": "tts_01J8Z3K7QF9YB2M4N6P8R0S2T4",
}

#: A sentence with one of these in it is about driving Postman, not the API.
POSTMAN_ONLY = ("Postman", "Send and Download", "Automatically follow redirects", "run this one last")

#: Wording in the Postman descriptions that only makes sense inside Postman.
TEXT_FIXES = (
    ("(Phone numbers folder)", "(see *Phone numbers*)"),
    ("*Phone numbers → Import a Plivo number*", "*Import a Plivo number*"),
    ("Flows folder", "Flows section"),
    ("**Telephony** folder", "**Telephony** section"),
    ("Agents folder's", "Agents section's"),
    ("this folder's", "this section's"),
    ("; the collection keeps it in `{{agent_revision}}` from the last response that returned the agent.",
     ": the `revision` of the last response that returned the agent."),
    (", which the collection keeps in `{{agent_revision}}`.", ": the `revision` of the last response that returned the agent."),
    ("`Authorization: Bearer {{api_key}}`", "`Authorization: Bearer sk_live_YOUR_API_KEY`"),
    ("`{{base_url}}/v1`", "`https://sandbox.voice.miraiminds.co/v1`"),
)

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
TEMPLATE_VAR = re.compile(r"\{\{\s*([$A-Za-z0-9_]+)\s*\}\}")


# --------------------------------------------------------------------------- sources

def load_sources(sources_dir: Path | None) -> dict[str, bytes]:
    out = {}
    for name, url in SOURCES.items():
        if sources_dir:
            out[name] = (sources_dir / name).read_bytes()
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "mirai-docs-build"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out[name] = r.read()
    return out


def walk_collection(collection: dict):
    """Yield (folder, item) for every request, in collection order."""
    for folder in collection["item"]:
        if "item" in folder:
            for item in folder["item"]:
                yield folder, item
        else:
            yield None, folder


# --------------------------------------------------------------------------- text

def clean(text: str | None) -> str:
    """Drop Postman-only instructions from a description written for Postman."""
    if not text:
        return ""
    for old, new in TEXT_FIXES:
        text = text.replace(old, new)
    lines = []
    for line in text.split("\n"):
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z*`(])", line)
        kept = [s for s in sentences if not any(w in s for w in POSTMAN_ONLY)]
        if kept or not line.strip():
            lines.append(" ".join(kept).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def response_label(name: str) -> str:
    """'402 — the wallet will not cover a minute' -> 'The wallet will not cover a minute'."""
    label = re.sub(r"^\s*\d{3}\s*[—–-]\s*", "", name or "").strip()
    return (label[:1].upper() + label[1:]) if label else ""


# --------------------------------------------------------------------------- values

def substitute(text: str, variables: dict[str, str]) -> str:
    def repl(m):
        key = m.group(1)
        return variables[key] if key in variables else m.group(0)
    return TEMPLATE_VAR.sub(repl, text)


def parse_body(raw: str, variables: dict[str, str]):
    text = substitute(raw, variables)
    try:
        return json.loads(text)
    except ValueError:
        return text


def infer_schema(value):
    """A plain schema for an example, so the playground can edit the body."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array", "items": infer_schema(value[0]) if value else {}}
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: infer_schema(v) for k, v in value.items()}}
    return {}


# --------------------------------------------------------------------------- paths

def postman_path(item: dict) -> tuple[str, list[str], list[dict]]:
    """Return (openapi path, [param names in order], query list)."""
    url = item["request"]["url"]
    raw = url["raw"] if isinstance(url, dict) else url
    path = raw.replace("{{base_url}}", "").split("?")[0]
    names = []

    def repl(m):
        name = PARAM_RENAME.get(m.group(1), m.group(1))
        names.append(name)
        return "{" + name + "}"
    path = TEMPLATE_VAR.sub(repl, path)
    query = url.get("query", []) if isinstance(url, dict) else []
    return path, names, query


def shape(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


# --------------------------------------------------------------------------- build

def build_openapi(src: dict[str, bytes]) -> tuple[dict, list[tuple[str, list[str]]]]:
    collection = json.loads(src["mirai-voice.postman_collection.json"])
    tts = json.loads(src["mira-tts.postman_collection.json"])
    contract = json.loads(src["schema.json"])

    variables = {v["key"]: str(v["value"]) for v in collection.get("variable", [])}
    variables.update({v["key"]: str(v["value"]) for v in tts.get("variable", []) if v["key"] not in variables})
    variables.update(VAR_OVERRIDES)
    variables.pop("base_url", None)
    variables.pop("api_key", None)

    contract_ops = {}
    for p, ops in contract["paths"].items():
        for m, op in ops.items():
            if m in HTTP_METHODS:
                contract_ops[(m.upper(), shape(p))] = (p, op)

    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Mirai Voice API",
            "version": contract["info"]["version"],
            "description": (
                "The v2 API for voice agents, calls, campaigns, phone numbers and speech. "
                "Every request carries `Authorization: Bearer sk_live_…`. "
                "Generated from the API's own contract and its Postman collection."
            ),
        },
        "servers": SERVERS,
        "security": [{"bearerAuth": []}],
        "tags": [],
        "paths": {},
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Your workspace secret key, `sk_live_` followed by 32 hex characters. "
                                   "Create one in the console under **Developers**.",
                }
            },
            "schemas": copy.deepcopy(contract["components"]["schemas"]),
        },
    }

    nav: list[tuple[str, list[str]]] = []  # (tag, ["METHOD /path", ...])
    tag_pages: dict[str, list[str]] = {}
    used: set[tuple[str, str]] = set()

    def add_tag(name: str, description: str):
        if name not in tag_pages:
            tag_pages[name] = []
            nav.append((name, tag_pages[name]))
            spec["tags"].append({"name": name, "description": clean(description)})

    def add_operation(tag: str, method: str, path: str, op: dict):
        key = (method, shape(path))
        if key in used:
            raise SystemExit(f"duplicate operation {method} {path}")
        used.add(key)
        spec["paths"].setdefault(path, {})[method.lower()] = op
        tag_pages[tag].append(f"{method} {path}")

    sources = [(collection, None), (tts, "Text to speech")]
    for coll, only_tag in sources:
        for folder, item in walk_collection(coll):
            method = item["request"]["method"].upper()
            path, names, query = postman_path(item)
            if not path.startswith("/v2/"):
                continue
            tag = only_tag or (folder["name"] if folder else "Reference")
            if (method, shape(path)) in SKIP_POSTMAN:
                continue
            if (method, shape(path)) in used:
                if not only_tag:
                    # A second worked request for the same route (a browser call
                    # on POST /v2/calls): its body and answers join the first
                    # request's page as more examples.
                    merge_variant(spec["paths"][path][method.lower()],
                                  operation_from_postman(item, method, path, names, query, {}, variables))
                continue  # the main collection already has it (List voices)
            add_tag(tag, (folder or {}).get("description", "") if not only_tag else
                    "Turn text into speech in one request, and read back what each request cost.")
            cpath, cop = contract_ops.get((method, shape(path)), (None, {}))
            add_operation(tag, method, path,
                          operation_from_postman(item, method, path, names, query, cop, variables))

    for (method, cpath), (title, tag, _renames) in CONTRACT_ONLY.items():
        _p, cop = contract_ops[(method, shape(cpath))]
        add_tag(tag, "")
        add_operation(tag, method, cpath, operation_from_contract(title, cop))

    # Every contract operation on a v2 path is either documented or skipped
    # for a stated reason, so a new endpoint cannot go missing silently.
    missing = []
    for (method, sh), (p, _op) in contract_ops.items():
        if not p.startswith("/v2/") or (method, sh) in used:
            continue
        if (method, p) not in SKIP_CONTRACT and (method, sh) not in SKIP_POSTMAN:
            missing.append(f"{method} {p}")
    if missing:
        raise SystemExit("contract operations with no page and no SKIP_CONTRACT reason:\n  "
                         + "\n  ".join(sorted(missing)))

    return spec, nav


def merge_variant(op: dict, variant: dict):
    """Add a variant request's body and responses to op as named examples."""
    vbody = variant.get("requestBody", {}).get("content", {}).get("application/json", {})
    body = op.get("requestBody", {}).get("content", {}).get("application/json")
    if body is not None:
        body.setdefault("examples", {}).update(vbody.get("examples", {}))
    for code, vresp in variant.get("responses", {}).items():
        resp = op.setdefault("responses", {}).setdefault(code, {"description": vresp.get("description", "")})
        for ctype, vmedia in vresp.get("content", {}).items():
            media = resp.setdefault("content", {}).setdefault(ctype, {})
            for name, ex in vmedia.get("examples", {}).items():
                media.setdefault("examples", {}).setdefault(name, ex)


def operation_from_contract(title: str, cop: dict) -> dict:
    op = {
        "operationId": cop.get("operationId"),
        "summary": title,
        "description": cop.get("summary", ""),
        "tags": [],
        "responses": copy.deepcopy(cop.get("responses")) or {"200": {"description": "OK"}},
    }
    for code, resp in list(op["responses"].items()):
        resp.setdefault("description", "OK" if code.startswith("2") else "Error")
    if cop.get("parameters"):
        op["parameters"] = copy.deepcopy(cop["parameters"])
    if cop.get("requestBody"):
        op["requestBody"] = copy.deepcopy(cop["requestBody"])
    return op


def operation_from_postman(item, method, path, names, query, cop, variables) -> dict:
    req = item["request"]
    op: dict = {
        "operationId": cop.get("operationId") or re.sub(r"[^a-z0-9]+", "_", item["name"].lower()).strip("_"),
        "summary": item["name"],
        "description": clean(req.get("description")),
        "tags": [],
    }

    params = []
    contract_params = {(p["in"], p["name"]): p for p in cop.get("parameters", [])}
    contract_path_params = [p for p in cop.get("parameters", []) if p["in"] == "path"]
    for i, name in enumerate(names):
        cp = contract_path_params[i] if i < len(contract_path_params) else {}
        var = next((k for k, v in PARAM_RENAME.items() if v == name), name)
        example = variables.get(var, "")
        params.append({
            "name": name, "in": "path", "required": True,
            "description": PARAM_DOCS.get(name) or cp.get("description") or "",
            "schema": {"type": "string"}, "example": example,
        })

    seen_query = set()
    for q in query:
        key = q["key"]
        seen_query.add(key)
        cp = contract_params.get(("query", key), {})
        value = substitute(str(q.get("value", "")), variables)
        schema = copy.deepcopy(cp.get("schema")) or {"type": "string"}
        entry = {
            "name": key, "in": "query",
            "required": bool(cp.get("required")),
            "description": (q.get("description") or cp.get("description") or "").strip(),
            "schema": schema,
        }
        if value and not TEMPLATE_VAR.search(value):
            entry["example"] = int(value) if schema.get("type") == "integer" and value.isdigit() else value
        params.append(entry)
    for (where, key), cp in contract_params.items():
        if where == "query" and key not in seen_query:
            params.append(copy.deepcopy(cp))

    for h in req.get("header", []):
        if h["key"].lower() in ("content-type", "authorization"):
            continue
        cp = contract_params.get(("header", h["key"]), {})
        entry = {
            "name": h["key"], "in": "header", "required": False,
            "description": clean(h.get("description")) or cp.get("description", ""),
            "schema": copy.deepcopy(cp.get("schema")) or {"type": "string"},
        }
        if h["key"] == "Idempotency-Key":
            entry["description"] = ("Up to 255 characters. The same key within 24 hours replays the first "
                                    "answer and creates nothing new. Build it from your own record, such as "
                                    "`order-8842-reminder-1`.")
            entry["example"] = "order-8842-reminder-1"
        elif h.get("value") and not TEMPLATE_VAR.search(h["value"]):
            entry["example"] = h["value"]
        params.append(entry)
    if params:
        op["parameters"] = params

    body = req.get("body") or {}
    if body.get("mode") == "raw" and body.get("raw", "").strip():
        example = parse_body(body["raw"], variables)
        schema = None
        if cop.get("requestBody"):
            schema = copy.deepcopy(cop["requestBody"]["content"].get("application/json", {}).get("schema"))
        content = {"schema": schema or infer_schema(example)}
        content["examples"] = {item["name"]: {"summary": item["name"], "value": example}}
        op["requestBody"] = {"required": True, "content": {"application/json": content}}
    elif body.get("mode") == "formdata":
        props, required = {}, []
        for f in body["formdata"]:
            if f.get("disabled"):
                prop = {"type": "string"}
            elif f.get("type") == "file":
                prop = {"type": "string", "format": "binary"}
                required.append(f["key"])
            else:
                prop = {"type": "string"}
                if f.get("value"):
                    prop["example"] = substitute(f["value"], variables)
            if f.get("description"):
                prop["description"] = f["description"]
            props[f["key"]] = prop
        op["requestBody"] = {"required": True, "content": {"multipart/form-data": {
            "schema": {"type": "object", "properties": props, "required": required}}}}
    elif cop.get("requestBody"):
        op["requestBody"] = copy.deepcopy(cop["requestBody"])

    op["responses"] = responses_from_postman(item, cop, variables)
    return op


def responses_from_postman(item, cop, variables) -> dict:
    out: dict = {}
    contract_responses = cop.get("responses", {})
    for i, ex in enumerate(item.get("response", [])):
        code = str(ex.get("code") or 200)
        resp = out.setdefault(code, {"description": response_label(ex.get("name")) or ex.get("status", "")})
        ctype = next((h["value"] for h in ex.get("header", []) if h["key"].lower() == "content-type"), None)
        lang = ex.get("_postman_previewlanguage")
        raw = ex.get("body")
        if raw is None or raw == "" or code in ("204", "304"):
            continue
        if not ctype:
            ctype = "application/json" if lang == "json" else "text/plain"
        ctype = ctype.split(";")[0].strip()
        value = parse_body(raw, variables) if ctype == "application/json" else substitute(raw, variables)
        media = resp.setdefault("content", {}).setdefault(ctype, {})
        if ctype == "application/json":
            cschema = (contract_responses.get(code, {}).get("content", {})
                       .get("application/json", {}).get("schema"))
            if cschema and "schema" not in media:
                media["schema"] = copy.deepcopy(cschema)
        label = response_label(ex.get("name")) or code
        examples = media.setdefault("examples", {})
        name = label if label not in examples else f"{label} ({i})"
        examples[name] = {"summary": ex.get("name") or code, "value": value}
    if not out:
        out = copy.deepcopy(contract_responses) or {"200": {"description": "OK"}}
        for code, resp in out.items():
            resp.setdefault("description", "OK")
    return out


def slug(text: str) -> str:
    """How Mintlify turns a tag or a summary into a URL segment."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "")).strip("-")


def linkify(text: str, pages: dict[str, str]) -> str:
    """Turn *Request name* references into links to that endpoint's page."""
    def repl(m):
        url = pages.get(m.group(1))
        return f"[{m.group(1)}]({url})" if url else m.group(0)
    return re.sub(r"(?<![*\w])\*([A-Z][^*\n]{2,60})\*(?![*\w])", repl, text)


def finish(spec: dict, nav):
    """Attach tags, now that every operation has its group, and link references."""
    pages = {"Start a browser call": "/api-reference/calls/start-a-browser-call"}
    for tag, entries in nav:
        for page in entries:
            method, path = page.split(" ", 1)
            op = spec["paths"][path][method.lower()]
            op["tags"] = [tag]
            pages.setdefault(op["summary"], f"/api-reference/{slug(tag)}/{slug(op['summary'])}")
    for ops in spec["paths"].values():
        for m, op in ops.items():
            if m in HTTP_METHODS and op.get("description"):
                op["description"] = linkify(op["description"], pages)
    for tag in spec["tags"]:
        tag["description"] = linkify(tag["description"], pages)
    rank = {t: i for i, t in enumerate(tag for tag, _ in ordered(nav))}
    spec["tags"].sort(key=lambda t: rank[t["name"]])
    return spec


def ordered(nav):
    rank = {t: i for i, t in enumerate(TAG_ORDER)}
    last = rank["Reference"]
    return sorted(nav, key=lambda tp: rank.get(tp[0], last - 0.5))


def nav_groups(nav) -> list[dict]:
    groups = [copy.deepcopy(LEAD_GROUP)]
    for tag, pages in ordered(nav):
        out = []
        for page in pages:
            out.append(page)
            out.extend(INSERT_AFTER.get(page, []))
        groups.append({"group": tag, "pages": out})
    return groups


def postman_zip(src: dict[str, bytes]) -> bytes:
    """The download, byte-for-byte reproducible: fixed timestamps and order."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in POSTMAN_DOWNLOADS:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, src[name])
    return buf.getvalue()


def render(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def updated_docs_json(groups: list[dict]) -> str:
    docs = json.loads(DOCS_JSON.read_text())
    tabs = docs["navigation"]["tabs"]
    tab = next((t for t in tabs if t.get("tab") == TAB), None)
    if tab is None:
        raise SystemExit(f'docs.json has no "{TAB}" tab')
    tab["openapi"] = "api-reference/openapi.json"
    tab["groups"] = groups
    return render(docs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed files are stale")
    ap.add_argument("--sources", type=Path, help="read the source files from this directory")
    args = ap.parse_args()

    src = load_sources(args.sources)
    spec, nav = build_openapi(src)
    spec = finish(spec, nav)

    files = {
        OPENAPI_FILE: render(spec).encode(),
        DOCS_JSON: updated_docs_json(nav_groups(nav)).encode(),
        POSTMAN_ZIP: postman_zip(src),
    }

    stale = [p for p, data in files.items() if not p.exists() or p.read_bytes() != data]
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)}")
        return 1 if stale else 0
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(files[p])
        print(f"wrote {p.relative_to(ROOT)}")
    ops = sum(len([m for m in v if m in HTTP_METHODS]) for v in spec["paths"].values())
    print(f"{ops} endpoints in {len(nav)} groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
