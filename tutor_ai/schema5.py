"""Additive schema 5. Historical schema-4 aggregates remain unchanged."""

SQL = """
CREATE TABLE learning_source_versions(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, hash TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL);
CREATE INDEX source_owner ON learning_source_versions(student,kind);
CREATE INDEX source_hash ON learning_source_versions(hash);
CREATE TABLE learning_source_segments(
 id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES learning_source_versions(id) ON DELETE CASCADE,
 body TEXT NOT NULL);
CREATE TABLE learning_source_matches(
 id TEXT PRIMARY KEY, book TEXT NOT NULL REFERENCES learning_source_versions(id) ON DELETE CASCADE,
 method TEXT NOT NULL REFERENCES learning_source_versions(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(book,method,revision));
CREATE TABLE learning_outline_nodes(
 id TEXT PRIMARY KEY, curriculum TEXT NOT NULL REFERENCES learning_curricula(id) ON DELETE CASCADE,
 parent TEXT REFERENCES learning_outline_nodes(id) ON DELETE CASCADE,
 topic TEXT REFERENCES learning_topics(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, kind TEXT NOT NULL, optional INTEGER CHECK(optional IN (0,1)),
 source TEXT REFERENCES learning_source_versions(id), body TEXT NOT NULL);
CREATE UNIQUE INDEX outline_roots ON learning_outline_nodes(curriculum,position) WHERE parent IS NULL;
CREATE UNIQUE INDEX outline_children ON learning_outline_nodes(curriculum,parent,position) WHERE parent IS NOT NULL;
CREATE TABLE learning_skill_provenance(
 skill TEXT PRIMARY KEY REFERENCES learning_skills(id) ON DELETE CASCADE,
 source TEXT REFERENCES learning_source_versions(id),
 match TEXT REFERENCES learning_source_matches(id), origin TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_preparations(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 curriculum TEXT NOT NULL REFERENCES learning_curricula(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_preparation_batches(
 id TEXT PRIMARY KEY, preparation TEXT NOT NULL REFERENCES learning_preparations(id) ON DELETE CASCADE,
 job TEXT REFERENCES learning_jobs(id) ON DELETE SET NULL,
 position INTEGER NOT NULL, repair INTEGER NOT NULL, body TEXT NOT NULL,
 UNIQUE(preparation,position,repair));
CREATE TABLE learning_job_events(
 id TEXT PRIMARY KEY, job TEXT NOT NULL REFERENCES learning_jobs(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(job,position));
CREATE TABLE learning_artifacts(
 id TEXT PRIMARY KEY, job TEXT NOT NULL REFERENCES learning_jobs(id) ON DELETE CASCADE,
 body TEXT NOT NULL);
"""


def install(db):
    for statement in SQL.split(";"):
        if statement.strip():
            db.execute(statement)
    db.execute("INSERT INTO learning_outline_nodes SELECT id,curriculum,NULL,id,position,'topic',NULL,NULL,"
               "'{\"origin\":\"legacy_unknown\"}' FROM learning_topics")
    db.execute("INSERT INTO learning_skill_provenance SELECT id,NULL,NULL,'legacy_unknown','{}' FROM learning_skills")
    db.execute("INSERT INTO schema_migrations VALUES(5)")
