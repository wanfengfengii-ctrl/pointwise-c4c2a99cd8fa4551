from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class SourceRef:
    artifact: str
    start: int
    end: int


@dataclass(frozen=True)
class ReadingCandidate:
    value: Fraction
    source: SourceRef


@dataclass(frozen=True)
class MeasurementOccurrence:
    occurrence_id: str
    position: int
    channel_id: str
    template_id: str
    original: ReadingCandidate
    supplement: ReadingCandidate | None = None


@dataclass(frozen=True)
class MeasurementSequence:
    channels: tuple[str, ...]
    occurrences: tuple[MeasurementOccurrence, ...]


@dataclass(frozen=True)
class Recording:
    recording_id: str
    work_order: str
    batch_id: str
    instrument_id: str
    channels: tuple[str, ...]


def parse_rational(value):
    if isinstance(value, Fraction):
        return value
    if type(value) not in (int, str):
        raise ValueError('expected an exact rational number')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid rational number') from error


def require_fields(data, fields, label):
    if not isinstance(data, dict) or data.keys() != set(fields.split()):
        raise ValueError(f'invalid {label} fields')
    return data


def source_data(source):
    return {'artifact': source.artifact, 'start': source.start, 'end': source.end}


def candidate_data(candidate):
    if candidate is None:
        return None
    return {'value': str(candidate.value), 'source': source_data(candidate.source)}


def occurrence_data(occurrence):
    return {
        'occurrence_id': occurrence.occurrence_id,
        'position': occurrence.position,
        'channel_id': occurrence.channel_id,
        'template_id': occurrence.template_id,
        'original': candidate_data(occurrence.original),
        'supplement': candidate_data(occurrence.supplement),
    }


def sequence_data(sequence):
    return {
        'channels': list(sequence.channels),
        'occurrences': [occurrence_data(row) for row in sequence.occurrences],
    }


def source_from_data(data):
    require_fields(data, 'artifact start end', 'source')
    return SourceRef(data['artifact'], data['start'], data['end'])


def candidate_from_data(data):
    require_fields(data, 'value source', 'reading')
    return ReadingCandidate(parse_rational(data['value']), source_from_data(data['source']))


def occurrence_from_data(data):
    require_fields(data, 'occurrence_id position channel_id template_id original supplement', 'occurrence')
    supplement = data['supplement']
    return MeasurementOccurrence(
        data['occurrence_id'], data['position'], data['channel_id'], data['template_id'],
        candidate_from_data(data['original']),
        None if supplement is None else candidate_from_data(supplement),
    )


def sequence_from_data(data):
    require_fields(data, 'channels occurrences', 'measurement sequence')
    if not isinstance(data['channels'], list) or not isinstance(data['occurrences'], list):
        raise ValueError('channels and occurrences must be arrays')
    return MeasurementSequence(
        tuple(data['channels']), tuple(occurrence_from_data(row) for row in data['occurrences']),
    )
