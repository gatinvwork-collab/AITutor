"""Remove later structures when constructing actual historical test fixtures."""


def before_v4(db):
    names = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'learning_%' ORDER BY rowid DESC"
        )
    ]
    for name in names:
        db.execute("DROP TABLE " + name)
    db.execute("DELETE FROM schema_migrations WHERE version>=4")
