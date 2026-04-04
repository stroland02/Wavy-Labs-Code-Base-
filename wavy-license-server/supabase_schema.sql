-- ============================================================
-- Wavy Labs — Supabase profiles schema
-- Apply in Supabase Dashboard > SQL Editor, or via CLI:
--   supabase db push  (if using local dev)
-- ============================================================

-- Profiles table — one row per Supabase auth.users record.
-- The license server writes tier/stripe fields via service_role key.
-- Row-level security lets users read their own row only.

CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID        REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email           TEXT        NOT NULL,
    tier            TEXT        NOT NULL DEFAULT 'free'
                                CHECK (tier IN ('free', 'pro', 'studio')),
    stripe_customer TEXT,
    stripe_sub_id   TEXT,
    sub_status      TEXT        NOT NULL DEFAULT 'none',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS profiles_email_idx       ON public.profiles (email);
CREATE INDEX IF NOT EXISTS profiles_stripe_cust_idx ON public.profiles (stripe_customer);
CREATE INDEX IF NOT EXISTS profiles_stripe_sub_idx  ON public.profiles (stripe_sub_id);

-- Row-level security
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Users can view only their own profile
CREATE POLICY "Users can view own profile"
    ON public.profiles
    FOR SELECT
    USING (auth.uid() = id);

-- No client-side INSERT/UPDATE — the license server uses service_role

-- ── Trigger: auto-create profile on signup ─────────────────────────────────

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, email)
    VALUES (new.id, new.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- ── Trigger: auto-update updated_at ────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.handle_profile_updated()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    new.updated_at = now();
    RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_profile_updated ON public.profiles;
CREATE TRIGGER on_profile_updated
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE PROCEDURE public.handle_profile_updated();
