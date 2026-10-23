-- Applied at every startup; idempotent. No migrations: to change it, drop the volume and re-seed.
CREATE TABLE IF NOT EXISTS route (
    route_id        text PRIMARY KEY,
    color           text NOT NULL,
    direction       text NOT NULL,
    name            text NOT NULL,
    line            jsonb NOT NULL,
    source          text NOT NULL,
    verified_on     date,
    osm_relation_id bigint
);

CREATE TABLE IF NOT EXISTS stop (
    stop_id     text PRIMARY KEY,
    name        text NOT NULL,
    lat         double precision NOT NULL,
    lng         double precision NOT NULL,
    osm_node_id bigint
);

CREATE TABLE IF NOT EXISTS route_stop (
    route_id text NOT NULL REFERENCES route (route_id),
    seq      integer NOT NULL,
    stop_id  text NOT NULL REFERENCES stop (stop_id),
    PRIMARY KEY (route_id, seq)
);

CREATE TABLE IF NOT EXISTS report (
    report_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    route_color text NOT NULL,
    message     text NOT NULL,
    lat         double precision,
    lng         double precision,
    status      text NOT NULL DEFAULT 'new',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS report_created_at_idx ON report (created_at DESC);
