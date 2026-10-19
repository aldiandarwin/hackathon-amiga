"""Read-only summaries of saved validation and tax results for the work queue."""

from .review import SOURCE_CHECKS


def queue_summary(snapshot, status):
    snapshot = snapshot or {}
    checks = (snapshot.get('validation') or {}).get('checks') or []
    failed = [item for item in checks if item.get('status') != 'PASSED']
    blockers = list(dict.fromkeys(item['code'] for item in failed
                                 if item.get('blocking') and item['code'] not in SOURCE_CHECKS))
    sources = {item['code'] for item in failed if item.get('blocking') and item['code'] in SOURCE_CHECKS}
    tax = snapshot.get('tax') or {}
    if tax.get('status') == 'NOT_SELECTED' and 'TAX_SELECTION_REQUIRED' not in blockers:
        blockers.append('TAX_SELECTION_REQUIRED')
    if tax.get('status') == 'NOT_COMPUTED' and not blockers:
        blockers.append('TAX_NOT_COMPUTED')
    return {
        'issue_codes': blockers[:3], 'issue_count': len(blockers),
        'source_check_count': 0 if status in ('AMIGA_REVIEWED', 'AMIGA_APPROVED') else len(sources),
        'net_payable': tax.get('net_payable') if tax.get('status') == 'COMPUTED' else None,
    }
