# MCP Apps Integration Plan

## Overview

MCP Apps let tools return interactive UIs (charts, tables, forms, dashboards) rendered directly in the conversation instead of plain text/JSON. FastMCP builds on the MCP Apps extension using Prefab UI, a Python component library.

mcp-generator can ship two layers of UI support:

1. **Curated display tools** -- a small, API-agnostic library of generic UI tools that work with any generated server
2. **Generated display tools** -- API-specific UI tools derived from OpenAPI response schemas

The curated set ships first and acts as the foundation. Generated tools are an opt-in enhancement that builds on top.

---

## Phase 1: Curated Display Tools

A reusable module of generic display tools that the LLM fills with data from API responses. These are API-agnostic and ship once as part of mcp-generator.

### Tool Catalog

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `show_table` | Tabular data display | `title`, `columns: list[dict]`, `rows: list[dict]` |
| `show_detail` | Key-value detail view | `title`, `fields: list[dict]` |
| `show_chart` | Bar/line/area charts | `title`, `chart_type`, `data`, `x_axis`, `y_axis` |
| `show_form` | Dynamic form that calls back into a generated tool | `title`, `fields: list[dict]`, `submit_tool: str` |
| `show_comparison` | Side-by-side comparison | `title`, `items: list[dict]`, `highlight_key: str` |

### Architecture

```
generated_mcp/
  apps/
    __init__.py
    display_tools.py      <-- curated tools (show_table, show_detail, etc.)
  servers/
    pet_server.py          <-- existing generated API tools
    store_server.py
```

The curated tools are added as a `FastMCPApp` provider to the main server:

```python
from fastmcp import FastMCP, FastMCPApp
from .apps.display_tools import display_app

mcp = FastMCP("Petstore")
mcp.add_provider(display_app)
```

### Example: show_table

```python
@display_app.tool(app=True)
def show_table(title: str, columns: list[dict], rows: list[dict]) -> PrefabApp:
    """Display data as an interactive table."""
    with Column(gap=4, css_class="p-6") as view:
        Heading(title)
        DataTable(
            data=rows,
            columns=[TableColumn(key=c["key"], label=c["label"]) for c in columns],
        )
    return PrefabApp(view=view)
```

The LLM calls it with data from any API response:

```
show_table(
  title="Available Pets",
  columns=[{"key": "id", "label": "ID"}, {"key": "name", "label": "Name"}, {"key": "status", "label": "Status"}],
  rows=[{"id": 1, "name": "Buddy", "status": "available"}, ...]
)
```

### Delivery

- Ship `display_tools.py` as a static template in `mcp_generator/templates/`
- Generator copies it into `generated_mcp/apps/` during generation
- Controlled by a `--enable-apps` CLI flag (off by default until stable)
- `pyproject.toml` gains `fastmcp[apps]` as an optional dependency

---

## Phase 2: Generated Display Tools

API-specific display tools derived from OpenAPI response schemas. These wrap API calls and render purpose-built UIs with the correct columns, field names, and layout.

### How It Works

#### Step 1: Extract response schemas at introspection time

The OpenAPI spec already declares response shapes:

```yaml
/pets/{petId}:
  get:
    operationId: getPetById
    responses:
      200:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:    { type: integer }
                name:  { type: string }
                status: { type: string, enum: [available, pending, sold] }
```

`introspection.py` already parses responses (line 404). We add a `ResponseSchema` dataclass to `ToolSpec`:

```python
@dataclass
class ResponseField:
    name: str
    python_type: str
    is_enum: bool = False
    enum_values: list[str] = field(default_factory=list)
    is_nested_object: bool = False
    is_array: bool = False
    nested_fields: list["ResponseField"] = field(default_factory=list)

@dataclass
class ResponseSchema:
    fields: list[ResponseField]
    is_array: bool = False          # top-level is list vs single object
    is_object: bool = False         # top-level is an object with properties
```

#### Step 2: Classify the response shape

A heuristic on the schema determines which display pattern to use:

