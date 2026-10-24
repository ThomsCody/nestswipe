-- Run as the database owner in both the application and postgres databases.
-- PostgreSQL 16 provides statement/activity access through pg_monitor.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE SCHEMA IF NOT EXISTS datadog;
REVOKE ALL ON SCHEMA datadog FROM PUBLIC;
GRANT USAGE ON SCHEMA datadog, public TO datadog;
GRANT pg_monitor TO datadog;

CREATE OR REPLACE FUNCTION datadog.explain_statement(
    l_query TEXT, OUT explain JSON
)
RETURNS SETOF JSON AS
$$
DECLARE
    curs REFCURSOR;
    plan JSON;
BEGIN
    SET TRANSACTION READ ONLY;
    OPEN curs FOR EXECUTE pg_catalog.concat('EXPLAIN (FORMAT JSON) ', l_query);
    FETCH curs INTO plan;
    CLOSE curs;
    RETURN QUERY SELECT plan;
END;
$$
LANGUAGE plpgsql
RETURNS NULL ON NULL INPUT
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp;

REVOKE ALL ON FUNCTION datadog.explain_statement(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION datadog.explain_statement(TEXT) TO datadog;
