from fractions import Fraction

from record.measurements import MeasurementOccurrence, MeasurementSequence, ReadingCandidate, SourceRef


def require_identifier(value, label):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'invalid {label}')


def validate_channels(channels):
    if not isinstance(channels, tuple) or not channels:
        raise ValueError('a recording needs named channels')
    for channel in channels:
        require_identifier(channel, 'channel')
    if len(set(channels)) != len(channels):
        raise ValueError('duplicate channel')


def validate_recording(recording):
    require_identifier(recording.recording_id, 'recording id')
    require_identifier(recording.work_order, 'work order')
    require_identifier(recording.batch_id, 'batch id')
    require_identifier(recording.instrument_id, 'instrument id')
    validate_channels(recording.channels)


def validate_candidate(candidate):
    if not isinstance(candidate, ReadingCandidate) or not isinstance(candidate.value, Fraction):
        raise ValueError('a reading needs a Fraction value and a source')
    source = candidate.source
    if not isinstance(source, SourceRef):
        raise ValueError('invalid reading source')
    require_identifier(source.artifact, 'source artifact')
    if type(source.start) is not int or type(source.end) is not int or not 0 <= source.start < source.end:
        raise ValueError('source range must be a nonempty half-open byte range')


def validate_occurrence(occurrence, channels, position):
    if not isinstance(occurrence, MeasurementOccurrence):
        raise ValueError('invalid measurement occurrence')
    require_identifier(occurrence.occurrence_id, 'occurrence id')
    require_identifier(occurrence.channel_id, 'channel id')
    require_identifier(occurrence.template_id, 'template id')
    if type(occurrence.position) is not int or occurrence.position != position:
        raise ValueError('measurement positions must follow the original order')
    if occurrence.channel_id not in channels:
        raise ValueError(f'unknown channel {occurrence.channel_id!r}')
    validate_candidate(occurrence.original)
    if occurrence.supplement is not None:
        validate_candidate(occurrence.supplement)


def reject_duplicate_occurrence(occurrences):
    seen = set()
    for occurrence in occurrences:
        if occurrence.occurrence_id in seen:
            raise ValueError(f'duplicate occurrence {occurrence.occurrence_id!r}')
        seen.add(occurrence.occurrence_id)


def validate_sequence(sequence):
    if not isinstance(sequence, MeasurementSequence) or not isinstance(sequence.occurrences, tuple):
        raise ValueError('expected an immutable measurement sequence')
    validate_channels(sequence.channels)
    channels = frozenset(sequence.channels)
    for position, occurrence in enumerate(sequence.occurrences):
        validate_occurrence(occurrence, channels, position)
    reject_duplicate_occurrence(sequence.occurrences)


def validate_revision_shape(recording, revision_id, parent_revision_id, sequence):
    validate_recording(recording)
    require_identifier(revision_id, 'revision id')
    if parent_revision_id is not None:
        require_identifier(parent_revision_id, 'base revision id')
        if parent_revision_id == revision_id:
            raise ValueError('a revision cannot correct itself')
    validate_sequence(sequence)
    if sequence.channels != recording.channels or not sequence.occurrences:
        raise ValueError('a frozen revision needs registered channels and at least one occurrence')
