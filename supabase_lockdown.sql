    -- Pre-deployment lockdown, run in Supabase: Dashboard → SQL Editor.
    -- Closes the public-write holes before the site/repo goes public.

    -- 1. Write-capable RPCs are SECURITY DEFINER and, by Postgres default,
    --    executable by everyone, including `anon`, whose key ships in the public
    --    HTML. Functions are looked up BY NAME in pg_proc (the live DB has
    --    drifted from the local migration files, names/signatures differ), so
    --    this works regardless of signature and skips anything that don't exist.
    --
    --    Importer-only RPCs lose all web-facing roles (run importers with the
    --    service_role key: op run --env-file=.env.tpl ...).
    --    Editor RPCs lose anon but KEEP authenticated, the editor is signed in.
    do $$
    declare r record;
    begin
      -- importer-only: no web-facing role needs these
      for r in
        select p.oid::regprocedure as sig
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname in ('import_feature', 'import_trail')
      loop
        execute format('revoke execute on function %s from public, anon, authenticated', r.sig);
        raise notice 'importer RPC locked: %', r.sig;
      end loop;

      -- editor write RPCs: signed-in users only
      for r in
        select p.oid::regprocedure as sig
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname in ('upsert_drawn_feature', 'delete_drawn_feature',
                            'delete_feature_by_id', 'upsert_osm_feature',
                            'duplicate_experience_layer', 'fork_layer_for_experience')
      loop
        execute format('revoke execute on function %s from public, anon', r.sig);
        execute format('grant execute on function %s to authenticated', r.sig);
        raise notice 'editor RPC locked to authenticated: %', r.sig;
      end loop;
    end $$;

    -- 2. Read RPCs stay public, they're what the map uses. (No change needed;
    --    listed here for the record.)
    --      get_layer_geojson(text), get_experience_config(text), get_trails_geojson()

    -- 3. OPTIONAL but recommended: scope writes to your own account instead of any
    --    authenticated user. The current policies pass for ANYONE who signs up.
    --    Find your user id: select id, email from auth.users;
    --    Then uncomment and fill in:
    --
    -- drop policy "Auth insert" on osm_geometries;
    -- drop policy "Auth update" on osm_geometries;
    -- create policy "Owner insert" on osm_geometries for insert
    --   with check (auth.uid() = '<YOUR-USER-UUID>');
    -- create policy "Owner update" on osm_geometries for update
    --   using (auth.uid() = '<YOUR-USER-UUID>');
    --    (repeat for the trails table and any other writable tables)

    -- 4. NOT SQL, do these in the Dashboard:
    --    a. Authentication → Sign In / Up → disable new email signups.
    --       Without this, anyone can supabase.auth.signUp() with the anon key and
    --       become `authenticated`, passing the write policies in (3).
    --    b. Storage → policies: confirm photo-bucket writes require authenticated
    --       (and ideally your uid), reads public.
    --    c. Mapbox dashboard: URL-restrict the pk. token to your Pages domain,
    --       custom domain, and localhost. Create a separate token for scripts
    --       (compute_drive_times.py), URL restrictions don't apply server-side.
