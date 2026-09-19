-- SELECT only. Run with default_transaction_read_only=on and bounded timeouts.
-- Identifiers are fixed; release head and the grant matrix are bound values.
WITH roles AS (
  SELECT oid, rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,
         rolcanlogin
  FROM pg_roles
  WHERE rolname IN ('uranus_reader','admin_user','admin_migrator','admin_auth_operator')
), expected AS (
  SELECT key AS name, value AS privileges FROM jsonb_each(%(grants)s::jsonb)
), operator_expected(name, privileges) AS (
  VALUES ('alembic_version','["SELECT"]'::jsonb),
         ('auth_account','["SELECT","INSERT","UPDATE"]'::jsonb),
         ('auth_system_admin','["SELECT","INSERT","DELETE"]'::jsonb),
         ('auth_session','["SELECT","UPDATE"]'::jsonb)
), objects AS (
  SELECT c.oid,c.relname,c.relowner,c.relkind,n.nspname
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE c.relkind IN ('r','p','v','m','f')
), source_tables(name) AS (
  VALUES ('organization'),('venue'),('space'),('event'),('event_date'),('event_link'),
         ('license'),('event_category'),('event_type'),('event_type_link'),('genre_type'),
         ('language'),('link_type'),('pluto_image'),('pluto_image_link'),('user'),
         ('organization_partner_request'),('organization_member_link'),('organization_access_grants')
), problems(reason) AS (
  SELECT 'required_role_missing' WHERE (SELECT count(*) FROM roles) <> 4
  UNION ALL
  SELECT 'unsafe_role_attributes:'||rolname FROM roles
  WHERE rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR NOT rolcanlogin
  UNION ALL
  SELECT 'role_membership:'||r.rolname FROM roles r JOIN pg_auth_members m
    ON m.member=r.oid OR m.roleid=r.oid
  UNION ALL
  SELECT 'database_create_or_owner:'||r.rolname FROM roles r CROSS JOIN pg_database d
  WHERE d.datname=current_database() AND (d.datdba=r.oid OR has_database_privilege(r.oid,d.oid,'CREATE'))
  UNION ALL
  SELECT 'schema_create:'||r.rolname||':'||n.nspname FROM roles r CROSS JOIN pg_namespace n
  WHERE has_schema_privilege(r.oid,n.oid,'CREATE')
    AND NOT (r.rolname='admin_migrator' AND n.nspname='admin')
  UNION ALL
  SELECT 'admin_schema_owner' WHERE NOT EXISTS (
    SELECT 1 FROM pg_namespace n JOIN roles r ON r.oid=n.nspowner
    WHERE n.nspname='admin' AND r.rolname='admin_migrator')
  UNION ALL
  SELECT 'admin_schema_usage:'||r.rolname FROM roles r
  WHERE r.rolname IN ('admin_user','admin_migrator','admin_auth_operator')
    AND NOT has_schema_privilege(r.oid,'admin','USAGE')
  UNION ALL
  SELECT 'source_schema_usage' FROM roles r WHERE r.rolname='uranus_reader'
    AND NOT has_schema_privilege(r.oid,'uranus','USAGE')
  UNION ALL
  SELECT 'unexpected_schema_usage:'||r.rolname FROM roles r
  WHERE (r.rolname='uranus_reader' AND has_schema_privilege(r.oid,'admin','USAGE'))
     OR (r.rolname<>'uranus_reader' AND has_schema_privilege(r.oid,'uranus','USAGE'))
  UNION ALL
  SELECT 'reader_admin_privilege:'||o.relname FROM objects o CROSS JOIN roles r
  WHERE o.nspname='admin' AND r.rolname='uranus_reader'
    AND (has_table_privilege(r.oid,o.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
      OR has_any_column_privilege(r.oid,o.oid,'SELECT,INSERT,UPDATE,REFERENCES'))
  UNION ALL
  SELECT 'source_or_external_mutation:'||r.rolname||':'||o.nspname||'.'||o.relname
  FROM roles r CROSS JOIN objects o
  WHERE o.nspname NOT IN ('admin','pg_catalog','information_schema')
    AND o.nspname NOT LIKE 'pg_toast%%' AND o.nspname NOT LIKE 'pg_temp%%'
    AND (r.oid=o.relowner OR has_table_privilege(r.oid,o.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
      OR has_any_column_privilege(r.oid,o.oid,'INSERT,UPDATE,REFERENCES'))
  UNION ALL
  SELECT 'source_or_external_sequence_mutation:'||r.rolname||':'||c.relname
  FROM roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname NOT IN ('admin','pg_catalog','information_schema') AND c.relkind='S'
    AND (c.relowner=r.oid OR has_sequence_privilege(r.oid,c.oid,'USAGE,UPDATE'))
  UNION ALL
  SELECT 'unexpected_admin_sequence:'||c.relname FROM pg_class c
  WHERE c.relnamespace='admin'::regnamespace AND c.relkind='S'
  UNION ALL
  SELECT 'unexpected_function_owner:'||r.rolname||':'||n.nspname||'.'||p.proname
  FROM pg_proc p JOIN roles r ON r.oid=p.proowner JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE NOT (r.rolname='admin_migrator' AND n.nspname='admin')
  UNION ALL
  SELECT 'unexpected_type_owner:'||r.rolname||':'||n.nspname||'.'||t.typname
  FROM pg_type t JOIN roles r ON r.oid=t.typowner JOIN pg_namespace n ON n.oid=t.typnamespace
  WHERE NOT (r.rolname='admin_migrator' AND n.nspname='admin')
  UNION ALL
  SELECT 'unexpected_extension_owner:'||r.rolname||':'||e.extname
  FROM pg_extension e JOIN roles r ON r.oid=e.extowner
  UNION ALL
  SELECT 'source_grant_option:'||r.rolname||':'||o.relname FROM objects o CROSS JOIN roles r
  WHERE o.nspname='uranus' AND
    (has_table_privilege(r.oid,o.oid,'SELECT WITH GRANT OPTION')
      OR has_any_column_privilege(r.oid,o.oid,'SELECT WITH GRANT OPTION'))
  UNION ALL
  SELECT 'source_table_missing_or_unreadable:'||s.name FROM source_tables s CROSS JOIN roles r
  LEFT JOIN objects o ON o.nspname='uranus' AND o.relname=s.name
  WHERE r.rolname='uranus_reader' AND (o.oid IS NULL OR NOT has_table_privilege(r.oid,o.oid,'SELECT'))
  UNION ALL
  SELECT 'migration_head_mismatch' WHERE
    (SELECT array_agg(version_num::text ORDER BY version_num) FROM admin.alembic_version)
      IS DISTINCT FROM ARRAY[%(head)s::text]
  UNION ALL
  SELECT 'admin_table_missing:'||e.name FROM expected e LEFT JOIN objects o
    ON o.nspname='admin' AND o.relname=e.name WHERE o.oid IS NULL
  UNION ALL
  SELECT 'unexpected_admin_object:'||o.relname FROM objects o
    WHERE o.nspname='admin' AND NOT EXISTS(SELECT 1 FROM expected e WHERE e.name=o.relname)
  UNION ALL
  SELECT 'admin_object_owner:'||o.relname FROM objects o
    WHERE o.nspname='admin' AND o.relowner<>(SELECT oid FROM roles WHERE rolname='admin_migrator')
  UNION ALL
  SELECT 'runtime_missing_grant:'||e.name||':'||p.privilege
  FROM expected e JOIN objects o ON o.nspname='admin' AND o.relname=e.name
  CROSS JOIN LATERAL jsonb_array_elements_text(e.privileges) p(privilege)
  CROSS JOIN roles r WHERE r.rolname='admin_user' AND NOT has_table_privilege(r.oid,o.oid,p.privilege)
  UNION ALL
  SELECT 'runtime_excess_grant:'||e.name||':'||p.privilege
  FROM expected e JOIN objects o ON o.nspname='admin' AND o.relname=e.name
  CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),('REFERENCES'),('TRIGGER')) p(privilege)
  CROSS JOIN roles r WHERE r.rolname='admin_user'
    AND ((NOT e.privileges ? p.privilege AND has_table_privilege(r.oid,o.oid,p.privilege))
      OR has_table_privilege(r.oid,o.oid,p.privilege||' WITH GRANT OPTION'))
  UNION ALL
  SELECT 'runtime_excess_column_grant:'||e.name||':'||p.privilege
  FROM expected e JOIN objects o ON o.nspname='admin' AND o.relname=e.name
  CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) p(privilege)
  CROSS JOIN roles r WHERE r.rolname='admin_user'
    AND ((NOT e.privileges ? p.privilege AND has_any_column_privilege(r.oid,o.oid,p.privilege))
      OR has_any_column_privilege(r.oid,o.oid,p.privilege||' WITH GRANT OPTION'))
  UNION ALL
  SELECT 'operator_excess_grant:'||o.relname||':'||p.privilege
  FROM objects o LEFT JOIN operator_expected e ON e.name=o.relname
  CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),('REFERENCES'),('TRIGGER')) p(privilege)
  CROSS JOIN roles r WHERE o.nspname='admin' AND r.rolname='admin_auth_operator'
    AND ((NOT coalesce(e.privileges,'[]'::jsonb) ? p.privilege
      AND has_table_privilege(r.oid,o.oid,p.privilege))
      OR has_table_privilege(r.oid,o.oid,p.privilege||' WITH GRANT OPTION'))
  UNION ALL
  SELECT 'operator_excess_column_grant:'||o.relname||':'||p.privilege
  FROM objects o LEFT JOIN operator_expected e ON e.name=o.relname
  CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) p(privilege)
  CROSS JOIN roles r WHERE o.nspname='admin' AND r.rolname='admin_auth_operator'
    AND ((NOT coalesce(e.privileges,'[]'::jsonb) ? p.privilege
      AND has_any_column_privilege(r.oid,o.oid,p.privilege))
      OR has_any_column_privilege(r.oid,o.oid,p.privilege||' WITH GRANT OPTION'))
  UNION ALL
  SELECT 'unexpected_maintain:'||r.rolname||':'||c.relname
  FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a CROSS JOIN roles r
  WHERE a.privilege_type='MAINTAIN' AND a.grantee IN (0,r.oid)
    AND NOT (r.rolname='admin_migrator' AND c.relnamespace='admin'::regnamespace)
  UNION ALL
  SELECT 'cross_schema_admin_fk:'||k.conname FROM pg_constraint k
  JOIN pg_class a ON a.oid=k.conrelid JOIN pg_namespace na ON na.oid=a.relnamespace
  JOIN pg_class b ON b.oid=k.confrelid JOIN pg_namespace nb ON nb.oid=b.relnamespace
  WHERE k.contype='f' AND (na.nspname='admin' OR nb.nspname='admin') AND na.nspname<>nb.nspname
  UNION ALL
  SELECT 'admin_user_trigger:'||t.tgname FROM pg_trigger t JOIN objects o ON o.oid=t.tgrelid
    WHERE o.nspname='admin' AND NOT t.tgisinternal
  UNION ALL
  SELECT 'admin_rule:'||w.rulename FROM pg_rewrite w JOIN objects o ON o.oid=w.ev_class
    WHERE o.nspname='admin'
  UNION ALL
  SELECT 'event_trigger:'||evtname FROM pg_event_trigger WHERE evtenabled<>'D'
  UNION ALL
  SELECT 'accessible_security_definer:'||r.rolname||':'||n.nspname||'.'||p.proname
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN roles r
  WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
    AND has_schema_privilege(r.oid,n.oid,'USAGE') AND has_function_privilege(r.oid,p.oid,'EXECUTE')
  UNION ALL
  SELECT 'migrator_default_privileges_require_review' FROM pg_default_acl d JOIN roles r ON r.oid=d.defaclrole
    WHERE r.rolname='admin_migrator'
)
SELECT coalesce(jsonb_agg(DISTINCT reason ORDER BY reason),'[]'::jsonb) AS violations FROM problems;
