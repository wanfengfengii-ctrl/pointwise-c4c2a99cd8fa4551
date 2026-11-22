from dataclasses import dataclass

from issue.registry import IssueRegistry
from record.revisions import get_frozen_revision
from record.store import FrozenRevision, RecordStore


@dataclass(frozen=True)
class IssueSelection:
    revision: FrozenRevision


def select_revision_for_issue(store: RecordStore, revision_id):
    return IssueSelection(get_frozen_revision(store, revision_id))


def select_packet_for_reissue(registry: IssueRegistry, outbound_id):
    packet = registry.find_packet(outbound_id)
    if packet is None:
        raise KeyError(outbound_id)
    return packet
