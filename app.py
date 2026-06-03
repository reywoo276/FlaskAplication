from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:1234@localhost:5432/library_db"
)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


# ──────────────────────────── HOME ────────────────────────────

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.name, a.country, COUNT(b.id) AS book_count
        FROM authors a
        LEFT JOIN books b ON b.author_id = a.id
        GROUP BY a.id, a.name, a.country
        ORDER BY a.name
    """)
    authors = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS total FROM books")
    stats = cur.fetchone()
    cur.close(); conn.close()
    return render_template("index.html", authors=authors, stats=stats)


# ──────────────────────────── AUTHORS ────────────────────────────

@app.route("/authors/new", methods=["GET", "POST"])
def author_new():
    if request.method == "POST":
        name    = request.form["name"].strip()
        country = request.form["country"].strip()
        bio     = request.form["bio"].strip()
        if not name:
            flash("Ім'я автора обов'язкове", "error")
            return render_template("author_form.html", author=None)
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO authors (name, country, bio) VALUES (%s, %s, %s) RETURNING id",
            (name, country, bio)
        )
        conn.commit(); cur.close(); conn.close()
        flash(f"Автора «{name}» додано", "success")
        return redirect(url_for("index"))
    return render_template("author_form.html", author=None)


@app.route("/authors/<int:author_id>")
def author_detail(author_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM authors WHERE id = %s", (author_id,))
    author = cur.fetchone()
    if not author:
        flash("Автора не знайдено", "error")
        return redirect(url_for("index"))
    cur.execute(
        "SELECT * FROM books WHERE author_id = %s ORDER BY year DESC",
        (author_id,)
    )
    books = cur.fetchall()
    cur.close(); conn.close()
    return render_template("author_detail.html", author=author, books=books)


@app.route("/authors/<int:author_id>/edit", methods=["GET", "POST"])
def author_edit(author_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM authors WHERE id = %s", (author_id,))
    author = cur.fetchone()
    if not author:
        flash("Автора не знайдено", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        name    = request.form["name"].strip()
        country = request.form["country"].strip()
        bio     = request.form["bio"].strip()
        if not name:
            flash("Ім'я автора обов'язкове", "error")
            return render_template("author_form.html", author=author)
        cur.execute(
            "UPDATE authors SET name=%s, country=%s, bio=%s WHERE id=%s",
            (name, country, bio, author_id)
        )
        conn.commit(); cur.close(); conn.close()
        flash(f"Автора «{name}» оновлено", "success")
        return redirect(url_for("author_detail", author_id=author_id))
    cur.close(); conn.close()
    return render_template("author_form.html", author=author)


@app.route("/authors/<int:author_id>/delete", methods=["POST"])
def author_delete(author_id):
    """
    ТРАНЗАКЦІЯ: видаляємо всі книги автора, потім самого автора.
    Якщо щось піде не так — виконується rollback.
    """
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT name FROM authors WHERE id = %s", (author_id,))
        author = cur.fetchone()
        if not author:
            flash("Автора не знайдено", "error")
            return redirect(url_for("index"))
        # ── початок транзакції ──
        cur.execute("DELETE FROM books   WHERE author_id = %s", (author_id,))
        cur.execute("DELETE FROM authors WHERE id        = %s", (author_id,))
        conn.commit()   # commit, якщо обидві операції успішні
        flash(f"Автора «{author['name']}» та всі його книги видалено", "success")
    except Exception as e:
        conn.rollback()  # rollback у разі будь-якої помилки
        flash(f"Помилка при видаленні: {e}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("index"))


# ──────────────────────────── BOOKS ────────────────────────────

@app.route("/books")
def books_list():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT b.*, a.name AS author_name
        FROM books b
        JOIN authors a ON a.id = b.author_id
        ORDER BY b.created_at DESC
    """)
    books = cur.fetchall()
    cur.close(); conn.close()
    return render_template("books_list.html", books=books)


@app.route("/books/<int:book_id>")
def book_detail(book_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT b.*, a.name AS author_name, a.id AS author_id
        FROM books b JOIN authors a ON a.id = b.author_id
        WHERE b.id = %s
    """, (book_id,))
    book = cur.fetchone()
    if not book:
        flash("Книгу не знайдено", "error")
        return redirect(url_for("books_list"))
    # audit log для цієї книги
    cur.execute(
        "SELECT * FROM audit_log WHERE record_id=%s AND table_name='books' ORDER BY created_at DESC LIMIT 10",
        (book_id,)
    )
    logs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("book_detail.html", book=book, logs=logs)


@app.route("/books/new", methods=["GET", "POST"])
def book_new():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT id, name FROM authors ORDER BY name")
    authors = cur.fetchall()
    if request.method == "POST":
        title     = request.form["title"].strip()
        author_id = request.form["author_id"]
        year      = request.form["year"] or None
        genre     = request.form["genre"].strip()
        descr     = request.form["description"].strip()
        if not title or not author_id:
            flash("Назва та автор обов'язкові", "error")
            return render_template("book_form.html", book=None, authors=authors)
        # Використовуємо збережену процедуру add_book()
        cur.execute(
            "SELECT add_book(%s, %s, %s, %s, %s) AS new_id",
            (title, int(author_id), year, genre, descr)
        )
        new_id = cur.fetchone()["new_id"]
        conn.commit(); cur.close(); conn.close()
        flash(f"Книгу «{title}» додано", "success")
        return redirect(url_for("book_detail", book_id=new_id))
    cur.close(); conn.close()
    return render_template("book_form.html", book=None, authors=authors)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def book_edit(book_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM books WHERE id = %s", (book_id,))
    book = cur.fetchone()
    if not book:
        flash("Книгу не знайдено", "error")
        return redirect(url_for("books_list"))
    cur.execute("SELECT id, name FROM authors ORDER BY name")
    authors = cur.fetchall()
    if request.method == "POST":
        title     = request.form["title"].strip()
        author_id = request.form["author_id"]
        year      = request.form["year"] or None
        genre     = request.form["genre"].strip()
        descr     = request.form["description"].strip()
        if not title or not author_id:
            flash("Назва та автор обов'язкові", "error")
            return render_template("book_form.html", book=book, authors=authors)
        cur.execute("""
            UPDATE books
            SET title=%s, author_id=%s, year=%s, genre=%s, description=%s
            WHERE id=%s
        """, (title, int(author_id), year, genre, descr, book_id))
        conn.commit(); cur.close(); conn.close()
        flash(f"Книгу «{title}» оновлено", "success")
        return redirect(url_for("book_detail", book_id=book_id))
    cur.close(); conn.close()
    return render_template("book_form.html", book=book, authors=authors)


@app.route("/books/<int:book_id>/delete", methods=["POST"])
def book_delete(book_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT title FROM books WHERE id = %s", (book_id,))
    book = cur.fetchone()
    if book:
        cur.execute("DELETE FROM books WHERE id = %s", (book_id,))
        conn.commit()
        flash(f"Книгу «{book['title']}» видалено", "success")
    cur.close(); conn.close()
    return redirect(url_for("books_list"))


# ──────────────────────────── AUDIT LOG ────────────────────────────

@app.route("/audit")
def audit_log():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 50")
    logs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("audit_log.html", logs=logs)


if __name__ == "__main__":
    app.run(debug=True)
