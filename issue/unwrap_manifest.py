from dataclasses import dataclass

from record.measurements import SourceRef


unwrap_schema_version = 2


@dataclass(frozen=True)
class UnwrapSelected:
    position: int
    residue: int
    source: SourceRef


@dataclass(frozen=True)
class UnwrapManifest:
    recording_id: str
    revision_id: str
    channel: str
    modulus: int
    bounds: tuple[int, int]
    max_step: int
    selected: tuple[UnwrapSelected, ...]
    evidence: tuple[tuple[int, ...], ...]


def unwrap_manifest_data(manifest: UnwrapManifest):
    return {
        'kind': 'unwrap',
        'recording_id': manifest.recording_id,
        'revision_id': manifest.revision_id,
        'channel': manifest.channel,
        'modulus': manifest.modulus,
        'bounds': [manifest.bounds[0], manifest.bounds[1]],
        'max_step': manifest.max_step,
        'selected': [
            {
                'position': entry.position,
                'residue': entry.residue,
                'source': {
                    'artifact': entry.source.artifact,
                    'start': entry.source.start,
                    'end': entry.source.end,
                },
            }
            for entry in manifest.selected
        ],
        'evidence': [list(combo) for combo in manifest.evidence],
    }
