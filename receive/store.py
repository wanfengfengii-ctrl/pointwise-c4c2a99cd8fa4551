from labdb import SQLiteStore


MAX_ACCEPTANCE_ID = 2 ** 63 - 1


def valid_acceptance_id(acceptance_id):
    return type(acceptance_id) is int and 0 < acceptance_id <= MAX_ACCEPTANCE_ID


def initialize_receive_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS acceptances (
        acceptance_id INTEGER PRIMARY KEY, outbound_id TEXT NOT NULL,
        revision_id TEXT NOT NULL, digest TEXT NOT NULL, payload BLOB NOT NULL
    )''')
    connection.execute('CREATE INDEX IF NOT EXISTS acceptances_outbound ON acceptances(outbound_id)')


class ReceiveStore(SQLiteStore):
    def _initialize(self):
        initialize_receive_schema(self.connection)

    def save_acceptance(self, outbound_id, revision_id, digest, payload):
        with self.write() as connection:
            cursor = connection.execute('''INSERT INTO acceptances(outbound_id, revision_id, digest, payload)
                                           VALUES (?, ?, ?, ?)''', (outbound_id, revision_id, digest, payload))
            acceptance_id = cursor.lastrowid
        return acceptance_id

    def load_acceptance(self, acceptance_id):
        if not valid_acceptance_id(acceptance_id):
            raise KeyError(acceptance_id)
        row = self.connection.execute('SELECT * FROM acceptances WHERE acceptance_id = ?',
                                      (acceptance_id,)).fetchone()
        if row is None:
            raise KeyError(acceptance_id)
        return row

    def acceptance_rows(self):
        return self.connection.execute('SELECT * FROM acceptances ORDER BY acceptance_id').fetchall()
