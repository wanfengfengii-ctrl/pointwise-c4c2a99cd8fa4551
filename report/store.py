from dataclasses import dataclass

from labdb import SQLiteStore


@dataclass(frozen=True)
class StoredBundle:
    report_id: str
    acceptance_id: int
    report_digest: str
    report_bytes: bytes
    receipt_id: str
    receipt_bytes: bytes


def initialize_report_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS reports (
        report_id TEXT PRIMARY KEY, acceptance_id INTEGER NOT NULL,
        report_digest TEXT NOT NULL, report_bytes BLOB NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE REFERENCES reports(report_id),
        receipt_bytes BLOB NOT NULL
    )''')
    connection.execute('CREATE INDEX IF NOT EXISTS reports_acceptance ON reports(acceptance_id, report_id)')


class ReportStore(SQLiteStore):
    def _initialize(self):
        initialize_report_schema(self.connection)

    def commit_bundle(self, bundle: StoredBundle):
        with self.write() as connection:
            existing = self.find_report(bundle.report_id)
            if existing is None:
                connection.execute('INSERT INTO reports VALUES (?, ?, ?, ?)', (
                    bundle.report_id, bundle.acceptance_id, bundle.report_digest, bundle.report_bytes,
                ))
                connection.execute('INSERT INTO receipts VALUES (?, ?, ?)', (
                    bundle.receipt_id, bundle.report_id, bundle.receipt_bytes,
                ))
            elif existing != bundle:
                raise ValueError('this report identity already has different signed content')
            else:
                bundle = existing
        return bundle

    def find_report(self, report_id):
        row = self.connection.execute('''SELECT r.*, s.receipt_id, s.receipt_bytes
            FROM reports AS r LEFT JOIN receipts AS s ON r.report_id = s.report_id
            WHERE r.report_id = ?''', (report_id,)).fetchone()
        if row is None:
            return None
        if row['receipt_id'] is None:
            raise ValueError('stored report has no success receipt')
        return StoredBundle(row['report_id'], row['acceptance_id'], row['report_digest'],
                            row['report_bytes'], row['receipt_id'], row['receipt_bytes'])

    def load_bundle(self, report_id):
        bundle = self.find_report(report_id)
        if bundle is None:
            raise KeyError(report_id)
        return bundle

    def report_ids_for_acceptance(self, acceptance_id):
        return tuple(row[0] for row in self.connection.execute(
            'SELECT report_id FROM reports WHERE acceptance_id = ? ORDER BY report_id', (acceptance_id,),
        ))
