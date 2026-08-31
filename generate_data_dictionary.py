"""
Data Dictionary Generator for Unity Catalog
===========================================

Runs in a Databricks notebook or as a Databricks Job. Queries Unity Catalog's
information_schema for the metadata inventory (catalog > schema > table > column,
plus COMMENTs) and writes a single self-contained, searchable HTML file.

The output HTML has no backend and no external dependencies — one file you can
drop into SharePoint (or any web surface) for employees to browse and search.
It only ever contains METADATA (names, types, comments), never row data.

USAGE (Databricks notebook)
---------------------------
1. Set the CONFIG block below (which catalogs to include, output path).
2. Run all cells. The HTML is written to OUTPUT_PATH.
3. Download it (or have the job copy it) and upload to SharePoint.

Schedule it as a Job (nightly/weekly) to keep the dictionary current.
"""

from datetime import datetime, timezone
import html
import json

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Which catalogs to include. Leave as None to include everything the running
# identity can see. Populate to expose only curated catalogs (recommended:
# point at your 'gold'/presentation catalog so raw/bronze stays hidden).
INCLUDE_CATALOGS = None            # e.g. ["gold", "analytics"]

# Catalogs to always exclude (system + legacy metastore are noise for discovery).
EXCLUDE_CATALOGS = ["system", "information_schema", "__databricks_internal"]

# Where to write the HTML. In Databricks, a Volume path is convenient:
OUTPUT_PATH = "/Volumes/main/default/exports/data_dictionary.html"

# Title shown at the top of the page.
TITLE = "Data Dictionary"
SUBTITLE = "What data exists — search to find what to ask for."


# ---------------------------------------------------------------------------
# 1. FETCH METADATA (Databricks / Spark)
# ---------------------------------------------------------------------------

def fetch_metadata(spark):
    """Query information_schema across all visible catalogs and return a list
    of plain dict rows. Uses system.information_schema so we get every catalog
    in one shot rather than iterating catalog-by-catalog."""

    # Tables (+ comments). We pull table_type so we can show views vs tables.
    tables_df = spark.sql("""
        SELECT table_catalog, table_schema, table_name, table_type, comment
        FROM system.information_schema.tables
    """)

    # Columns (+ comments, types, ordinal for stable ordering).
    columns_df = spark.sql("""
        SELECT table_catalog, table_schema, table_name,
               column_name, data_type, ordinal_position, comment
        FROM system.information_schema.columns
    """)

    tables = [r.asDict() for r in tables_df.collect()]
    columns = [r.asDict() for r in columns_df.collect()]
    return tables, columns


# ---------------------------------------------------------------------------
# 2. SHAPE INTO A NESTED STRUCTURE
# ---------------------------------------------------------------------------

def build_tree(tables, columns,
               include_catalogs=INCLUDE_CATALOGS,
               exclude_catalogs=EXCLUDE_CATALOGS):
    """Turn flat table/column rows into a nested catalog>schema>table>column
    structure, applying include/exclude filtering."""

    exclude = set(exclude_catalogs or [])
    include = set(include_catalogs) if include_catalogs else None

    def keep(cat):
        if cat in exclude:
            return False
        if include is not None and cat not in include:
            return False
        return True

    # Index columns by (catalog, schema, table).
    cols_by_table = {}
    for c in columns:
        if not keep(c["table_catalog"]):
            continue
        key = (c["table_catalog"], c["table_schema"], c["table_name"])
        cols_by_table.setdefault(key, []).append(c)

    for key in cols_by_table:
        cols_by_table[key].sort(key=lambda c: c.get("ordinal_position") or 0)

    catalogs = {}
    for t in tables:
        cat = t["table_catalog"]
        if not keep(cat):
            continue
        sch = t["table_schema"]
        tbl = t["table_name"]
        key = (cat, sch, tbl)

        catalogs.setdefault(cat, {})
        catalogs[cat].setdefault(sch, {})
        catalogs[cat][sch][tbl] = {
            "name": tbl,
            "type": (t.get("table_type") or "").title(),
            "comment": t.get("comment") or "",
            "columns": [
                {
                    "name": c["column_name"],
                    "type": c.get("data_type") or "",
                    "comment": c.get("comment") or "",
                }
                for c in cols_by_table.get(key, [])
            ],
        }

    # Convert to sorted lists for stable rendering.
    tree = []
    for cat in sorted(catalogs):
        schemas = []
        for sch in sorted(catalogs[cat]):
            tbls = [catalogs[cat][sch][t] for t in sorted(catalogs[cat][sch])]
            schemas.append({"name": sch, "tables": tbls})
        tree.append({"name": cat, "schemas": schemas})
    return tree


def count_stats(tree):
    n_cat = len(tree)
    n_sch = sum(len(c["schemas"]) for c in tree)
    n_tbl = sum(len(s["tables"]) for c in tree for s in c["schemas"])
    n_col = sum(len(t["columns"]) for c in tree for s in c["schemas"] for t in s["tables"])
    return n_cat, n_sch, n_tbl, n_col


