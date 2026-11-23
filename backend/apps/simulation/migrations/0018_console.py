"""The SQL console (P3.4): a schema of views over one game's own data.

Each view keeps only the rows of the organisation whose console session is open
(``console_session``, keyed by the database backend's process id). The console
role ``simb_console`` may read these views and nothing else: not the world, not
the app's own tables, not the answer key. The role is created once by a superuser
(README, "The SQL console"); its grants are given here if it exists, and by
``manage.py console_grants`` if it is created later.
"""

from django.db import migrations

ORG = "(SELECT organization_id FROM console_session WHERE pid = pg_backend_pid())"

VIEWS = {
    "customers": f"""
        SELECT c.id, c.customer_reference, c.customer_type, c.record_status, c.created_at
        FROM bureau_core_customer c WHERE c.organization_id = {ORG}""",
    "individuals": f"""
        SELECT p.customer_id, p.first_name, p.middle_name, p.last_name, p.date_of_birth,
               p.gender_code, p.employment_status
        FROM bureau_core_individualprofile p
        JOIN bureau_core_customer c ON c.id = p.customer_id WHERE c.organization_id = {ORG}""",
    "businesses": f"""
        SELECT p.customer_id, p.registered_name, p.trading_name, p.registration_number,
               p.tin_number, p.sector_code, p.registration_date
        FROM bureau_core_businessprofile p
        JOIN bureau_core_customer c ON c.id = p.customer_id WHERE c.organization_id = {ORG}""",
    "identifiers": f"""
        SELECT i.customer_id, i.identifier_type, i.identifier_value, i.verification_status
        FROM bureau_core_customeridentifier i WHERE i.organization_id = {ORG}""",
    "accounts": f"""
        SELECT a.id, a.customer_id, inst.institution_code AS lender, b.branch_code,
               b.region, a.facility_account_number, a.facility_type, a.currency_code,
               a.disbursement_date, a.maturity_date, a.original_amount, a.account_status
        FROM bureau_core_creditaccount a
        JOIN bureau_providers_institution inst ON inst.id = a.institution_id
        LEFT JOIN bureau_providers_institutionbranch b ON b.id = a.branch_id
        WHERE a.organization_id = {ORG}""",
    "observations": f"""
        SELECT o.credit_account_id AS account_id, o.reporting_date, o.outstanding_balance,
               o.arrears_amount, o.days_past_due, o.instalment_amount, o.amount_paid,
               o.facility_status, o.asset_classification, o.is_written_off
        FROM bureau_core_accountobservation o
        JOIN bureau_core_creditaccount a ON a.id = o.credit_account_id
        WHERE o.is_current AND a.organization_id = {ORG}""",
    "enquiries": f"""
        SELECT e.id, e.enquiry_reference, s.subscriber_code AS subscriber, e.product_code,
               e.purpose, e.enquired_at, e.outcome, e.customer_id, e.accounts_reported
        FROM bureau_core_enquiry e
        LEFT JOIN commercial_subscriber s ON s.id = e.subscriber_id
        WHERE e.organization_id = {ORG}""",
    "submissions": f"""
        SELECT s.submission_reference, inst.institution_code AS lender, s.reporting_period,
               s.template_version, s.due_date, s.received_at, s.submission_status,
               s.total_records
        FROM bureau_submissions_submission s
        JOIN bureau_providers_institution inst ON inst.id = s.institution_id
        WHERE s.organization_id = {ORG}""",
    "disputes": f"""
        SELECT d.dispute_number, d.customer_id, d.subject_name, d.claim, d.received_at,
               d.due_date, d.status, d.outcome, d.resolved_at, d.resolved_by
        FROM bureau_quality_dispute d WHERE d.organization_id = {ORG}""",
    "work_items": f"""
        SELECT w.item_number, w.item_type, w.difficulty, w.created_tick, w.due_tick, w.status,
               e.employee_number AS assignee, w.started_tick, w.resolved_tick, w.resolved_by,
               w.decision, w.confidence
        FROM workitems_workitem w
        LEFT JOIN org_employee e ON e.id = w.assignee_id
        WHERE w.organization_id = {ORG}""",
    "ledger_accounts": f"""
        SELECT a.code, a.name, a.account_type
        FROM finance_account a WHERE a.organization_id = {ORG}""",
    "journal_entries": f"""
        SELECT j.id, j.journal_reference, j.transaction_date, j.description, j.source_type,
               j.source_reference, j.posted_at
        FROM finance_journalentry j WHERE j.organization_id = {ORG}""",
    "journal_lines": f"""
        SELECT l.entry_id, a.code AS account_code, a.name AS account_name, l.debit, l.credit,
               l.memo
        FROM finance_journalline l
        JOIN finance_journalentry j ON j.id = l.entry_id
        JOIN finance_account a ON a.id = l.account_id
        WHERE j.organization_id = {ORG}""",
    "invoices": f"""
        SELECT i.invoice_number, s.subscriber_code AS subscriber, i.period_start, i.period_end,
               i.issue_date, i.due_date, i.subtotal, i.tax, i.total
        FROM finance_invoice i
        JOIN commercial_subscriber s ON s.id = i.subscriber_id
        WHERE i.organization_id = {ORG}""",
}

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'simb_console') THEN
        GRANT USAGE ON SCHEMA console TO simb_console;
        GRANT SELECT ON ALL TABLES IN SCHEMA console TO simb_console;
    END IF;
END $$;
"""

FORWARD = [
    "CREATE SCHEMA IF NOT EXISTS console",
    # Which organisation each open console session may see; the console role cannot write it.
    "CREATE TABLE console_session (pid integer PRIMARY KEY, organization_id bigint NOT NULL)",
    *(
        f"CREATE VIEW console.{name} WITH (security_barrier = true) AS {sql}"
        for name, sql in VIEWS.items()
    ),
    GRANTS,
]
BACKWARD = ["DROP SCHEMA IF EXISTS console CASCADE", "DROP TABLE IF EXISTS console_session"]


class Migration(migrations.Migration):
    dependencies = [
        ("simulation", "0017_roles"),
        ("bureau_core", "0006_link_method"),
        ("bureau_providers", "0002_institution_srn"),
        ("bureau_quality", "0004_disputes"),
        ("bureau_submissions", "0008_alter_submissionfile_file_kind_and_more"),
        ("commercial", "0001_initial"),
        ("finance", "0002_journalentry_rules_version"),
        ("workitems", "0003_workitem_due_tick"),
        ("org", "0009_departments"),
    ]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
