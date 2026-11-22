from issue.manifest import PacketManifest, PacketOccurrence
from record.measurements import occurrence_data
from record.store import FrozenRevision
from record.validation import validate_revision_shape


def build_packet_evidence(revision: FrozenRevision):
    return PacketManifest(
        revision.recording, revision.revision_id, revision.parent_revision_id, revision.sequence.occurrences,
    )


def attach_occurrence_provenance(occurrence: PacketOccurrence):
    return occurrence_data(occurrence)


def validate_evidence_completeness(manifest: PacketManifest):
    validate_revision_shape(manifest.recording, manifest.revision_id,
                            manifest.parent_revision_id, manifest.sequence())
