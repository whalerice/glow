CREATE TABLE IF NOT EXISTS person (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mdl_id text NOT NULL UNIQUE,
    name text,
    native_name text,
    first_name text,
    family_name text,
    stage_name text,
    also_known_as text[] NOT NULL DEFAULT '{}',
    nationality text,
    gender text,
    born_text text,
    image_url text,
    about text,
    mdl_url text,
    collect_status text NOT NULL,
    collect_error text,
    collected_at timestamptz,
    listed boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT person_mdl_id_digits CHECK (mdl_id ~ '^[0-9]+$'),
    CONSTRAINT person_collect_status_chk CHECK (collect_status IN ('registered', 'collected', 'failed'))
);

CREATE TABLE IF NOT EXISTS work (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mdl_id text UNIQUE,
    title text NOT NULL,
    kind text NOT NULL,
    year integer,
    episodes integer,
    rating numeric,
    mdl_url text,
    image_url text,
    synopsis text,
    native_title text,
    tags text[] NOT NULL DEFAULT '{}',
    detail_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT work_mdl_id_digits CHECK (mdl_id IS NULL OR mdl_id ~ '^[0-9]+$'),
    CONSTRAINT work_kind_chk CHECK (kind IN ('drama', 'movie', 'tv_show'))
);

ALTER TABLE person ADD COLUMN IF NOT EXISTS stage_name text;
ALTER TABLE person DROP COLUMN IF EXISTS age;
ALTER TABLE person ADD COLUMN IF NOT EXISTS listed boolean NOT NULL DEFAULT true;

ALTER TABLE work ADD COLUMN IF NOT EXISTS image_url text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS synopsis text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS native_title text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}';
ALTER TABLE work ADD COLUMN IF NOT EXISTS detail_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS work_title_year_kind_no_mdl
    ON work (title, year, kind) NULLS NOT DISTINCT
    WHERE mdl_id IS NULL;

CREATE TABLE IF NOT EXISTS person_work (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES person (id),
    work_id bigint NOT NULL REFERENCES work (id),
    role text NOT NULL DEFAULT '',
    character_name text,
    UNIQUE (person_id, work_id, role)
);

CREATE TABLE IF NOT EXISTS company (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mdl_id text UNIQUE,
    name text NOT NULL,
    name_key text NOT NULL,
    match_status text NOT NULL DEFAULT 'name_only',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT company_mdl_id_digits CHECK (mdl_id IS NULL OR mdl_id ~ '^[0-9]+$')
);

CREATE TABLE IF NOT EXISTS person_source (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES person (id),
    source text NOT NULL,
    external_key text NOT NULL,
    display_name text,
    payload jsonb NOT NULL,
    selected_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (person_id, source),
    UNIQUE (source, external_key)
);

CREATE TABLE IF NOT EXISTS person_company (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES person (id),
    company_id bigint NOT NULL REFERENCES company (id),
    relation text NOT NULL DEFAULT 'agency',
    start_year integer,
    end_year integer,
    period_text text,
    is_current boolean NOT NULL DEFAULT false
);

ALTER TABLE company ADD COLUMN IF NOT EXISTS sapphic_slug text;
CREATE UNIQUE INDEX IF NOT EXISTS company_sapphic_slug_key ON company (sapphic_slug) WHERE sapphic_slug IS NOT NULL;
ALTER TABLE person_company DROP CONSTRAINT IF EXISTS person_company_person_id_company_id_relation_key;
ALTER TABLE person_company ADD COLUMN IF NOT EXISTS start_year integer;
ALTER TABLE person_company ADD COLUMN IF NOT EXISTS end_year integer;
ALTER TABLE person_company ADD COLUMN IF NOT EXISTS period_text text;
ALTER TABLE person_company ADD COLUMN IF NOT EXISTS is_current boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS ship (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    name text NOT NULL,
    image_url text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS person_ship (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES person (id),
    ship_id bigint NOT NULL REFERENCES ship (id),
    UNIQUE (person_id, ship_id)
);

CREATE INDEX IF NOT EXISTS person_ship_ship_id_idx ON person_ship (ship_id);

CREATE TABLE IF NOT EXISTS episode (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_id bigint NOT NULL REFERENCES work (id),
    number integer NOT NULL,
    title text,
    air_date text,
    rating numeric,
    votes integer,
    image_url text,
    mdl_url text,
    summary text,
    UNIQUE (work_id, number)
);
