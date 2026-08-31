# Databricks notebook source

display(spark.sql("SHOW CATALOGS"))

# COMMAND ----------

display(spark.sql("""
    SELECT table_catalog, table_schema, table_name, table_type, comment
    FROM system.information_schema.tables
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
    ORDER BY table_catalog, table_schema, table_name
"""))

# COMMAND ----------

display(spark.sql("""
    SELECT table_catalog, table_schema, table_name,
           column_name, data_type, ordinal_position, comment
    FROM system.information_schema.columns
    WHERE table_catalog NOT IN ('system', 'information_schema', '__databricks_internal')
    ORDER BY table_catalog, table_schema, table_name, ordinal_position
"""))
