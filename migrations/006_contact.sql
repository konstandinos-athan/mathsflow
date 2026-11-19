CREATE TABLE contact_requests (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
 category TEXT NOT NULL, message TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '',
 created_at REAL NOT NULL, replied_at REAL
);
CREATE INDEX contact_owner ON contact_requests(user_id,created_at);
