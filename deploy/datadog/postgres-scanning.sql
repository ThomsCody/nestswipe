-- Run as the database owner in the application database only.
-- Explicit grants cover existing application tables selected for scanning.
-- New tables require a separate grant; no write privileges are granted.
-- users includes OAuth refresh tokens and API keys; access explicitly approved.
BEGIN;
SET LOCAL lock_timeout = '3s';
GRANT USAGE ON SCHEMA public TO datadog;
GRANT SELECT ON TABLE
    public.comments,
    public.favorites,
    public.household_invites,
    public.households,
    public.listing_photos,
    public.listings,
    public.maintenance_presence,
    public.notifications,
    public.parse_attempts,
    public.price_history,
    public.swipe_actions,
    public.users
TO datadog;
COMMIT;
