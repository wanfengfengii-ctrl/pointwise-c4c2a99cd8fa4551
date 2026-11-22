from dataclasses import dataclass
from fractions import Fraction

from lab import IssueRegistry, ReceiveStore, RecordStore, ReportStore
from lab import issue_packet, read_report, receive_packet, record_revision
from lab import register_recording, reissue_packet, sign_review
from record.measurements import MeasurementOccurrence, ReadingCandidate, SourceRef


@dataclass(frozen=True)
class Example:
    residues: tuple[int, ...]
    bounds: tuple[int, int]
    max_step: int
    positions: tuple[int, ...]
    anchors: tuple[tuple[int, int], ...] = ()
    modulus: int = 10
    channel: str = "A"


EXAMPLES = {
    "middle-five": Example((0, 5, 0), (0, 20), 6, (0, 2), ((0, 0), (2, 10))),
    "middle-zero": Example((0, 0, 0), (0, 20), 6, (0, 2), ((0, 0), (2, 10))),
    "hidden-prefix": Example((4, 0), (0, 10), 4, (1,)),
}


def freeze_example(source, name):
    example = EXAMPLES[name]
    register_recording(source, name, "unwrap-check", "steel-K4", "wrap-meter", (example.channel,))
    occurrences = tuple(
        MeasurementOccurrence(
            f"{name}-m{position}", position, example.channel, "bridge",
            ReadingCandidate(Fraction(residue), SourceRef(f"{name}-{position}.raw", 0, 2)),
        )
        for position, residue in enumerate(example.residues)
    )
    return record_revision(source, name, f"{name}-draft", f"{name}-r1", occurrences)


def main():
    deliveries = {}
    with RecordStore(":memory:") as source, IssueRegistry(":memory:") as registry:
        for name in EXAMPLES:
            revision = freeze_example(source, name)
            issued = issue_packet(source, registry, revision.revision_id)
            delivery = reissue_packet(registry, issued.outbound_id)
            if delivery != issued:
                raise RuntimeError(f"{name}: V1 reissue changed delivery bytes")
            deliveries[name] = delivery
    with ReceiveStore(":memory:") as inventory, ReportStore(":memory:") as reports:
        for name, delivery in deliveries.items():
            example = EXAMPLES[name]
            accepted = receive_packet(inventory, delivery.payload, delivery.digest, delivery.outbound_id)
            initial_references = {example.channel: 0}
            signed = sign_review(inventory, reports, accepted.acceptance_id,
                                 initial_references, max(map(abs, example.residues)))
            report = read_report(reports, signed.receipt.report_id)
            values = [row["delta"] for row in report.report["rows"]]
            if report != signed or values != [str(residue) for residue in example.residues]:
                raise RuntimeError(f"{name}: V1 round trip changed the recorded reads")
            print(f"{accepted.revision_id} / acceptance {accepted.acceptance_id}: V1 mV {values}")


if __name__ == "__main__":
    main()
