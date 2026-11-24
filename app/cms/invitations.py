"""Invitation integration contract, intentionally not connected to a mail transport.

No pending credentials are persisted. When delivery is implemented, use a short-lived
set-password link instead of queuing the account's plaintext password.
"""
TEAM_LABELS = {'students': 'معلومات الطلاب', 'teachers': 'معلومات المعلم', 'other': 'باقي المعلومات'}


def invitation_preview(full_name, username, team_type):
    return {'status': 'disabled', 'subject': 'دعوة لفريق إدخال بيانات WE MATH',
            'body': f'مرحبًا {full_name}، تم إنشاء حسابك ضمن فريق {TEAM_LABELS[team_type]}. اسم المستخدم: {username}. سيزودك الأدمن ببيانات الدخول.'}
