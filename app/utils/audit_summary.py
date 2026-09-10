"""Allowlisted audit descriptions; raw payloads never reach the template."""
CATEGORIES = {'account': 'Accounts', 'capstone': 'Capstones', 'workflow': 'Requests & advisory', 'other': 'Other'}
ACTION_GROUPS = {
    'account': {
        'signup': 'Registered an account', 'login': 'Signed in', 'logout': 'Signed out',
        'password_reset': 'Reset a password', 'otp_verified': 'Verified a reset code',
        'update_contact': 'Updated contact information', 'role_change': 'Changed a user role',
        'account_status_change': 'Changed account status', 'delete_user': 'Deleted a user',
        'reapplication': 'Resubmitted account information',
        'verification_request': 'Requested account verification',
        'review_verification_request': 'Reviewed account verification',
        'promotion_request': 'Requested a role promotion',
        'review_promotion_request': 'Reviewed a role promotion',
        'cancel_promotion_request': 'Cancelled a role promotion request',
    },
    'capstone': {
        'create_capstone': 'Created a capstone', 'update_capstone': 'Updated a capstone',
        'update_capstone_people': 'Updated capstone contributors',
        'delete_capstone': 'Deleted a capstone', 'archive_capstone': 'Archived a capstone',
        'restore_capstone': 'Restored a capstone', 'assign_capstoner_credit': 'Linked an author account',
        'save_capstone': 'Saved a capstone', 'unsave_capstone': 'Removed a saved capstone',
    },
    'workflow': {
        'manuscript_request': 'Requested manuscript access', 'review_request': 'Reviewed manuscript access',
        'cancel_request': 'Cancelled a manuscript request', 'request_capstoner': 'Requested capstoner registration',
        'review_capstoner': 'Reviewed capstoner registration',
        'approve_capstoner_by_assignment': 'Approved capstoner registration by assignment',
        'create_advisory_group': 'Created an advisory group', 'rename_advisory_group': 'Renamed an advisory group',
        'add_advisory_student': 'Added an advisory student', 'remove_advisory_student': 'Removed an advisory student',
    },
}
ACTIONS = {action: label for group in ACTION_GROUPS.values() for action, label in group.items()}


def summarize_audit(row, roles):
    action = row['action_type']
    category = next((key for key, group in ACTION_GROUPS.items() if action in group), 'other')
    label = ACTIONS.get(action, 'Recorded an unrecognized action')
    changes = []
    if action == 'role_change':
        for field, caption in [('old_values', 'Previous role'), ('new_values', 'New role')]:
            value = str(row.get(field) or '')
            changes.append((caption, roles.get(int(value), 'Unknown role') if value.isascii() and value.isdigit() and len(value) < 10 else 'Unknown role'))
    elif action == 'account_status_change':
        for field, caption in [('old_values', 'Previous status'), ('new_values', 'New status')]:
            value = row.get(field)
            changes.append((caption, value if value in {'active', 'pending', 'rejected', 'inactive', 'suspended'} else 'Unknown status'))
    elif action in {'review_verification_request', 'review_promotion_request', 'review_request', 'review_capstoner'}:
        value = row.get('new_values') or ''
        decision = value.split(' -> ', 1)[0]
        if decision in {'approved', 'rejected'}:
            changes.append(('Decision', decision.capitalize()))
    target = row.get('affected_record_id')
    summary = label + (f' (record #{target})' if target is not None else '')
    if changes:
        summary += ': ' + ' → '.join(value for _, value in changes)
    return {
        'audit_id': row['audit_id'], 'actor_id': row.get('user_id'),
        'actor': (row.get('actor_name') or '').strip() or 'Unknown / deleted user',
        'timestamp': row['action_timestamp'], 'category': CATEGORIES[category],
        'action': label, 'summary': summary + '.', 'target_id': target,
        'target_table': row.get('affected_table') or 'Unknown', 'changes': changes,
    }
