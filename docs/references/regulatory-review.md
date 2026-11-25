# Regulatory content for the owner's review (D14)

Every regulatory statement the game makes, with the provision it cites. Each is marked
**TO_CONFIRM** in the code until the owner has checked it against the text; confirming one
means setting its `status` to `CONFIRMED` (Handbook: `apps/standards/handbook.py`; compliance
rules: `apps/standards/compliance_rules.py`) and, for a Handbook entry, `reviewed=True` once
all its citations are confirmed. The Data Standards Committee manuals (R1-R3) are our own
references and are already marked confirmed.

Generated for P3.14 (Handbook v2) on 2026-11-25. The texts needed: R6 Act 726, R7 L.I. 2394,
R10 Act 843, R11 Bank of Ghana directives, R19 Act 1015; R15 for the economy entry.

## Handbook entries

| Entry | Version | Provision cited | Reference | Status | Owner's note |
| --- | --- | --- | --- | --- | --- |
| Days past due (`days-past-due`) | v1 | Bank of Ghana prudential classification, as noted in R2 | R2 | TO_CONFIRM | |
| Enquiry (`enquiry`) | v1 | Credit Reporting Act, 2007 (Act 726), provision to be confirmed | R6 | TO_CONFIRM | |
| Permissible purpose (`permissible-purpose`) | v1 | Credit Reporting Act, 2007 (Act 726), provision to be confirmed | R6 | TO_CONFIRM | |
| Permissible purpose (`permissible-purpose`) | v1 | Credit Reporting Regulations, 2020 (L.I. 2394), provision to be confirmed | R7 | TO_CONFIRM | |
| Consent (`consent`) | v1 | Credit Reporting Regulations, 2020 (L.I. 2394), provision to be confirmed | R7 | TO_CONFIRM | |
| Consent (`consent`) | v1 | Data Protection Act, 2012 (Act 843), provision to be confirmed | R10 | TO_CONFIRM | |
| Dispute (`dispute`) | v1 | Credit Reporting Regulations, 2020 (L.I. 2394), Regulations 23-26 (dispute resolution) | R7 | TO_CONFIRM | |
| Dispute (`dispute`) | v1 | Credit Reporting Act, 2007 (Act 726), provision to be confirmed | R6 | TO_CONFIRM | |
| Overdraft, creditors and insolvency (`insolvency`) | v1 | Corporate Insolvency and Restructuring Act, 2020 (Act 1015), provision to be confirmed | R19 | TO_CONFIRM | |
| The bureau's licence (`licence`) | v1 | Credit Reporting Act, 2007 (Act 726), provision to be confirmed | R6 | TO_CONFIRM | |
| The bureau's licence (`licence`) | v1 | Bank of Ghana directives and notices, provision to be confirmed | R11 | TO_CONFIRM | |
| The subject's rights (`subject-rights`) | v2 | Credit Reporting Act, 2007 (Act 726), on the rights of the data subject | R6 | TO_CONFIRM | |
| The subject's rights (`subject-rights`) | v2 | Credit Reporting Regulations, 2020 (L.I. 2394), Regulations 23-26 (dispute resolution) | R7 | TO_CONFIRM | |
| The subject's rights (`subject-rights`) | v2 | Data Protection Act, 2012 (Act 843), on the data subject's rights of access and correction | R10 | TO_CONFIRM | |
| Correcting a record (`correction`) | v2 | Credit Reporting Regulations, 2020 (L.I. 2394), Regulations 23-26 (dispute resolution) | R7 | TO_CONFIRM | |
| Findings and the regulator's ladder (`regulator-ladder`) | v2 | Bank of Ghana directives and notices, provision to be confirmed | R11 | TO_CONFIRM | |
| Findings and the regulator's ladder (`regulator-ladder`) | v2 | Credit Reporting Act, 2007 (Act 726), on the supervisor's powers | R6 | TO_CONFIRM | |
| Restricted attributes (`restricted-attribute`) | v2 | Owner's policy for the game (D14); anti-discrimination principles, provision to be confirmed | — | TO_CONFIRM | |
| Consent sampling (`consent-sampling`) | v2 | Credit Reporting Regulations, 2020 (L.I. 2394), on consent and permissible purpose | R7 | TO_CONFIRM | |
| Consent sampling (`consent-sampling`) | v2 | Credit Reporting Act, 2007 (Act 726), on access to credit information | R6 | TO_CONFIRM | |
| Sanctioning a subscriber (`sanction`) | v2 | Credit Reporting Regulations, 2020 (L.I. 2394), on the bureau's duties toward users of credit information | R7 | TO_CONFIRM | |
| The monthly return (`regulatory-return`) | v2 | Bank of Ghana directives to credit bureaus, provision to be confirmed | R11 | TO_CONFIRM | |
| Retention (`retention`) | v2 | Credit Reporting Regulations, 2020 (L.I. 2394), on retention of credit information | R7 | TO_CONFIRM | |
| Retention (`retention`) | v2 | Data Protection Act, 2012 (Act 843), on keeping personal data no longer than necessary | R10 | TO_CONFIRM | |
| Access review (`access-review`) | v2 | Data Protection Act, 2012 (Act 843), on security of personal data | R10 | TO_CONFIRM | |
| Onboarding a data provider (`provider-onboarding`) | v2 | Credit Reporting Act, 2007 (Act 726), on the duty of data providers to report | R6 | TO_CONFIRM | |
| The economy (`economy`) | v2 | Bank of Ghana statistical releases, provision to be confirmed | R15 | TO_CONFIRM | |

## Compliance rules (the Compliance screen)

| Rule | What the game enforces | Citation | Status | Owner's note |
| --- | --- | --- | --- | --- |
| Consent and permissible purpose (`CONSENT`) | A subscriber may enquire only with the subject's consent, given on the application form, and for a permitted purpose: new credit, review of an existing account, employment or tenancy screening, or collecting a debt. The bureau checks a sample and acts on a subscriber that cannot show consent. | Credit Reporting Act, 2007 (Act 726), on access to credit information; Credit Reporting Regulations, 2020 (L.I. 2394), on consent and permissible purpose | TO_CONFIRM | |
| Monthly return to the Bank of Ghana (`RETURN`) | The bureau files a return on its activity for each month by the 15th of the next month (the next working day if that is not one). | Bank of Ghana directives to credit bureaus (R11) | TO_CONFIRM | |
| Retention of credit information (`RETENTION`) | A closed account is kept on reports for 5 years after it closed, and no longer. A bureau may keep it for a shorter time, not a longer one. | Credit Reporting Regulations, 2020 (L.I. 2394), on retention; Data Protection Act, 2012 (Act 843), on keeping personal data no longer than necessary | TO_CONFIRM | |
| Access to the bureau's data (`ACCESS`) | Only staff who need it may reach the bureau's data. Access is reviewed each quarter, and a leaver's access is removed. | Data Protection Act, 2012 (Act 843), on security of personal data | TO_CONFIRM | |
| Restricted attributes in credit decisions (`FAIRNESS`) | A credit score may not use a restricted attribute such as gender. | Owner's policy for the game (D14); anti-discrimination principles to confirm | TO_CONFIRM | |
| Putting findings right (`FINDINGS`) | Each compliance finding has a remedy and a deadline. A finding left past its deadline is reported to the regulator. | Bank of Ghana supervisory practice (R11) | TO_CONFIRM | |

33 citations in all, none yet confirmed by the owner.
