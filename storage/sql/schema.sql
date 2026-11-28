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
ALTER TABLE person ADD COLUMN IF NOT EXISTS socials jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE person ADD COLUMN IF NOT EXISTS deleted smallint NOT NULL DEFAULT 0;
ALTER TABLE person DROP CONSTRAINT IF EXISTS person_deleted_chk;
ALTER TABLE person ADD CONSTRAINT person_deleted_chk CHECK (deleted IN (0, 1, 2));
ALTER TABLE person DROP COLUMN IF EXISTS age;

ALTER TABLE work ADD COLUMN IF NOT EXISTS image_url text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS synopsis text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS native_title text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}';
ALTER TABLE work ADD COLUMN IF NOT EXISTS detail_at timestamptz;
ALTER TABLE work ADD COLUMN IF NOT EXISTS networks_at timestamptz;
ALTER TABLE work ADD COLUMN IF NOT EXISTS aired text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS aired_on text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS content_rating text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS air_at timestamptz;
ALTER TABLE work DROP COLUMN IF EXISTS watch_at;
ALTER TABLE work ADD COLUMN IF NOT EXISTS tmdb_id bigint;
ALTER TABLE work ADD COLUMN IF NOT EXISTS tmdb_kind text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS keywords text[];
ALTER TABLE work ADD COLUMN IF NOT EXISTS ko_title text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS homepage text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS teaser_url text;
CREATE TABLE IF NOT EXISTS work_status (
    key text PRIMARY KEY,
    name text NOT NULL
);
INSERT INTO work_status (key, name) VALUES
    ('Returning Series', '방영중'),
    ('Planned', '예정'),
    ('In Production', '제작중'),
    ('Post Production', '후반작업'),
    ('Pilot', '파일럿'),
    ('Ended', '종영'),
    ('Canceled', '취소'),
    ('Released', '공개'),
    ('Rumored', '루머')
ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name;
ALTER TABLE work ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS poster_url text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS backdrop_url text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS backdrop_urls text[] NOT NULL DEFAULT '{}';
ALTER TABLE work ADD COLUMN IF NOT EXISTS next_season integer;
ALTER TABLE work ADD COLUMN IF NOT EXISTS next_episode integer;
ALTER TABLE work ADD COLUMN IF NOT EXISTS next_air_date text;
ALTER TABLE work ADD COLUMN IF NOT EXISTS deleted smallint NOT NULL DEFAULT 0;
ALTER TABLE work DROP CONSTRAINT IF EXISTS work_deleted_chk;
ALTER TABLE work ADD CONSTRAINT work_deleted_chk CHECK (deleted IN (0, 1, 2));
CREATE TABLE IF NOT EXISTS queer (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);
INSERT INTO queer (name)
VALUES ('BL'), ('GL'), ('LGBTQ')
ON CONFLICT (name) DO NOTHING;
ALTER TABLE work DROP CONSTRAINT IF EXISTS work_pair_chk;
ALTER TABLE work DROP COLUMN IF EXISTS pair;
ALTER TABLE work ADD COLUMN IF NOT EXISTS queer bigint REFERENCES queer (id);
UPDATE work
SET queer = (
  SELECT id FROM queer
  WHERE name = CASE
    WHEN EXISTS (SELECT 1 FROM unnest(tags) AS tag WHERE tag ILIKE '%lesbian%')
     AND ('Gay Romance' = ANY (tags) OR 'Gay Male Lead' = ANY (tags)) THEN 'LGBTQ'
    WHEN EXISTS (SELECT 1 FROM unnest(tags) AS tag WHERE tag ILIKE '%lesbian%') THEN 'GL'
    WHEN 'Gay Romance' = ANY (tags) OR 'Gay Male Lead' = ANY (tags) THEN 'BL'
  END
)
WHERE queer IS NULL
  AND (
    EXISTS (SELECT 1 FROM unnest(tags) AS tag WHERE tag ILIKE '%lesbian%')
    OR 'Gay Romance' = ANY (tags)
    OR 'Gay Male Lead' = ANY (tags)
  );
