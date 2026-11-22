import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lab import IssueRegistry, RecordStore, issue_packet, record_revision, register_recording
from record.measurements import sequence_from_data


def emit_scenario(case_id, input_data, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': input_data,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, sort_keys=True), flush=True)


class LabCase(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory(prefix='lab-test-'))
        self.root = Path(directory)
        self.source_path = self.root / 'source.sqlite'
        self.outbound_path = self.root / 'outbound.sqlite'
        self.receive_path = self.root / 'receive.sqlite'
        self.report_path = self.root / 'report.sqlite'
        sample_path = Path(__file__).resolve().parents[1] / 'samples' / 'shift.json'
        self.sample = json.loads(sample_path.read_text(encoding='utf-8'))
        self.sequence = sequence_from_data(self.sample['sequence'])

    def register(self, source, sequence):
        sample = self.sample
        return register_recording(source, sample['recording_id'], sample['work_order'], sample['batch_id'],
                                  sample['instrument_id'], sequence.channels)

    def freeze(self, source, sequence):
        recording = self.register(source, sequence)
        return record_revision(source, recording.recording_id, 'd1', self.sample['revision_id'], sequence.occurrences)

    def issue_sample(self, sequence=None):
        sequence = self.sequence if sequence is None else sequence
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            revision = self.freeze(source, sequence)
            return issue_packet(source, registry, revision.revision_id)