| Response Shape | Display Pattern | Components |
|----------------|----------------|------------|
| `type: array` of objects | Table view | `DataTable` with columns from properties |
| `type: object` with properties | Detail view | `Column` of key-value `Row`s, `Badge` for enums |
| Object with nested array | Detail + embedded table | Detail card + `DataTable` for the nested list |
| Scalar / string | No UI generated | Falls back to curated tools |

#### Step 3: Generate display tool code

A new `render_display_tool()` function in `renderers.py` emits the code.

**Detail view** (from `GET /pets/{petId}`):

```python
@mcp.tool(app=True)
def show_pet_detail(pet_id: int) -> PrefabApp:
    """Display pet details."""
    result = api.get_pet_by_id(pet_id=pet_id)

    with Column(gap=4, css_class="p-6") as view:
        Heading(f"Pet: {result.get('name', 'Unknown')}")
        with Row(gap=2):
            Text("ID"); Badge(str(result.get("id", "")))
        with Row(gap=2):
            Text("Status"); Badge(result.get("status", ""), variant="outline")
        with Row(gap=2):
            Text("Category"); Text(result.get("category", {}).get("name", ""))
    return PrefabApp(view=view)
```

**Table view** (from `GET /pets`):

```python
@mcp.tool(app=True)
def show_pets_table(status: str | None = None) -> PrefabApp:
    """Display pets as a searchable table."""
    results = api.find_pets_by_status(status=status)

    with Column(gap=4, css_class="p-6") as view:
        Heading("Pets")
        DataTable(
            data=results,
            columns=[
                TableColumn(key="id", label="ID"),
                TableColumn(key="name", label="Name"),
                TableColumn(key="status", label="Status"),
            ],
        )
    return PrefabApp(view=view)
```

#### Step 4: Integration in the pipeline

```
introspection.py  -->  extracts ResponseSchema from spec (new field on ToolSpec)
                            |
generator.py      -->  passes ResponseSchema to renderer
                            |
renderers.py      -->  render_display_tool() generates code (new function)
                            |
writers.py        -->  writes display_tools.py alongside pet_server.py
```

### Edge Cases

- **Undocumented responses**: Skip generation, fall back to curated tools
- **`additionalProperties: true`**: Skip -- too dynamic for static columns
- **Deeply nested objects (3+ levels)**: Flatten to 2 levels max
- **Binary / file responses**: Skip UI generation
- **`$ref` cycles**: Detect and break at depth limit

### Delivery

- Controlled by `--generate-ui` CLI flag (off by default)
- Requires `--enable-apps` as a prerequisite
- Generated into `generated_mcp/apps/` alongside curated tools
- One display file per tag (mirrors server file structure): `apps/pet_display.py`, `apps/store_display.py`

---

## Dependencies

```toml
# pyproject.toml (generated)
[project.optional-dependencies]
apps = ["prefab-ui>=0.17.0,<1.0.0"]

[project]
dependencies = [
    "fastmcp[apps]>=3.2.0,<4.0.0",   # bumped from 3.1.0 for FastMCPApp support
    # ... existing deps
]
```

Prefab UI must be pinned by the user for production (per FastMCP docs -- Prefab has frequent breaking changes).

---

## CLI Interface

```
mcp-generator generate --spec openapi.json --enable-apps             # curated only
mcp-generator generate --spec openapi.json --enable-apps --generate-ui  # curated + generated
```

---

## Rollout

| Phase | What | Depends On |
|-------|------|------------|
| 1a | Ship curated display tools template | fastmcp[apps] dependency |
| 1b | Wire `--enable-apps` flag, copy template during generation | Phase 1a |
| 1c | Add curated tools as provider in main server template | Phase 1b |
| 2a | Add `ResponseSchema` to `ToolSpec` + extraction in `introspection.py` | Phase 1b |
| 2b | Add `render_display_tool()` to `renderers.py` | Phase 2a |
| 2c | Wire `--generate-ui` flag, write display files in `writers.py` | Phase 2b |
| 2d | Tests: verify generated display tools for petstore spec | Phase 2c |
