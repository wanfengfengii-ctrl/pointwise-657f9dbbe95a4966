from contextlib import contextmanager
import sqlite3
from archive.schema import SCHEMA_VERSION, SCHEMA_STATEMENTS, CorruptArtifact
from archive.codec import artifact_digest


class Store:
    def __init__(self, path):
        self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        try:
            self.initialize()
        except BaseException:
            self.connection.close()
            raise

    def initialize(self):
        expected = {
            "metadata": (("key", "TEXT", 0, 1), ("value", "TEXT", 1, 0)),
            "records": (("namespace", "TEXT", 1, 1), ("id", "TEXT", 1, 2),
                        ("payload", "TEXT", 1, 0), ("digest", "TEXT", 1, 0)),
            "links": (("namespace", "TEXT", 1, 1), ("key", "TEXT", 1, 2),
                      ("target", "TEXT", 1, 0)),
        }
        objects = self.connection.execute(
            "SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if any(name not in expected or kind != "table" for name, kind in objects):
            raise CorruptArtifact("unknown database structure")
        existing = {name for name, _ in objects}
        for table in existing:
            columns = self.connection.execute("PRAGMA table_info(" + table + ")").fetchall()
            shape = tuple((row[1], row[2].upper(), row[3], row[5]) for row in columns)
            if shape != expected[table]:
                raise CorruptArtifact("incompatible table: " + table)
        if existing:
            if "metadata" not in existing:
                raise CorruptArtifact("missing schema version")
            row = self.connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if row is None or row[0] != str(SCHEMA_VERSION):
                raise CorruptArtifact("unsupported schema version")
        with self.transaction():
            for statement in SCHEMA_STATEMENTS:
                self.connection.execute(statement)
            if not existing:
                self.connection.execute("INSERT INTO metadata VALUES (?,?)",
                                        ("schema_version", str(SCHEMA_VERSION)))

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def get(self, namespace, record_id):
        row = self.connection.execute(
            "SELECT payload,digest FROM records WHERE namespace=? AND id=?",
            (namespace, record_id)).fetchone()
        if row is None:
            return None
        if artifact_digest(row[0]) != row[1]:
            raise CorruptArtifact("record digest mismatch")
        return row[0]

    def insert(self, namespace, record_id, body):
        self.connection.execute(
            "INSERT INTO records(namespace,id,payload,digest) VALUES (?,?,?,?)",
            (namespace, record_id, body, artifact_digest(body)))

    def lookup(self, namespace, key):
        row = self.connection.execute(
            "SELECT target FROM links WHERE namespace=? AND key=?", (namespace, key)).fetchone()
        return None if row is None else row[0]

    def link(self, namespace, key, target):
        self.connection.execute("INSERT INTO links(namespace,key,target) VALUES (?,?,?)",
                                (namespace, key, target))

    def close(self):
        self.connection.close()
