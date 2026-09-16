"""Exact selector extracted from the frozen experimental implementation."""
def select_cross(rows,public,n=3):
    """No labels are accepted by this selector; unavailable votes abstain."""
    votes={i:[] for i in range(n)}
    for row in rows:
        if not row.get('source_unchanged') or not row.get('eligible'):continue
        for i,cell in enumerate(row['cells']):
            if i==row['donor_index'] or not cell:continue
            rr=cell['results'];statuses=[r['status'] for r in rr]
            if statuses and all(s in ('pass','assertion') for s in statuses):
                votes[i].append(int(all(s=='pass' for s in statuses)))
    eligible=[i for i in range(n) if public.get(i)] or list(range(n))
    scores={i:sum(v)/len(v) for i,v in votes.items() if v and i in eligible}
    picked=[i for i,s in scores.items() if s==max(scores.values())] if scores else eligible
    return {'picked':picked,'scores':scores,'votes':votes,'decision':'cross_vote' if scores else 'public_fallback','tie_policy':'uniform'}
