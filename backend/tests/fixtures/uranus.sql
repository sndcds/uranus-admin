-- Schema-only test snapshot from user-provided live backup uranus-26-09-14-030001.sql.
-- PostgreSQL 16.15, backup 2026-09-14. No production rows, owners, secrets or ACLs.
-- Only the nine queried tables, their enums, constraints and indexes are included.
-- Trigger functions are excluded: event text search depends on public functions
-- outside the schema-only backup. This is not a complete Uranus installation.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA uranus;
CREATE TYPE uranus.event_release_status AS ENUM (
    'inherited',
    'draft',
    'review',
    'released',
    'cancelled',
    'deferred',
    'rescheduled'
);
CREATE TYPE uranus.uranus_price_type AS ENUM (
    'not_specified',
    'regular_price',
    'free',
    'donation',
    'tiered_prices'
);
CREATE TYPE uranus.uranus_ticket_flag AS ENUM (
    'advance_ticket',
    'ticket_required',
    'on_site_ticket_sales',
    'registration_required',
    'reduced_price_available',
    'presale_fee_applies'
);
CREATE TABLE uranus."user" (
    uuid uuid NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_at timestamp without time zone,
    email character varying NOT NULL,
    password_hash text NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    username text,
    display_name character varying,
    first_name character varying,
    last_name character varying,
    locale character varying(2),
    theme character varying,
    activate_token text
);
CREATE TABLE uranus.organization (
    uuid uuid NOT NULL,
    created_by uuid,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_by uuid,
    modified_at timestamp without time zone,
    name text NOT NULL,
    description text,
    contact_email character varying(255),
    contact_phone character varying(50),
    web_link text,
    street character varying(255),
    house_number character varying(50),
    address_addition character varying,
    postal_code character varying(20),
    city character varying(100),
    country character varying(100),
    state character varying(2),
    holding_org_uuid uuid,
    legal_form text,
    nonprofit boolean,
    point public.geometry(Point,4326),
    api_import_token text,
    api_import_enabled boolean DEFAULT false,
    content_iso_639_1 character varying(2)
);
CREATE TABLE uranus.venue (
    uuid uuid NOT NULL,
    created_by uuid,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_by uuid,
    modified_at timestamp without time zone,
    org_uuid uuid NOT NULL,
    type text,
    name character varying(255) NOT NULL,
    description text,
    summary text,
    contact_email character varying,
    contact_phone character varying,
    web_link text,
    street character varying(255),
    house_number character varying(50),
    postal_code character varying(20),
    city character varying(100),
    country character(3),
    state character varying(2),
    point public.geometry(Point,4326),
    opened_at date,
    closed_at date,
    ticket_info text,
    ticket_link text,
    opening_hours text,
    accessibility_flags bigint,
    accessibility_summary text,
    content_iso_639_1 character varying(2),
    slug text,
    scope text DEFAULT 'standard'::text NOT NULL,
    osm_id bigint,
    building public.geometry(Geometry,4326),
    wikidata text,
    wikipedia text,
    CONSTRAINT venue_country_check CHECK ((char_length((country)::text) = 3)),
    CONSTRAINT venue_scope_check CHECK ((scope = ANY (ARRAY['organization'::text, 'shared'::text]))),
    CONSTRAINT venue_slug_format_check CHECK (((slug IS NULL) OR (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'::text)))
);
CREATE TABLE uranus.space (
    uuid uuid NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_at timestamp without time zone,
    venue_uuid uuid NOT NULL,
    name text NOT NULL,
    description text,
    web_link text,
    space_type text,
    building_level integer,
    area_sqm numeric(8,2),
    total_capacity integer,
    seating_capacity integer,
    accessibility_flags bigint,
    accessibility_summary text,
    created_by uuid,
    modified_by uuid,
    content_iso_639_1 character varying(2)
);
CREATE TABLE uranus.event (
    uuid uuid NOT NULL,
    external_id text,
    created_by uuid,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_by uuid,
    modified_at timestamp without time zone,
    release_date date,
    release_status uranus.event_release_status DEFAULT 'draft'::uranus.event_release_status NOT NULL,
    org_uuid uuid NOT NULL,
    venue_uuid uuid,
    space_uuid uuid,
    content_iso_639_1 character varying(2),
    title text NOT NULL,
    description text,
    subtitle text,
    summary text,
    categories integer[],
    languages text[],
    tags text[],
    occasion_type_id integer,
    min_age integer,
    max_age integer,
    participation_info text,
    max_attendees integer,
    visitor_info_flags bigint,
    meeting_point text,
    source_link text,
    online_link text,
    ticket_link text,
    ticket_flags uranus.uranus_ticket_flag[] DEFAULT '{}'::uranus.uranus_ticket_flag[] NOT NULL,
    price_type uranus.uranus_price_type DEFAULT 'not_specified'::uranus.uranus_price_type NOT NULL,
    currency character varying(8),
    min_price double precision,
    max_price double precision,
    custom text,
    style text,
    search_text text,
    registration_link text,
    registration_email text,
    registration_phone text,
    registration_deadline date,
    logo_mode integer DEFAULT 1 NOT NULL
);
CREATE TABLE uranus.event_date (
    uuid uuid NOT NULL,
    created_by uuid,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_by uuid,
    modified_at timestamp without time zone,
    release_status uranus.event_release_status DEFAULT 'inherited'::uranus.event_release_status NOT NULL,
    event_uuid uuid,
    venue_uuid uuid,
    space_uuid uuid,
    start_date date NOT NULL,
    start_time time without time zone,
    end_date date,
    end_time time without time zone,
    entry_time time without time zone,
    duration integer,
    all_day boolean,
    ticket_link text,
    availability_status_id integer,
    accessibility_info text,
    sold_out boolean,
    limited_tickets_remaining boolean,
    custom text
);
CREATE TABLE uranus.organization_member_link (
    org_uuid uuid NOT NULL,
    user_uuid uuid NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    modified_at timestamp without time zone,
    invited_at timestamp without time zone DEFAULT now(),
    invited_by_user_uuid uuid,
    accept_token text,
    has_joined boolean DEFAULT false NOT NULL
);
CREATE TABLE uranus.organization_partner_request (
    from_org_uuid uuid NOT NULL,
    to_org_uuid uuid NOT NULL,
    message text,
    from_user_uuid uuid NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL
);
CREATE TABLE uranus.pluto_image (
    uuid uuid NOT NULL,
    created_by uuid,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    modified_at timestamp without time zone,
    expiration_date date,
    file_name text NOT NULL,
    gen_file_name text,
    mime_type text,
    width integer,
    height integer,
    description text,
    alt_text text,
    exif jsonb,
    creator_name text,
    copyright text,
    license character varying(32),
    focus_x double precision,
    focus_y double precision,
    ai_label text,
    CONSTRAINT pluto_image_ai_label_check CHECK ((ai_label = ANY (ARRAY['none'::text, 'ai'::text, 'ai_generated'::text, 'ai_modified'::text])))
);
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.organization_member_link
    ADD CONSTRAINT organization_member_unique UNIQUE (org_uuid, user_uuid);
ALTER TABLE ONLY uranus.organization
    ADD CONSTRAINT organization_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.pluto_image
    ADD CONSTRAINT pluto_image_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.space
    ADD CONSTRAINT space_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.organization_partner_request
    ADD CONSTRAINT uq_org_partner_request UNIQUE (from_org_uuid, to_org_uuid);
ALTER TABLE ONLY uranus."user"
    ADD CONSTRAINT user_email_key UNIQUE (email);
ALTER TABLE ONLY uranus."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus."user"
    ADD CONSTRAINT user_user_name_key UNIQUE (username);
ALTER TABLE ONLY uranus.venue
    ADD CONSTRAINT venue_pkey PRIMARY KEY (uuid);
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_event_uuid_fkey FOREIGN KEY (event_uuid) REFERENCES uranus.event(uuid) ON DELETE CASCADE;
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_modified_by_fkey FOREIGN KEY (modified_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_space_uuid_fkey FOREIGN KEY (space_uuid) REFERENCES uranus.space(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event_date
    ADD CONSTRAINT event_date_venue_uuid_fkey FOREIGN KEY (venue_uuid) REFERENCES uranus.venue(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_modified_by_fkey FOREIGN KEY (modified_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_org_uuid_fkey FOREIGN KEY (org_uuid) REFERENCES uranus.organization(uuid) ON DELETE CASCADE;
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_space_uuid_fkey FOREIGN KEY (space_uuid) REFERENCES uranus.space(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.event
    ADD CONSTRAINT event_venue_uuid_fkey FOREIGN KEY (venue_uuid) REFERENCES uranus.venue(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.organization
    ADD CONSTRAINT organization_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.organization
    ADD CONSTRAINT organization_holding_org_uuid_fkey FOREIGN KEY (holding_org_uuid) REFERENCES uranus.organization(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.organization_member_link
    ADD CONSTRAINT organization_member_link_invited_by_user_uuid_fkey FOREIGN KEY (invited_by_user_uuid) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.organization_member_link
    ADD CONSTRAINT organization_member_link_org_uuid_fkey FOREIGN KEY (org_uuid) REFERENCES uranus.organization(uuid) ON DELETE CASCADE;
ALTER TABLE ONLY uranus.organization_member_link
    ADD CONSTRAINT organization_member_link_user_uuid_fkey FOREIGN KEY (user_uuid) REFERENCES uranus."user"(uuid) ON DELETE CASCADE;
ALTER TABLE ONLY uranus.organization
    ADD CONSTRAINT organization_modified_by_fkey FOREIGN KEY (modified_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.pluto_image
    ADD CONSTRAINT pluto_image_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.space
    ADD CONSTRAINT space_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.space
    ADD CONSTRAINT space_modified_by_fkey FOREIGN KEY (modified_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.space
    ADD CONSTRAINT space_venue_uuid_fkey FOREIGN KEY (venue_uuid) REFERENCES uranus.venue(uuid) ON DELETE CASCADE;
ALTER TABLE ONLY uranus.venue
    ADD CONSTRAINT venue_created_by_fkey FOREIGN KEY (created_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.venue
    ADD CONSTRAINT venue_modified_by_fkey FOREIGN KEY (modified_by) REFERENCES uranus."user"(uuid) ON DELETE SET NULL;
ALTER TABLE ONLY uranus.venue
    ADD CONSTRAINT venue_org_uuid_fkey FOREIGN KEY (org_uuid) REFERENCES uranus.organization(uuid) ON DELETE CASCADE;
CREATE INDEX idx_event_date_event_uuid ON uranus.event_date USING btree (event_uuid);
CREATE INDEX idx_event_date_venue_uuid ON uranus.event_date USING btree (venue_uuid);
CREATE INDEX idx_event_release_status ON uranus.event USING btree (release_status);
CREATE INDEX idx_event_venue_uuid ON uranus.event USING btree (venue_uuid);
CREATE INDEX idx_venue_point ON uranus.venue USING gist (point);
-- Additional source-only tables verified against Uranus dev 733c541 (2026-09-14).
CREATE TABLE uranus.event_link (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
 modified_at timestamp,
 event_uuid uuid NOT NULL REFERENCES uranus.event(uuid) ON DELETE CASCADE,
 type text, label varchar(255), url text NOT NULL
);
CREATE TABLE uranus.license (key text PRIMARY KEY, spdx_id text, url text);
CREATE TABLE uranus.pluto_image_link (
 pluto_image_uuid uuid REFERENCES uranus.pluto_image(uuid) ON DELETE CASCADE,
 context text NOT NULL, context_uuid uuid NOT NULL, identifier text NOT NULL,
 CONSTRAINT image_context_identifier_unique UNIQUE(context,context_uuid,identifier)
);
CREATE TABLE uranus.organization_access_grants (
 src_org_uuid uuid REFERENCES uranus.organization(uuid) ON DELETE CASCADE,
 dst_org_uuid uuid REFERENCES uranus.organization(uuid) ON DELETE CASCADE,
 permissions bigint DEFAULT 0,
 CONSTRAINT organization_access_grants_unique_pair UNIQUE(src_org_uuid,dst_org_uuid)
);

-- Event-content lookups verified at Uranus 0c2632e (2026-09-17).
CREATE TABLE uranus.event_category (
    category_id integer,
    iso_639_1 character varying(2),
    name text NOT NULL,
    schema_org_type text
);
CREATE TABLE uranus.event_type (
    type_id integer,
    iso_639_1 character varying(2),
    name text NOT NULL,
    schema_org_type text,
    CONSTRAINT event_type_pkey PRIMARY KEY (type_id, iso_639_1)
);
CREATE TABLE uranus.genre_type (
    name text NOT NULL,
    genre_id integer NOT NULL,
    type_id integer,
    iso_639_1 character varying(2)
);
CREATE TABLE uranus.event_type_link (
    event_uuid uuid NOT NULL REFERENCES uranus.event(uuid) ON DELETE CASCADE,
    type_id integer NOT NULL,
    genre_id integer NOT NULL DEFAULT 0,
    CONSTRAINT event_type_link_unique UNIQUE (event_uuid, type_id, genre_id)
);

-- Minimal vocabulary fixtures; current Uranus DDL audited at 15835d8.
CREATE TABLE uranus.language (
 code_iso_639_1 varchar(2) NOT NULL, name text NOT NULL, name_iso_639_1 varchar(2) NOT NULL
);
CREATE TABLE uranus.link_type (key text PRIMARY KEY);