UPDATE work
SET queer = (
  SELECT id FROM queer
  WHERE name = CASE
    WHEN 'Gay Romance' = ANY (tags) OR 'Gay Male Lead' = ANY (tags) THEN 'LGBTQ'
    ELSE 'GL'
  END
)
WHERE EXISTS (
  SELECT 1 FROM unnest(tags) AS tag WHERE tag ILIKE '%lesbian%'
);
UPDATE work
SET queer = (
  SELECT id FROM queer
  WHERE name = CASE
    WHEN 'Gay Romance' = ANY (tags) OR 'Gay Male Lead' = ANY (tags) THEN 'LGBTQ'
    ELSE 'GL'
  END
)
WHERE EXISTS (
  SELECT 1
  FROM unnest(keywords) AS keyword
  WHERE replace(replace(lower(keyword), '’', ''''), '‘', '''')
        IN ('girls'' love (gl)', 'girls'' love', 'gl')
);
ALTER TABLE work DROP COLUMN IF EXISTS pair_id;
DROP TABLE IF EXISTS pair;

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
    name text NOT NULL,
    name_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE company DROP COLUMN IF EXISTS mdl_id;
ALTER TABLE company DROP COLUMN IF EXISTS match_status;
ALTER TABLE company DROP COLUMN IF EXISTS tmdb_network;

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
ALTER TABLE company ADD COLUMN IF NOT EXISTS sapphic jsonb;
ALTER TABLE company ADD COLUMN IF NOT EXISTS logo_url text;
ALTER TABLE company ADD COLUMN IF NOT EXISTS homepage text;
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

CREATE TABLE IF NOT EXISTS org_type (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);

INSERT INTO org_type (name)
VALUES ('제작사'), ('배급사'), ('방송사'), ('엔터테이먼트')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS company_type (
    company_id bigint NOT NULL REFERENCES company (id),
    org_type_id bigint NOT NULL REFERENCES org_type (id),
    PRIMARY KEY (company_id, org_type_id)
);

DELETE FROM company_type
WHERE org_type_id IN (SELECT id FROM org_type WHERE name = 'OTT');

DELETE FROM org_type WHERE name = 'OTT';

CREATE TABLE IF NOT EXISTS work_company (
    work_id bigint NOT NULL REFERENCES work (id),
    company_id bigint NOT NULL REFERENCES company (id),
    PRIMARY KEY (work_id, company_id)
);

CREATE TABLE IF NOT EXISTS work_watch (
    work_id bigint NOT NULL REFERENCES work (id),
    name text NOT NULL,
    offer text NOT NULL,
    url text,
    PRIMARY KEY (work_id, name, offer)
);

CREATE TABLE IF NOT EXISTS work_provider (
    work_id bigint NOT NULL REFERENCES work (id),
    country text NOT NULL,
    name text NOT NULL,
    offer text NOT NULL,
    url text,
    PRIMARY KEY (work_id, country, name, offer)
);

ALTER TABLE work_provider ADD COLUMN IF NOT EXISTS url text;

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

CREATE TABLE IF NOT EXISTS role (
    code text PRIMARY KEY,
    name text NOT NULL
);

INSERT INTO role (code, name) VALUES
    ('a', '배우'),
    ('d', '감독'),
    ('w', '작가')
ON CONFLICT (code) DO NOTHING;

UPDATE work AS w
SET episodes = counted.n
FROM (
    SELECT work_id, count(*)::integer AS n
    FROM episode
    GROUP BY work_id
) AS counted
WHERE w.id = counted.work_id
  AND (w.episodes IS NULL OR w.episodes = 0)
  AND counted.n > 0;

CREATE TABLE IF NOT EXISTS person_role (
    person_id bigint NOT NULL REFERENCES person (id),
    role_code text NOT NULL REFERENCES role (code),
    PRIMARY KEY (person_id, role_code)
);
