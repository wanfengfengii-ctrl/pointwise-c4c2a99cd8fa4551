from dataclasses import dataclass

from record.measurements import MeasurementOccurrence, MeasurementSequence, Recording


manifest_schema_version = 1
PacketOccurrence = MeasurementOccurrence


@dataclass(frozen=True)
class PacketManifest:
    recording: Recording
    revision_id: str
    parent_revision_id: str | None
    occurrences: tuple[PacketOccurrence, ...]

    def sequence(self):
        return MeasurementSequence(self.recording.channels, self.occurrences)
