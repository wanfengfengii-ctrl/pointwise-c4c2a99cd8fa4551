from issue.encode import FixedPacket, compute_packet_digest, encode_packet
from issue.manifest import PacketManifest
from labdb import SQLiteStore


class IssueRegistry(SQLiteStore):
    def _initialize(self):
        self.connection.execute('''CREATE TABLE IF NOT EXISTS outbound_packets (
            outbound_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL, revision_id TEXT NOT NULL,
            digest TEXT NOT NULL, payload BLOB NOT NULL
        )''')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS reissues (
            reissue_id INTEGER PRIMARY KEY,
            outbound_id TEXT NOT NULL REFERENCES outbound_packets(outbound_id)
        )''')
        self.connection.execute('CREATE INDEX IF NOT EXISTS reissues_outbound ON reissues(outbound_id)')

    def register_packet(self, manifest: PacketManifest):
        packet = encode_packet(manifest)
        with self.write() as connection:
            existing = self.find_packet(packet.outbound_id)
            if existing is None:
                connection.execute('INSERT INTO outbound_packets VALUES (?, ?, ?, ?, ?)', (
                    packet.outbound_id, manifest.recording.recording_id, manifest.revision_id,
                    packet.digest, packet.payload,
                ))
            elif existing != packet:
                raise ValueError('outbound identity is already bound to other bytes')
        return packet

    def find_packet(self, outbound_id):
        row = self.connection.execute('''SELECT digest, payload FROM outbound_packets
                                         WHERE outbound_id = ?''', (outbound_id,)).fetchone()
        if row is None:
            return None
        if compute_packet_digest(row['payload']) != row['digest']:
            raise ValueError('stored outbound packet digest mismatch')
        return FixedPacket(outbound_id, row['digest'], row['payload'])

    def record_reissue(self, packet: FixedPacket):
        with self.write() as connection:
            current = self.find_packet(packet.outbound_id)
            if current is None:
                raise KeyError(packet.outbound_id)
            if current != packet:
                raise ValueError('reissue must use the original outbound bytes and digest')
            connection.execute('INSERT INTO reissues(outbound_id) VALUES (?)', (packet.outbound_id,))
        return current
