# Databricks notebook source
# MAGIC %md
# MAGIC # Explore Unity Catalog Metadata
# MAGIC
# MAGIC Quick, read-only check of what's in the catalog — **no volume, no file
# MAGIC writing, no dbutils needed.** Just runs queries and displays the results
# MAGIC in the notebook so you can confirm access and eyeball what's there before
# MAGIC generating the full data dictionary.
# MAGIC
# MAGIC Run the cells top to bottom. If cell 2 errors, jump to the "Fallback"
# MAGIC section at the bottom.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1. What catalogs can I even see?
# MAGIC Run this first — it lists the catalogs your identity has access to.

# COMMAND ----------

display(spark.sql("SHOW CATALOGS"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2. All tables (with descriptions)
# MAGIC Uses `system.information_schema`, which spans every catalog in one query.
# MAGIC `display()` gives a sortable, filterable grid. If this errors, the `system`
# MAGIC catalog may not be enabled for you — use the Fallback section instead.

# COMMAND ----------

tables_df = spark.sql("""
    SELECT table_catalog, table_schema, table_name, table_type, comment
    FROM system.information_schema.tables
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
    ORDER BY table_catalog, table_schema, table_name
""")
display(tables_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3. All columns (with data types and descriptions)
# MAGIC The `comment` column here is the key thing to inspect — if it's mostly
# MAGIC null, backfilling table/column comments is the highest-value next step for
# MAGIC making the dictionary useful to employees.

# COMMAND ----------

columns_df = spark.sql("""
    SELECT table_catalog, table_schema, table_name,
           column_name, data_type, ordinal_position, comment
    FROM system.information_schema.columns
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
    ORDER BY table_catalog, table_schema, table_name, ordinal_position
""")
display(columns_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4. Quick counts
# MAGIC Tells you the scale — 20 tables or 2,000 — which decides whether a single
# MAGIC HTML file is fine or the dictionary should be scoped to certain catalogs.

# COMMAND ----------

display(spark.sql("""
    SELECT table_catalog,
           COUNT(DISTINCT table_schema) AS schemas,
           COUNT(*)                      AS tables
    FROM system.information_schema.tables
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
    GROUP BY table_catalog
    ORDER BY table_catalog
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5. How complete are the comments?
# MAGIC A rough "documentation coverage" check — what fraction of tables and
# MAGIC columns actually have a description.

# COMMAND ----------

display(spark.sql("""
    SELECT
      SUM(CASE WHEN comment IS NULL OR comment = '' THEN 0 ELSE 1 END) AS documented,
      COUNT(*)                                                          AS total,
      ROUND(100.0 * SUM(CASE WHEN comment IS NULL OR comment = '' THEN 0 ELSE 1 END) / COUNT(*), 1) AS pct_documented
    FROM system.information_schema.columns
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Fallback — if `system.information_schema` isn't accessible
# MAGIC
# MAGIC Every catalog has its *own* `information_schema`. If the `system` catalog
# MAGIC is not enabled for you, query a specific catalog directly. Look at the
# MAGIC output of cell 1 (`SHOW CATALOGS`), pick a real catalog name, and set it
# MAGIC below.

# COMMAND ----------

CATALOG = "main"   # <-- change to a catalog from SHOW CATALOGS output

display(spark.sql(f"""
    SELECT table_catalog, table_schema, table_name, table_type, comment
    FROM {CATALOG}.information_schema.tables
    ORDER BY table_schema, table_name
"""))

# COMMAND ----------

display(spark.sql(f"""
    SELECT table_catalog, table_schema, table_name,
           column_name, data_type, ordinal_position, comment
    FROM {CATALOG}.information_schema.columns
    ORDER BY table_schema, table_name, ordinal_position
"""))
