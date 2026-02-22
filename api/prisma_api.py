import hashlib
import json
import re
import requests

GRAPHQL_URL = "https://graphql-api.prismamarket.ee/"
STORE_ID    = "542860184"   # Estonian ePrisma — the only store on prismamarket.ee

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://www.prismamarket.ee",
    "Referer":      "https://www.prismamarket.ee/",
    "User-Agent":   (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_APQ_HASH_CACHE: dict[str, str] = {}


def _load_query_from_bundle() -> str:
    """Extract RemoteFilteredProducts query from JS bundle."""
    from graphql import print_ast
    from graphql.language.ast import (
        DocumentNode, OperationDefinitionNode, FieldNode, SelectionSetNode,
        NameNode, VariableNode, ArgumentNode, VariableDefinitionNode,
        NamedTypeNode, NonNullTypeNode, ListTypeNode,
        FragmentDefinitionNode, FragmentSpreadNode, InlineFragmentNode,
        OperationType,
        StringValueNode, BooleanValueNode, IntValueNode, FloatValueNode,
        NullValueNode, EnumValueNode, ListValueNode,
        ObjectValueNode, ObjectFieldNode,
    )

    chunk_url = (
        "https://www.prismamarket.ee/_next/static/chunks/"
        "1521-05cd8b3e7f5c5e35.js"
    )
    r = requests.get(chunk_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
    r.raise_for_status()
    js = r.text

    # Find the Document AST for RemoteFilteredProducts
    doc_pos = None
    for m in re.finditer(r'\{kind:"Document"', js):
        if "RemoteFilteredProducts" in js[m.start():m.start() + 2000]:
            doc_pos = m.start()
            break
    if doc_pos is None:
        raise RuntimeError(
            "Could not find RemoteFilteredProducts AST in bundle. "
            "The chunk filename may have changed after a site deploy."
        )

    # Extract the full AST object
    depth = end = 0
    for i, c in enumerate(js[doc_pos:doc_pos + 200_000]):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = doc_pos + i
                break

    ast_js = js[doc_pos:end + 1]
    ast_dict = json.loads(re.sub(r'(?<=[{,])\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'"\1":', ast_js))

    OP = {
        "query":        OperationType.QUERY,
        "mutation":     OperationType.MUTATION,
        "subscription": OperationType.SUBSCRIPTION,
    }

    def to_ast(d):
        if not isinstance(d, dict):
            return d
        k = d.get("kind")
        if k == "Document":
            return DocumentNode(definitions=tuple(to_ast(x) for x in d["definitions"]))
        if k == "OperationDefinition":
            return OperationDefinitionNode(
                operation=OP[d["operation"]],
                name=to_ast(d.get("name")),
                variable_definitions=tuple(to_ast(x) for x in d.get("variableDefinitions", [])),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
                selection_set=to_ast(d["selectionSet"]),
            )
        if k == "FragmentDefinition":
            return FragmentDefinitionNode(
                name=to_ast(d["name"]),
                type_condition=to_ast(d["typeCondition"]),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
                selection_set=to_ast(d["selectionSet"]),
            )
        if k == "SelectionSet":
            return SelectionSetNode(selections=tuple(to_ast(x) for x in d["selections"]))
        if k == "Field":
            return FieldNode(
                alias=to_ast(d.get("alias")),
                name=to_ast(d["name"]),
                arguments=tuple(to_ast(x) for x in d.get("arguments", [])),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
                selection_set=to_ast(d.get("selectionSet")),
            )
        if k == "Argument":
            return ArgumentNode(name=to_ast(d["name"]), value=to_ast(d["value"]))
        if k == "VariableDefinition":
            return VariableDefinitionNode(
                variable=to_ast(d["variable"]),
                type=to_ast(d["type"]),
                default_value=to_ast(d.get("defaultValue")),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
            )
        if k == "Variable":    return VariableNode(name=to_ast(d["name"]))
        if k == "NamedType":   return NamedTypeNode(name=to_ast(d["name"]))
        if k == "NonNullType": return NonNullTypeNode(type=to_ast(d["type"]))
        if k == "ListType":    return ListTypeNode(type=to_ast(d["type"]))
        if k == "Name":        return NameNode(value=d["value"])
        if k == "FragmentSpread":
            return FragmentSpreadNode(
                name=to_ast(d["name"]),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
            )
        if k == "InlineFragment":
            return InlineFragmentNode(
                type_condition=to_ast(d.get("typeCondition")),
                directives=tuple(to_ast(x) for x in d.get("directives", [])),
                selection_set=to_ast(d["selectionSet"]),
            )
        if k == "StringValue":  return StringValueNode(value=d["value"])
        if k == "BooleanValue": return BooleanValueNode(value=d["value"])
        if k == "IntValue":     return IntValueNode(value=str(d["value"]))
        if k == "FloatValue":   return FloatValueNode(value=str(d["value"]))
        if k == "NullValue":    return NullValueNode()
        if k == "EnumValue":    return EnumValueNode(value=d["value"])
        if k == "ListValue":    return ListValueNode(values=tuple(to_ast(x) for x in d["values"]))
        if k == "ObjectValue":  return ObjectValueNode(fields=tuple(to_ast(x) for x in d["fields"]))
        if k == "ObjectField":  return ObjectFieldNode(name=to_ast(d["name"]), value=to_ast(d["value"]))
        return None

    return print_ast(to_ast(ast_dict))


def _register_query(operation: str = "RemoteFilteredProducts") -> str:
    """Register query hash with Prisma API via APQ phase-2."""
    query_str = _load_query_from_bundle()
    h = hashlib.sha256(query_str.encode()).hexdigest()

    payload = {
        "operationName": operation,
        "query":         query_str,
        "variables":     {"queryString": "test", "storeId": STORE_ID, "limit": 1, "from": 0},
        "extensions":    {"persistedQuery": {"version": 1, "sha256Hash": h}},
    }
    r = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()

    errors = data.get("errors", [])
    if any("PersistedQueryNotFound" in str(e) for e in errors):
        raise RuntimeError(f"Server rejected query registration: {errors}")

    _APQ_HASH_CACHE[operation] = h
    return h


def _get_hash(operation: str = "RemoteFilteredProducts") -> str:
    """Return cached hash, or register the query to get one."""
    if operation not in _APQ_HASH_CACHE:
        _register_query(operation)
    return _APQ_HASH_CACHE[operation]


def search_prisma(
    query:    str,
    size:     int  = 24,
    page:     int  = 0,
    store_id: str  = STORE_ID,
) -> list[dict]:
    """Search Prisma Market Estonia for products."""
    operation = "RemoteFilteredProducts"
    variables = {
        "queryString":        query,
        "storeId":            store_id,
        "limit":              size,
        "from":               page * size,
        "loop54DirectSearch": True,
        "fallbackToGlobal":   True,
        "useRandomId":        False,
    }

    h = _get_hash(operation)
    payload = {
        "operationName": operation,
        "variables":     variables,
        "extensions":    {"persistedQuery": {"version": 1, "sha256Hash": h}},
    }

    try:
        r = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        return []

    data = r.json()

    errors = data.get("errors", [])
    if any("PersistedQueryNotFound" in str(e) for e in errors):
        _APQ_HASH_CACHE.pop(operation, None)
        return search_prisma(query, size, page, store_id)

    if errors:
        return []

    result = (data.get("data") or {}).get("store", {}).get("products", {})
    raw    = result.get("items", [])
    total  = result.get("total", len(raw))

    products = []
    for item in raw:
        pricing = item.get("pricing") or {}
        comp    = item.get("comparisonPrice")

        products.append({
            "store":        "prisma",
            "name":         (item.get("name") or "").strip(),
            "brand":        item.get("brandName"),
            "price":        pricing.get("currentPrice"),
            "retail_price": pricing.get("regularPrice"),
            "unit":         item.get("comparisonUnit") or pricing.get("comparisonUnit"),
            "unit_price":   comp if isinstance(comp, (int, float)) else pricing.get("comparisonPrice"),
            "id":           item.get("ean") or item.get("id"),
            "ean":          item.get("ean"),
            "slug":         item.get("slug"),
            "on_sale":      pricing.get("campaignPrice") is not None,
            "image_url":    _image_url(item),
        })

    return products


def _image_url(item: dict) -> str | None:
    """Build a usable image URL from the urlTemplate + fixed modifiers."""
    try:
        tpl = (
            item["productDetails"]["productImages"]["mainImage"]["urlTemplate"]
        )
        return tpl.replace("{MODIFIERS}", "w_200,c_fit").replace("{EXTENSION}", "webp")
    except (KeyError, TypeError):
        return None