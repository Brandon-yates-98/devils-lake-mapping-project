-- ============================================================
-- Devil's Lake Mapping Project, add "Accessible" + "Pet Friendly" filter chips
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Appends two saved-filter presets to the Campsites experience search tool. Both
-- target the campgrounds layer (pois_camping) and use the Google-enriched amenity
-- fields (google_wheelchair / google_allows_dogs, set to 'Yes' only when true), so
-- an `exists` condition == the amenity is present. Idempotent: skipped if the
-- "Accessible" chip already exists.
-- ============================================================

update experiences
set saved_filters = saved_filters || jsonb_build_array(
      jsonb_build_object('id', gen_random_uuid()::text, 'icon','fa-wheelchair','label','Accessible','match','all','target','pois_camping',
        'conditions', jsonb_build_array(jsonb_build_object('op','exists','field','google_wheelchair','value',''))),
      jsonb_build_object('id', gen_random_uuid()::text, 'icon','fa-dog','label','Pet Friendly','match','all','target','pois_camping',
        'conditions', jsonb_build_array(jsonb_build_object('op','exists','field','google_allows_dogs','value','')))
    ),
    updated_at = now()
where slug = 'campsites'
  and not (saved_filters @> '[{"label":"Accessible"}]'::jsonb);
