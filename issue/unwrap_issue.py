from issue.unwrap_manifest import UnwrapManifest, UnwrapSelected
from record.revisions import get_frozen_revision
from record.store import RecordStore
from unwrap.tracks import joint_evidence


def _require_int(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer (booleans are rejected)')
    return value


def validate_unwrap_parameters(channel, modulus, bounds, max_step, positions):
    if not isinstance(channel, str) or not channel or channel.strip() != channel:
        raise ValueError('channel must be a registered channel name')
    _require_int(modulus, 'modulus')
    if modulus <= 0:
        raise ValueError('modulus must be a positive integer')
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError('bounds must be a closed [lo, hi] range')
    low, high = bounds
    _require_int(low, 'bounds endpoint')
    _require_int(high, 'bounds endpoint')
    if low > high:
        raise ValueError('bounds must satisfy lo <= hi')
    _require_int(max_step, 'max_step')
    if max_step < 0:
        raise ValueError('max_step must be a nonnegative integer')
    if not isinstance(positions, (list, tuple)) or not positions:
        raise ValueError('positions must be a nonempty list or tuple')
    normalized = []
    for position in positions:
        _require_int(position, 'position')
        if position < 0:
            raise ValueError('positions must be zero-based original positions')
        normalized.append(position)
    if len(set(normalized)) != len(normalized):
        raise ValueError('positions must be distinct')
    return channel, modulus, low, high, max_step, tuple(sorted(normalized))


def select_unwrap_for_issue(store: RecordStore, revision_id, channel, modulus, bounds, max_step, positions):
    channel, modulus, low, high, max_step, positions = validate_unwrap_parameters(
        channel, modulus, bounds, max_step, positions,
    )
    revision = get_frozen_revision(store, revision_id)
    if channel not in revision.recording.channels:
        raise ValueError(f'unknown channel {channel!r}')
    channel_rows = tuple(
        occurrence for occurrence in revision.sequence.occurrences if occurrence.channel_id == channel
    )
    if not channel_rows:
        raise ValueError(f'channel {channel!r} has no occurrences in this revision')
    channel_positions = {occurrence.position for occurrence in channel_rows}
    unknown = [position for position in positions if position not in channel_positions]
    if unknown:
        raise ValueError(f'positions do not belong to channel {channel!r}: {unknown!r}')
    residues = []
    for occurrence in channel_rows:
        value = occurrence.original.value
        if value.denominator != 1:
            raise ValueError('original readings must be integer residues')
        residue = value.numerator
        if not 0 <= residue < modulus:
            raise ValueError('each original reading must be an integer residue in [0, modulus)')
        residues.append(residue)
    local_index = {occurrence.position: index for index, occurrence in enumerate(channel_rows)}
    selected_beats = tuple(local_index[position] for position in positions)
    evidence = joint_evidence(residues, selected_beats, modulus, low, high, max_step)
    if evidence is None:
        raise ValueError('no legal full track exists; unwrap packet rejected')
    rows_by_position = {occurrence.position: occurrence for occurrence in channel_rows}
    selected = tuple(
        UnwrapSelected(position, rows_by_position[position].original.value.numerator,
                       rows_by_position[position].original.source)
        for position in positions
    )
    return UnwrapManifest(revision.recording.recording_id, revision.revision_id, channel, modulus,
                          (low, high), max_step, selected, evidence)
