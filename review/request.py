from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from receive.store import valid_acceptance_id
from record.measurements import parse_rational
from record.validation import require_identifier


@dataclass(frozen=True)
class ReviewRequest:
    acceptance_id: int
    initial_references: tuple[tuple[str, Fraction], ...]
    threshold: Fraction

    def as_data(self):
        return {
            'acceptance_id': self.acceptance_id,
            'initial_references': {channel: str(value) for channel, value in self.initial_references},
            'threshold': str(self.threshold),
            'unit': 'mV',
        }


def make_review_request(acceptance_id, initial_references, threshold):
    if not isinstance(initial_references, Mapping):
        raise ValueError('initial references must map channel names to exact values')
    pairs = []
    for channel, value in initial_references.items():
        require_identifier(channel, 'reference channel')
        pairs.append((channel, parse_rational(value)))
    request = ReviewRequest(acceptance_id, tuple(sorted(pairs)), parse_rational(threshold))
    validate_review_request(request)
    return request


def validate_review_request(request: ReviewRequest, declared_channels=None, active_channels=None):
    if not isinstance(request, ReviewRequest) or not valid_acceptance_id(request.acceptance_id):
        raise ValueError('invalid review acceptance id')
    if not isinstance(request.threshold, Fraction) or request.threshold < 0:
        raise ValueError('threshold must be an exact nonnegative rational number')
    if not isinstance(request.initial_references, tuple):
        raise ValueError('initial reference snapshot must be an immutable sequence')
    given = set()
    for entry in request.initial_references:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError('invalid initial reference entry')
        channel, value = entry
        require_identifier(channel, 'reference channel')
        if channel in given or not isinstance(value, Fraction):
            raise ValueError('each initial reference needs a unique channel and a Fraction')
        given.add(channel)
    if declared_channels is not None:
        unknown = given.difference(declared_channels)
        if unknown:
            raise ValueError(f'unknown reference channels: {sorted(unknown)!r}')
    if active_channels is not None:
        missing = set(active_channels).difference(given)
        if missing:
            raise ValueError(f'missing initial references: {sorted(missing)!r}')
