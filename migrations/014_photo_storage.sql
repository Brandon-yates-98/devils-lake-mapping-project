    -- ============================================================
    -- Devil's Lake Mapping Project, Photo storage + usage tracking
    -- Run in Supabase: Dashboard → SQL Editor → New query
    --
    -- 1. Public "photos" bucket: anyone can view (the map hotlinks them),
    --    only signed-in editors can upload/modify.
    -- 2. set_feature_photos(): persists a feature's photo URL list into the
    --    osm_geometries.photos COLUMN (get_layer_geojson serves photos from
    --    the column, overriding any properties.photos key, writing the
    --    column is the only way edits surface on the map).
    -- 3. storage_usage(): total bytes across all buckets, for the editor's
    --    free-tier usage meter (1 GB limit on the Supabase free plan).
    -- ============================================================

    -- ── 1. Bucket + policies ────────────────────────────────────
    insert into storage.buckets (id, name, public)
    values ('photos', 'photos', true)
    on conflict (id) do update set public = true;

    drop policy if exists "photos public read"  on storage.objects;
    drop policy if exists "photos auth insert"  on storage.objects;
    drop policy if exists "photos auth update"  on storage.objects;
    drop policy if exists "photos auth delete"  on storage.objects;

    create policy "photos public read" on storage.objects
      for select using (bucket_id = 'photos');
    create policy "photos auth insert" on storage.objects
      for insert to authenticated with check (bucket_id = 'photos');
    create policy "photos auth update" on storage.objects
      for update to authenticated using (bucket_id = 'photos');
    create policy "photos auth delete" on storage.objects
      for delete to authenticated using (bucket_id = 'photos');

    -- ── 2. Persist a feature's photo list ───────────────────────
    create or replace function set_feature_photos(p_source text, p_key text, p_photos text[])
    returns void language plpgsql security definer as $$
    begin
      update osm_geometries
      set photos = coalesce(p_photos, '{}'), updated_at = now()
      where source = p_source
        and (id::text = p_key or properties->>'_draw_id' = p_key);
    end;
    $$;

    revoke execute on function set_feature_photos(text, text, text[]) from public, anon;
    grant  execute on function set_feature_photos(text, text, text[]) to authenticated;

    -- ── 3. Storage usage (editor meter) ─────────────────────────
    create or replace function storage_usage()
    returns bigint language sql security definer as $$
      select coalesce(sum((metadata->>'size')::bigint), 0) from storage.objects;
    $$;

    revoke execute on function storage_usage() from public, anon;
    grant  execute on function storage_usage() to authenticated;
