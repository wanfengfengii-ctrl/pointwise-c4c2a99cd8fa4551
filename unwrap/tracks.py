"""Pure integer track solver for frozen-wrap (V2) calibration handover.

A track assigns one integer real value to every beat of the selected channel.
Each real value must lie in the closed bounds, share its beat's residue modulo
the modulus, and adjacent same-channel beats may differ by at most max_step.
"""


def candidate_values(residue, modulus, low, high):
    """All integers in [low, high] congruent to residue modulo modulus."""
    first = low + ((residue - low) % modulus)
    return tuple(range(first, high + 1, modulus))


def feasible_beat_values(residues, modulus, low, high, max_step):
    """Return the per-beat values that participate in at least one legal track.

    Returns None when no full track exists. Supplements never participate: only
    the channel's original readings are passed in as residues.
    """
    candidates = [candidate_values(residue, modulus, low, high) for residue in residues]
    if any(not values for values in candidates):
        return None
    forward = [set(candidates[0])]
    for index in range(1, len(residues)):
        reachable = set()
        earlier = forward[-1]
        for value in candidates[index]:
            if any(abs(value - previous) <= max_step for previous in earlier):
                reachable.add(value)
        if not reachable:
            return None
        forward.append(reachable)
    backward = [set(candidates[-1])]
    for index in range(len(residues) - 2, -1, -1):
        reachable = set()
        later = backward[0]
        for value in candidates[index]:
            if any(abs(value - following) <= max_step for following in later):
                reachable.add(value)
        if not reachable:
            return None
        backward.insert(0, reachable)
    return tuple(frozenset(forward[index] & backward[index]) for index in range(len(residues)))


def joint_evidence(residues, selected_beats, modulus, low, high, max_step):
    """Exact set of joint value tuples at selected beats extendable to a track.

    Returns the sorted tuple of value tuples, or None when no legal full track
    exists. Beat indices are local to the selected channel (interleaved rows of
    other channels do not break adjacency).
    """
    feasible = feasible_beat_values(residues, modulus, low, high, max_step)
    if feasible is None:
        return None
    selected = set(selected_beats)
    states = {}
    for value in feasible[0]:
        key = (value,) if 0 in selected else ()
        states.setdefault(key, set()).add(value)
    for index in range(1, len(residues)):
        following = {}
        for key, reachable in states.items():
            for value in feasible[index]:
                if any(abs(value - previous) <= max_step for previous in reachable):
                    next_key = key + ((value,) if index in selected else ())
                    following.setdefault(next_key, set()).add(value)
        if not following:
            return None
        states = following
    return tuple(sorted(states.keys()))


def adjudicate(evidence, anchor_indexes, anchors):
    """Apply one calibration sheet to the exact joint evidence.

    ``anchor_indexes`` maps a selected position to its tuple index. Returns
    ``('conflict', ())`` when no common track carries every anchor, otherwise
    ``('consistent', rows)`` where each row is (index, status, value).
    """
    matching = []
    for combo in evidence:
        if all(combo[anchor_indexes[position]] == value for position, value in anchors.items()):
            matching.append(combo)
    if not matching:
        return 'conflict', ()
    rows = []
    for index in range(len(anchor_indexes)):
        values = {combo[index] for combo in matching}
        if len(values) == 1:
            rows.append((index, 'unique', next(iter(values))))
        else:
            rows.append((index, 'ambiguous', None))
    return 'consistent', tuple(rows)
