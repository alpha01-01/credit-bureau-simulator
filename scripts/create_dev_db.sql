-- One-time local setup: creates the SimB development role and database.
-- Run as a PostgreSQL superuser, e.g.:
--   psql -h localhost -U postgres -f scripts/create_dev_db.sql
-- The password matches .env.example and is for LOCAL DEVELOPMENT ONLY.
-- CREATEDB lets the test runner create and drop its own test database.

CREATE ROLE simb WITH LOGIN PASSWORD 'simb_local_dev' CREATEDB;
CREATE DATABASE simb OWNER simb ENCODING 'UTF8';
