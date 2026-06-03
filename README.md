# LibraryDB — Flask + PostgreSQL

Міні-застосунок для ведення каталогу книг та авторів.  
Реалізує всі вимоги на **максимальний бал**: транзакцію, збережену процедуру та тригер.

---

## Структура БД

| Таблиця     | Опис |
|-------------|------|
| `authors`   | Автори книг |
| `books`     | Книги (зовнішній ключ → `authors`) |
| `audit_log` | Журнал змін (заповнюється тригером) |

---

## Реалізовані функції PostgreSQL

### 1. Тригер — `books_audit_trigger`

**Файл:** `schema.sql`  
**Функція:** `trg_books_audit()`

Спрацьовує на `BEFORE INSERT OR UPDATE OR DELETE` в таблиці `books`:
- При `UPDATE` — автоматично встановлює `updated_at = NOW()`
- При будь-якій операції — записує подію у таблицю `audit_log` (час, тип операції, id запису, деталі)

Результат видно на сторінці `/audit` та на сторінці кожної книги.

---

### 2. Збережена процедура (функція) — `add_book()`

**Файл:** `schema.sql`  
**Виклик у Flask:** `SELECT add_book(%s, %s, %s, %s, %s)`

PostgreSQL-функція на мові `plpgsql`, яка:
1. Перевіряє існування автора (`RAISE EXCEPTION` якщо не знайдено)
2. Вставляє запис у `books` та повертає `id` нового рядка

Використовується при створенні нової книги (`POST /books/new`).

---

### 3. Транзакція з rollback — видалення автора

**Файл:** `app.py`, функція `author_delete()`

При видаленні автора виконуються дві пов'язані операції в одній транзакції:
```python
cur.execute("DELETE FROM books   WHERE author_id = %s", (author_id,))
cur.execute("DELETE FROM authors WHERE id        = %s", (author_id,))
conn.commit()   # якщо обидві успішні
```
Якщо будь-яка операція викидає виняток — викликається `conn.rollback()`, і БД залишається в консистентному стані.

---

## Як запустити

### 1. Клонуйте / розпакуйте проєкт

```bash
cd library_app
```

### 2. Створіть віртуальне середовище та встановіть залежності

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Налаштуйте PostgreSQL

```bash
psql -U postgres -c "CREATE DATABASE library_db;"
```

### 4. Застосуйте схему БД

```bash
psql -U postgres -d library_db -f schema.sql
```

Це створить таблиці, тригер, функцію та завантажить тестові дані.

### 5. Налаштуйте змінні середовища

```bash
cp .env.example .env
# відредагуйте .env — вкажіть DATABASE_URL та SECRET_KEY
```

### 6. Запустіть застосунок

```bash
flask run
# або
python app.py
```

Застосунок доступний за адресою: **http://localhost:5000**

---

## Функціонал застосунку

| Маршрут | Опис |
|---------|------|
| `GET /` | Список авторів з кількістю книг |
| `GET /authors/<id>` | Деталі автора + список книг |
| `GET/POST /authors/new` | Форма створення автора |
| `GET/POST /authors/<id>/edit` | Форма редагування автора |
| `POST /authors/<id>/delete` | Видалення автора (транзакція) |
| `GET /books` | Список всіх книг |
| `GET /books/<id>` | Деталі книги + журнал змін |
| `GET/POST /books/new` | Форма створення (через `add_book()`) |
| `GET/POST /books/<id>/edit` | Форма редагування книги |
| `POST /books/<id>/delete` | Видалення книги |
| `GET /audit` | Повний журнал аудиту |

---

## Технології

- **Backend:** Python 3.11+, Flask 3.0
- **Database:** PostgreSQL 14+, psycopg2
- **Frontend:** Jinja2, CSS (без фреймворків)
