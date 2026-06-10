-- ============================================================
-- Apex Web Maps — Template / Experience System
-- Run in Supabase: Dashboard → SQL Editor → New query
-- Assumes osm_geometries table already exists.
-- ============================================================

-- ── 1. layer_templates ──────────────────────────────────────
-- Metadata registry for all data sources (12 OSM + custom drawn).
-- slug must match osm_geometries.source values exactly.
create table if not exists layer_templates (
  id           uuid        primary key default gen_random_uuid(),
  slug         text        not null unique,
  label        text        not null,
  geom_type    text        not null check (geom_type in ('line','polygon','point','mixed')),
  default_style jsonb      not null default '{}',
  layer_group  text        not null default 'Other',
  is_custom    boolean     not null default false,
  sort_order   int         not null default 0,
  created_at   timestamptz not null default now()
);

-- ── 2. experiences ──────────────────────────────────────────
create table if not exists experiences (
  id             uuid        primary key default gen_random_uuid(),
  slug           text        not null unique,
  title          text        not null,
  description    text,
  initial_center jsonb       not null default '[-89.73, 43.43]',
  initial_zoom   numeric     not null default 11,
  bounds         jsonb,
  basemap        text        not null default 'mapbox://styles/mapbox/outdoors-v12',
  is_public      boolean     not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create trigger experiences_updated_at
  before update on experiences
  for each row execute function update_updated_at();

-- ── 3. experience_layers ────────────────────────────────────
create table if not exists experience_layers (
  id                  uuid    primary key default gen_random_uuid(),
  experience_id       uuid    not null references experiences(id) on delete cascade,
  template_slug       text    not null references layer_templates(slug) on delete restrict,
  instance_type       text    not null default 'live' check (instance_type in ('live','static')),
  static_source       text,
  style_overrides     jsonb   not null default '{}',
  filter_expr         jsonb,
  visible_by_default  boolean not null default true,
  sort_order          int     not null default 0,
  constraint static_needs_source check (
    instance_type = 'live' or static_source is not null
  )
);

create index if not exists experience_layers_experience_id_idx on experience_layers(experience_id);
create index if not exists experience_layers_template_slug_idx on experience_layers(template_slug);

-- ── 4. RLS ──────────────────────────────────────────────────
alter table layer_templates  enable row level security;
alter table experiences      enable row level security;
alter table experience_layers enable row level security;

create policy "Public read"  on layer_templates  for select using (true);
create policy "Auth write"   on layer_templates  for all    using (auth.role() = 'authenticated');

create policy "Public read"  on experiences      for select using (is_public = true);
create policy "Auth all"     on experiences      for all    using (auth.role() = 'authenticated');

create policy "Public read"  on experience_layers for select using (true);
create policy "Auth all"     on experience_layers for all    using (auth.role() = 'authenticated');

-- ── 5. RPCs ─────────────────────────────────────────────────

-- get_experience_config: single bootstrap call for the public map.
-- Returns the experience metadata + all its layers in one round-trip.
-- source_key is computed: template_slug for live, static_source for static.
create or replace function get_experience_config(p_slug text)
returns json language sql security definer as $$
  select json_build_object(
    'experience', row_to_json(e.*),
    'layers', (
      select coalesce(json_agg(
        json_build_object(
          'id',                 el.id,
          'template_slug',      el.template_slug,
          'instance_type',      el.instance_type,
          'source_key',         case
                                  when el.instance_type = 'static' then el.static_source
                                  else el.template_slug
                                end,
          'style_overrides',    el.style_overrides,
          'filter_expr',        el.filter_expr,
          'visible_by_default', el.visible_by_default,
          'label',              lt.label,
          'geom_type',          lt.geom_type,
          'layer_group',        lt.layer_group,
          'default_style',      lt.default_style,
          'sort_order',         el.sort_order
        ) order by el.sort_order
      ), '[]'::json)
      from experience_layers el
      join layer_templates lt on lt.slug = el.template_slug
      where el.experience_id = e.id
    )
  )
  from experiences e
  where e.slug = p_slug and e.is_public = true;
$$;

-- fork_layer_for_experience: converts a live layer into a static (frozen) snapshot.
-- Copies all rows from the template source into a new 'static_<uuid>' source,
-- then marks the experience_layer as static.
create or replace function fork_layer_for_experience(p_experience_layer_id uuid)
returns text language plpgsql security definer as $$
declare
  v_template_slug  text;
  v_instance_type  text;
  v_static_source  text;
  v_count          int;
begin
  select template_slug, instance_type
  into v_template_slug, v_instance_type
  from experience_layers
  where id = p_experience_layer_id;

  if v_template_slug is null then
    raise exception 'experience_layer % not found', p_experience_layer_id;
  end if;

  if v_instance_type = 'static' then
    raise exception 'layer is already static';
  end if;

  v_static_source := 'static_' || p_experience_layer_id;

  insert into osm_geometries (source, osm_id, name, geometry, properties, photos, custom_data)
  select v_static_source, osm_id, name, geometry, properties, photos, custom_data
  from osm_geometries
  where source = v_template_slug;

  get diagnostics v_count = row_count;

  update experience_layers
  set instance_type = 'static',
      static_source = v_static_source
  where id = p_experience_layer_id;

  return v_static_source || ':' || v_count;
end;
$$;

-- upsert_drawn_feature: save a mapbox-gl-draw feature into osm_geometries.
-- Matches the import_feature(p_source, feature) pattern from supabase_migration.sql.
-- Uses properties->>'_draw_id' to upsert (update if exists, insert if new).
create or replace function upsert_drawn_feature(p_source text, p_feature json)
returns void language plpgsql security definer as $$
declare
  props    json;
  draw_id  text;
  geom     geometry;
begin
  props   := p_feature->'properties';
  draw_id := props->>'_draw_id';
  geom    := st_geomfromgeojson(p_feature->'geometry');

  if draw_id is not null then
    update osm_geometries
    set
      geometry    = geom,
      properties  = props::jsonb,
      name        = props->>'name',
      custom_data = coalesce((props->>'custom_data')::jsonb, custom_data),
      updated_at  = now()
    where source = p_source and properties->>'_draw_id' = draw_id;

    if not found then
      insert into osm_geometries (source, name, geometry, properties, custom_data)
      values (
        p_source,
        props->>'name',
        geom,
        props::jsonb,
        coalesce((props->>'custom_data')::jsonb, '{}')
      );
    end if;
  else
    insert into osm_geometries (source, name, geometry, properties)
    values (p_source, props->>'name', geom, props::jsonb);
  end if;
end;
$$;

-- delete_drawn_feature: remove a mapbox-gl-draw feature by _draw_id.
create or replace function delete_drawn_feature(p_source text, p_draw_id text)
returns void language sql security definer as $$
  delete from osm_geometries
  where source = p_source and properties->>'_draw_id' = p_draw_id;
$$;

-- ── 6. Seed layer_templates (12 OSM sources) ────────────────
insert into layer_templates (slug, label, geom_type, layer_group, default_style, sort_order)
values
  ('trails',    'Trails',          'line',    'Paths & Routes',     '{"color":"#27ae60"}',  0),
  ('routes',    'Named Routes',    'line',    'Paths & Routes',     '{"color":"#f39c12"}',  1),
  ('roads',     'Roads',           'line',    'Paths & Routes',     '{"color":"#8a9ba8"}',  2),
  ('natural',   'Natural Areas',   'mixed',   'Natural',            '{"color":"#52b788"}',  3),
  ('water',     'Water',           'mixed',   'Natural',            '{"color":"#3d9be9"}',  4),
  ('parks',     'Parks & Reserves','mixed',   'Natural',            '{"color":"#1abc9c"}',  5),
  ('landuse',   'Land Use',        'polygon', 'Natural',            '{"color":"#9b59b6"}',  6),
  ('buildings', 'Buildings',       'polygon', 'Built Environment',  '{"color":"#e17055"}',  7),
  ('parking',   'Parking',         'mixed',   'Built Environment',  '{"color":"#4a90d9"}',  8),
  ('barriers',  'Barriers',        'mixed',   'Built Environment',  '{"color":"#d63031"}',  9),
  ('pois',      'POIs',            'point',   'Points of Interest', '{"color":"#fdcb6e"}', 10),
  ('other',     'Other Features',  'mixed',   'Points of Interest', '{"color":"#636e72"}', 11)
on conflict (slug) do nothing;

-- ── 7. Seed default experience (all 12 layers, live) ────────
with new_exp as (
  insert into experiences (slug, title, description, initial_center, initial_zoom, basemap)
  values (
    'default',
    'Devils Lake Trail Map',
    'Full trail and feature map for Devils Lake State Park, Baraboo, WI',
    '[-89.73, 43.43]',
    11,
    'mapbox://styles/mapbox/outdoors-v12'
  )
  on conflict (slug) do nothing
  returning id
)
insert into experience_layers (experience_id, template_slug, visible_by_default, sort_order)
select
  new_exp.id,
  t.slug,
  t.slug in ('trails','routes','natural','water','parks','parking','pois'),
  t.sort_order
from new_exp, layer_templates t
where t.is_custom = false
on conflict do nothing;
