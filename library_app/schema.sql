-- ============================================================
--  Library DB — schema.sql
--  Містить: таблиці, тригер, збережену процедуру (функцію)
-- ============================================================

-- 1. Основні таблиці

CREATE TABLE IF NOT EXISTS authors (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    country    VARCHAR(100),
    bio        TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS books (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    year        SMALLINT,
    genre       VARCHAR(100),
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()   -- автоматично оновлюється тригером
);

-- 2. Таблиця для audit log (використовується тригером)

CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    table_name  VARCHAR(100),
    operation   VARCHAR(10),   -- INSERT / UPDATE / DELETE
    record_id   INTEGER,
    changed_by  TEXT DEFAULT current_user,
    created_at  TIMESTAMP DEFAULT NOW(),
    details     TEXT
);

-- ============================================================
--  ТРИГЕР: автоматично оновлює updated_at та пише в audit_log
--          при будь-якій зміні рядка в таблиці books
-- ============================================================

CREATE OR REPLACE FUNCTION trg_books_audit()
RETURNS TRIGGER AS $$
BEGIN
    -- Оновлюємо updated_at для UPDATE
    IF TG_OP = 'UPDATE' THEN
        NEW.updated_at := NOW();
    END IF;

    -- Пишемо запис у audit_log
    INSERT INTO audit_log (table_name, operation, record_id, details)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        COALESCE(NEW.id, OLD.id),
        CASE
            WHEN TG_OP = 'INSERT' THEN 'Додано: ' || NEW.title
            WHEN TG_OP = 'UPDATE' THEN 'Оновлено: ' || NEW.title
            WHEN TG_OP = 'DELETE' THEN 'Видалено: ' || OLD.title
        END
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS books_audit_trigger ON books;
CREATE TRIGGER books_audit_trigger
BEFORE INSERT OR UPDATE OR DELETE ON books
FOR EACH ROW EXECUTE FUNCTION trg_books_audit();

-- ============================================================
--  ЗБЕРЕЖЕНА ПРОЦЕДУРА (функція): add_book
--  Додає книгу і повертає її id.
--  Flask викликає: SELECT add_book(%s, %s, %s, %s, %s)
-- ============================================================

CREATE OR REPLACE FUNCTION add_book(
    p_title       VARCHAR,
    p_author_id   INTEGER,
    p_year        SMALLINT,
    p_genre       VARCHAR,
    p_description TEXT
)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    -- Перевірка: автор має існувати
    IF NOT EXISTS (SELECT 1 FROM authors WHERE id = p_author_id) THEN
        RAISE EXCEPTION 'Автор з id=% не існує', p_author_id;
    END IF;

    INSERT INTO books (title, author_id, year, genre, description)
    VALUES (p_title, p_author_id, p_year, p_genre, p_description)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
--  Тестові дані
-- ============================================================

INSERT INTO authors (name, country, bio) VALUES
    ('Ліна Костенко',  'Україна', 'Видатна українська поетеса, прозаїк і кіносценарист.'),
    ('Михайло Коцюбинський', 'Україна', 'Класик української літератури, майстер новели.'),
    ('Джордж Орвелл',  'Велика Британія', 'Англійський письменник і публіцист, автор антиутопій.')
ON CONFLICT DO NOTHING;

SELECT add_book('Маруся Чурай',           1, 1979, 'Роман у віршах', 'Історичний роман у віршах про легендарну полтавську співачку.');
SELECT add_book('Берестечко',             1, 1999, 'Поезія',         'Поема про битву під Берестечком 1651 року.');
SELECT add_book('Тіні забутих предків',   2, 1911, 'Повість',        'Поетична повість про кохання і трагедію в Карпатах.');
SELECT add_book('Fata Morgana',           2, 1903, 'Новела',         'Новела про соціальні суперечності на селі.');
SELECT add_book('1984',                   3, 1949, 'Антиутопія',     'Класична антиутопія про тоталітарне суспільство.');
SELECT add_book('Скотний двір',           3, 1945, 'Сатира',         'Алегорична повість-казка про революцію і владу.');
