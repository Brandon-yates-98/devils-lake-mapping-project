-- ============================================================
-- Devil's Lake Community Map — photo gallery infrastructure
--
-- 1. photo_meta jsonb column on osm_geometries — ordered list of
--    {url, caption} objects; authoritative order for the gallery.
--    photos text[] kept for backward compat.
-- 2. pending_images table — anonymous public submissions awaiting
--    editor approval.
-- 3. pending-photos storage bucket — private until approved.
-- 4. set_feature_photos_v2() — updates both photos[] and photo_meta.
-- 5. submit_pending_image()  — anon-accessible INSERT.
-- 6. approve_pending_image() — auth-only; moves to approved photos.
-- 7. nearby_features_for_image() — spatial lookup for batch uploader.
-- ============================================================

-- ── 1. photo_meta column ────────────────────────────────────
alter table osm_geometries
  add column if not exists photo_meta jsonb default '[]'::jsonb;

-- ── 2. pending_images table ─────────────────────────────────
create table if not exists pending_images (
  id               uuid primary key default gen_random_uuid(),
  feature_source   text,
  feature_key      text,
  url              text not null,
  caption          text,
  submitter_email  text,
  submitted_at     timestamptz default now(),
  status           text default 'pending',
  exif_lat         float,
  exif_lng         float,
  exif_taken_at    timestamptz,
  exif_raw         jsonb
);

alter table pending_images enable row level security;

drop policy if exists "pending anon insert"  on pending_images;
drop policy if exists "pending auth select"  on pending_images;
drop policy if exists "pending auth update"  on pending_images;
drop policy if exists "pending auth delete"  on pending_images;

create policy "pending anon insert" on pending_images
  for insert to anon, authenticated with check (true);
create policy "pending auth select" on pending_images
  for select to authenticated using (true);
create policy "pending auth update" on pending_images
  for update to authenticated using (true);
create policy "pending auth delete" on pending_images
  for delete to authenticated using (true);

-- ── 3. pending-photos storage bucket ────────────────────────
insert into storage.buckets (id, name, public)
values ('pending-photos', 'pending-photos', false)
on conflict (id) do update set public = false;

drop policy if exists "pending-photos anon insert" on storage.objects;
drop policy if exists "pending-photos auth select" on storage.objects;
drop policy if exists "pending-photos auth delete" on storage.objects;

create policy "pending-photos anon insert" on storage.objects
  for insert to anon, authenticated
  with check (bucket_id = 'pending-photos');
create policy "pending-photos auth select" on storage.objects
  for select to authenticated
  using (bucket_id = 'pending-photos');
create policy "pending-photos auth delete" on storage.objects
  for delete to authenticated
  using (bucket_id = 'pending-photos');

-- ── 4. set_feature_photos_v2 ────────────────────────────────
create or replace function set_feature_photos_v2(
  p_source     text,
  p_key        text,
  p_photos     text[],
  p_photo_meta jsonb
) returns void language plpgsql security definer as $$
begin
  update osm_geometries
  set
    photos     = coalesce(p_photos, '{}'),
    photo_meta = coalesce(p_photo_meta, '[]'::jsonb),
    updated_at = now()
  where source = p_source
    and (id::text = p_key or properties->>'_draw_id' = p_key);
end;
$$;

revoke execute on function set_feature_photos_v2(text,text,text[],jsonb) from public, anon;
grant  execute on function set_feature_photos_v2(text,text,text[],jsonb) to authenticated;

-- ── 5. submit_pending_image ──────────────────────────────────
create or replace function submit_pending_image(
  p_source       text,
  p_feature_key  text,
  p_url          text,
  p_caption      text,
  p_email        text,
  p_lat          float,
  p_lng          float,
  p_exif_raw     jsonb
) returns uuid language plpgsql security definer as $$
declare
  v_id uuid;
begin
  insert into pending_images
    (feature_source, feature_key, url, caption, submitter_email,
     exif_lat, exif_lng, exif_raw)
  values
    (p_source, p_feature_key, p_url, nullif(trim(p_caption),''),
     nullif(trim(p_email),''), p_lat, p_lng, p_exif_raw)
  returning id into v_id;
  return v_id;
end;
$$;

revoke execute on function submit_pending_image(text,text,text,text,text,float,float,jsonb) from public;
grant  execute on function submit_pending_image(text,text,text,text,text,float,float,jsonb) to anon, authenticated;

-- ── 6. approve_pending_image ────────────────────────────────
create or replace function approve_pending_image(p_id uuid)
returns void language plpgsql security definer as $$
declare
  rec pending_images%rowtype;
  v_meta jsonb;
begin
  select * into rec from pending_images where id = p_id;
  if not found then return; end if;

  -- append to photos[] and photo_meta on the target feature
  update osm_geometries
  set
    photos     = array_append(photos, rec.url),
    photo_meta = photo_meta || jsonb_build_array(
                   jsonb_build_object('url', rec.url, 'caption', coalesce(rec.caption, ''))),
    updated_at = now()
  where source = rec.feature_source
    and (id::text = rec.feature_key or properties->>'_draw_id' = rec.feature_key);

  update pending_images set status = 'approved' where id = p_id;
end;
$$;

revoke execute on function approve_pending_image(uuid) from public, anon;
grant  execute on function approve_pending_image(uuid) to authenticated;

-- ── 7. nearby_features_for_image ────────────────────────────
create or replace function nearby_features_for_image(
  p_lat      float,
  p_lng      float,
  p_radius_m float default 300
) returns table(
  feature_id   text,
  feature_source text,
  feature_name text,
  distance_m   float
) language sql security definer as $$
  select
    coalesce(properties->>'_draw_id', id::text) as feature_id,
    source                                       as feature_source,
    name                                         as feature_name,
    round(st_distance(
      geometry::geography,
      st_setsrid(st_makepoint(p_lng, p_lat), 4326)::geography
    )::numeric, 1)::float                        as distance_m
  from osm_geometries
  where source in ('climbing_areas','climbing_routes','climbing_boulders',
                   'campsites','trails')
    and st_dwithin(
      geometry::geography,
      st_setsrid(st_makepoint(p_lng, p_lat), 4326)::geography,
      p_radius_m
    )
  order by distance_m
  limit 20;
$$;

revoke execute on function nearby_features_for_image(float,float,float) from public;
grant  execute on function nearby_features_for_image(float,float,float) to anon, authenticated;
