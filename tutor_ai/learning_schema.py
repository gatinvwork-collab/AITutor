"""Schema 4. Personal aggregates have a real owner FK; immutable revisions are rows."""

SQL = """
CREATE TABLE learning_assignments(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 subject TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(student,subject,revision));
CREATE TABLE learning_curricula(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 subject TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
 body TEXT NOT NULL, UNIQUE(student,subject,revision));
CREATE TABLE learning_topics(
 id TEXT PRIMARY KEY, curriculum TEXT NOT NULL REFERENCES learning_curricula(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, title TEXT NOT NULL, UNIQUE(curriculum,position));
CREATE TABLE learning_skills(
 id TEXT PRIMARY KEY, topic TEXT NOT NULL REFERENCES learning_topics(id) ON DELETE CASCADE,
 title TEXT NOT NULL, UNIQUE(topic,title));
CREATE TABLE learning_state(
 student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject TEXT NOT NULL,
 revision INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(student,subject));
CREATE TABLE learning_requests(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_collections(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 curriculum TEXT NOT NULL REFERENCES learning_curricula(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_questions(
 id TEXT PRIMARY KEY, collection TEXT NOT NULL REFERENCES learning_collections(id) ON DELETE CASCADE,
 fingerprint TEXT NOT NULL, starred INTEGER NOT NULL CHECK(starred IN (0,1)), body TEXT NOT NULL,
 UNIQUE(collection,fingerprint));
CREATE TABLE learning_criteria(
 id TEXT PRIMARY KEY, question TEXT NOT NULL REFERENCES learning_questions(id) ON DELETE CASCADE,
 topic TEXT NOT NULL REFERENCES learning_topics(id) ON DELETE CASCADE, body TEXT NOT NULL);
CREATE TABLE learning_criterion_skills(
 criterion TEXT NOT NULL REFERENCES learning_criteria(id) ON DELETE CASCADE,
 skill TEXT NOT NULL REFERENCES learning_skills(id) ON DELETE CASCADE, PRIMARY KEY(criterion,skill));
CREATE TABLE learning_attempts(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 collection TEXT NOT NULL REFERENCES learning_collections(id) ON DELETE CASCADE,
 purpose TEXT NOT NULL CHECK(purpose IN ('topic_confirmation','subject_screening')),
 revision INTEGER NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_slots(
 id TEXT PRIMARY KEY, attempt TEXT NOT NULL REFERENCES learning_attempts(id) ON DELETE CASCADE,
 question TEXT NOT NULL REFERENCES learning_questions(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, skipped INTEGER NOT NULL DEFAULT 0,
 UNIQUE(attempt,position), UNIQUE(attempt,question));
CREATE TABLE learning_answers(
 id TEXT PRIMARY KEY, slot TEXT NOT NULL REFERENCES learning_slots(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, independent INTEGER NOT NULL, body TEXT NOT NULL,
 UNIQUE(slot,revision));
CREATE TABLE learning_observations(
 id TEXT PRIMARY KEY, answer TEXT NOT NULL REFERENCES learning_answers(id) ON DELETE CASCADE,
 criterion TEXT NOT NULL REFERENCES learning_criteria(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, code TEXT NOT NULL CHECK(code IN ('C','W','U')),
 method TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(answer,criterion,revision));
CREATE TABLE learning_decisions(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 actor TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
 request_id TEXT REFERENCES learning_requests(id) ON DELETE CASCADE,
 answer_id TEXT REFERENCES learning_answers(id) ON DELETE CASCADE,
 CHECK((request_id IS NOT NULL AND answer_id IS NULL) OR (request_id IS NULL AND answer_id IS NOT NULL)));
CREATE TABLE learning_signals(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 skill TEXT NOT NULL REFERENCES learning_skills(id) ON DELETE CASCADE,
 observation TEXT NOT NULL REFERENCES learning_observations(id) ON DELETE CASCADE,
 active INTEGER NOT NULL, UNIQUE(student,observation,skill));
CREATE TABLE learning_confirmations(
 id TEXT PRIMARY KEY, attempt TEXT NOT NULL REFERENCES learning_attempts(id) ON DELETE CASCADE,
 topic TEXT NOT NULL REFERENCES learning_topics(id) ON DELETE CASCADE,
 result_revision INTEGER NOT NULL, active INTEGER NOT NULL, UNIQUE(attempt,topic,result_revision));
CREATE TABLE learning_success(
 student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 question TEXT NOT NULL REFERENCES learning_questions(id) ON DELETE CASCADE,
 attempt TEXT NOT NULL REFERENCES learning_attempts(id) ON DELETE CASCADE,
 PRIMARY KEY(student,question,attempt));
CREATE TABLE learning_operations(
 student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, actor TEXT NOT NULL,
 operation TEXT NOT NULL, fingerprint TEXT NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(student,actor,operation));
CREATE TABLE learning_jobs(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 context TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE learning_work_revisions(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 work TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(work,revision));
CREATE TABLE learning_originals(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 work_revision TEXT NOT NULL REFERENCES learning_work_revisions(id) ON DELETE CASCADE,
 record_kind TEXT NOT NULL CHECK(record_kind='homework'), original TEXT NOT NULL,
 FOREIGN KEY(record_kind,original) REFERENCES records(kind,id) ON DELETE CASCADE);
CREATE TABLE learning_calls(
 id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 work TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX learning_attempt_owner ON learning_attempts(student,status);
CREATE INDEX learning_request_owner ON learning_requests(student,status);
CREATE INDEX learning_job_owner ON learning_jobs(student,status);
CREATE INDEX learning_signal_owner ON learning_signals(student,active);
"""


def install(db):
    # executescript commits implicitly: migrations must use execute per statement.
    for statement in SQL.split(";"):
        if statement.strip():
            db.execute(statement)
