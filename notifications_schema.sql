-- Schema pro Notifikační systém (Push & E-mail)

-- Tabulka pro E-mailové odběry
CREATE TABLE IF NOT EXISTS email_subscriptions (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    categories JSONB DEFAULT '[]'::jsonb, -- Seznam odebíraných kategorií, prázdné = všechny
    severities JSONB DEFAULT '[]'::jsonb, -- Seznam odebíraných závažností (Běžný, Vyžaduje pozornost, Závažné)
    is_active BOOLEAN DEFAULT true,
    unsubscribe_token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabulka pro Web Push odběry (do prohlížeče)
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id SERIAL PRIMARY KEY,
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