# ---------------------------------------------------------------------------
# 3. GENERATE SELF-CONTAINED HTML
# ---------------------------------------------------------------------------

def generate_html(tree, title=TITLE, subtitle=SUBTITLE):
    """Render the nested tree into one self-contained HTML string.

    Data is embedded as JSON and rendered client-side so search stays fast and
    the file has zero external dependencies."""

    n_cat, n_sch, n_tbl, n_col = count_stats(tree)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_json = json.dumps(tree, ensure_ascii=False)

    # Note: braces in the CSS/JS are doubled because we format() the data in.
    return _TEMPLATE.format(
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        generated=generated,
        n_cat=n_cat, n_sch=n_sch, n_tbl=n_tbl, n_col=n_col,
        data_json=data_json,
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #f7f8fa; --card: #ffffff; --ink: #1a2028; --muted: #5b6673;
    --line: #e4e8ee; --accent: #2557d6; --accent-soft: #eaf0ff;
    --chip: #eef1f5; --hit: #fff3ba; --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  header {{
    background: var(--card); border-bottom: 1px solid var(--line);
    padding: 22px 28px 18px; position: sticky; top: 0; z-index: 10;
  }}
  h1 {{ margin: 0 0 3px; font-size: 21px; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: 14px; margin-bottom: 14px; }}
  .searchbar {{ position: relative; max-width: 640px; }}
  #q {{
    width: 100%; padding: 11px 14px 11px 38px; font-size: 15px;
    border: 1px solid var(--line); border-radius: 9px; background: #fff; color: var(--ink);
    outline: none;
  }}
  #q:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }}
  .searchbar svg {{ position: absolute; left: 12px; top: 12px; color: var(--muted); }}
  .meta {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 12px; color: var(--muted); font-size: 13px; }}
  .meta b {{ color: var(--ink); }}
  main {{ max-width: 980px; margin: 0 auto; padding: 20px 28px 80px; }}
  .catalog {{ margin-bottom: 26px; }}
  .catalog > h2 {{
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); margin: 0 0 8px; font-weight: 700;
  }}
  .schema {{ margin: 0 0 14px; }}
  .schema-name {{ font-weight: 600; font-size: 14px; color: var(--ink); margin: 12px 0 6px; }}
  .schema-name .path {{ color: var(--muted); font-weight: 400; font-family: var(--mono); font-size: 12px; }}
  details.table {{
    background: var(--card); border: 1px solid var(--line); border-radius: 9px;
    margin-bottom: 7px; overflow: hidden;
  }}
  details.table > summary {{
    cursor: pointer; padding: 11px 14px; list-style: none; display: flex;
    align-items: baseline; gap: 10px; user-select: none;
  }}
  details.table > summary::-webkit-details-marker {{ display: none; }}
  .tw {{ transition: transform .15s; color: var(--muted); font-size: 11px; }}
  details[open] .tw {{ transform: rotate(90deg); }}
  .tname {{ font-family: var(--mono); font-weight: 600; font-size: 14px; }}
  .ttype {{
    font-size: 11px; background: var(--chip); color: var(--muted);
    padding: 1px 7px; border-radius: 20px; text-transform: lowercase;
  }}
  .tcomment {{ color: var(--muted); font-size: 13px; margin-left: auto; text-align: right; max-width: 45%; }}
  .cols {{ border-top: 1px solid var(--line); padding: 4px 0; }}
  .col {{ display: flex; gap: 12px; padding: 6px 16px 6px 34px; align-items: baseline; }}
  .col:not(:last-child) {{ border-bottom: 1px solid #f2f4f7; }}
  .cname {{ font-family: var(--mono); font-size: 13px; min-width: 180px; }}
  .ctype {{ font-family: var(--mono); font-size: 12px; color: var(--accent); min-width: 130px; }}
  .ccomment {{ color: var(--muted); font-size: 13px; }}
  mark {{ background: var(--hit); border-radius: 2px; padding: 0 1px; }}
  .empty {{ color: var(--muted); font-style: italic; padding: 40px 0; text-align: center; }}
  .count {{ color: var(--muted); font-weight: 400; font-size: 12px; }}
  footer {{ color: var(--muted); font-size: 12px; text-align: center; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="searchbar">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="search" placeholder="Search tables, columns, descriptions…" autocomplete="off" autofocus>
  </div>
  <div class="meta">
    <span><b>{n_cat}</b> catalogs</span>
    <span><b>{n_sch}</b> schemas</span>
    <span><b>{n_tbl}</b> tables</span>
    <span><b>{n_col}</b> columns</span>
    <span id="resultcount"></span>
  </div>
</header>
<main id="out"></main>
<footer>Metadata only — no data values. Generated {generated}.</footer>

<script>
const DATA = {data_json};

const out = document.getElementById('out');
const q = document.getElementById('q');
const resultcount = document.getElementById('resultcount');

function esc(s) {{
  return (s || '').replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
}}
function hl(text, term) {{
  const t = esc(text);
  if (!term) return t;
  const i = t.toLowerCase().indexOf(term);
  if (i === -1) return t;
  return t.slice(0, i) + '<mark>' + t.slice(i, i + term.length) + '</mark>' + t.slice(i + term.length);
}}

function tableMatches(tbl, term) {{
  if (tbl.name.toLowerCase().includes(term)) return 'table';
  if ((tbl.comment || '').toLowerCase().includes(term)) return 'table';
  for (const c of tbl.columns) {{
    if (c.name.toLowerCase().includes(term) || (c.comment || '').toLowerCase().includes(term)) return 'column';
  }}
  return null;
}}

function render(term) {{
  term = (term || '').trim().toLowerCase();
  out.innerHTML = '';
  let shownTables = 0;

  for (const cat of DATA) {{
    const catSchemas = [];
    for (const sch of cat.schemas) {{
      const matchTables = [];
      for (const tbl of sch.tables) {{
        if (!term) {{ matchTables.push({{tbl, why: null}}); continue; }}
        const why = tableMatches(tbl, term);
        if (why) matchTables.push({{tbl, why}});
      }}
      if (matchTables.length) catSchemas.push({{sch, matchTables}});
    }}
    if (!catSchemas.length) continue;

    const catEl = document.createElement('div');
    catEl.className = 'catalog';
    catEl.innerHTML = '<h2>' + esc(cat.name) + '</h2>';

    for (const {{sch, matchTables}} of catSchemas) {{
      const schEl = document.createElement('div');
      schEl.className = 'schema';
      schEl.innerHTML = '<div class="schema-name">' + esc(sch.name) +
        ' <span class="path">' + esc(cat.name) + '.' + esc(sch.name) + '</span>' +
        ' <span class="count">· ' + matchTables.length + ' table' + (matchTables.length===1?'':'s') + '</span></div>';

      for (const {{tbl, why}} of matchTables) {{
        shownTables++;
        const det = document.createElement('details');
        det.className = 'table';
        if (term && why === 'column') det.open = true;

        const colMatch = term ? tbl.columns.filter(c =>
          c.name.toLowerCase().includes(term) || (c.comment||'').toLowerCase().includes(term)) : [];

        det.innerHTML =
          '<summary>' +
            '<span class="tw">▶</span>' +
            '<span class="tname">' + hl(tbl.name, term) + '</span>' +
            (tbl.type ? '<span class="ttype">' + esc(tbl.type.replace(/_/g,' ')) + '</span>' : '') +
            (tbl.comment ? '<span class="tcomment">' + hl(tbl.comment, term) + '</span>' : '') +
          '</summary>' +
          '<div class="cols">' +
            tbl.columns.map(c => {{
              const isHit = term && (c.name.toLowerCase().includes(term) || (c.comment||'').toLowerCase().includes(term));
              return '<div class="col"' + (isHit ? ' style="background:#fffdf0"' : '') + '>' +
                '<span class="cname">' + hl(c.name, term) + '</span>' +
                '<span class="ctype">' + esc(c.type) + '</span>' +
                '<span class="ccomment">' + hl(c.comment, term) + '</span>' +
              '</div>';
            }}).join('') +
          '</div>';
        schEl.appendChild(det);
      }}
      catEl.appendChild(schEl);
    }}
    out.appendChild(catEl);
  }}

  if (shownTables === 0) {{
    out.innerHTML = '<div class="empty">No tables or columns match &ldquo;' + esc(term) + '&rdquo;.</div>';
    resultcount.innerHTML = '';
  }} else {{
    resultcount.innerHTML = term ? ('<b>' + shownTables + '</b> matching tables') : '';
  }}
}}

let timer;
q.addEventListener('input', () => {{
  clearTimeout(timer);
  timer = setTimeout(() => render(q.value), 120);
}});
render('');
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 4. MAIN (Databricks entrypoint)
# ---------------------------------------------------------------------------

def main():
    """Databricks entrypoint. `spark` is available in notebooks/jobs."""
    tables, columns = fetch_metadata(spark)          # noqa: F821 (spark provided by Databricks)
    tree = build_tree(tables, columns)
    doc = generate_html(tree)

    # Write via dbutils so Volume/DBFS paths work.
    dbutils.fs.put(OUTPUT_PATH.replace("/Volumes", "dbfs:/Volumes")  # noqa: F821
                   if OUTPUT_PATH.startswith("/Volumes") else OUTPUT_PATH,
                   doc, overwrite=True)               # noqa: F821
    print(f"Wrote {len(doc):,} bytes to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
