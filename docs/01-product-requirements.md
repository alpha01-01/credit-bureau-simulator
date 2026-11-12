# CREDIT BUREAU SIMULATOR

## Product Requirements Document (PRD)

**Document ID:** CBS-PRD-001
**Version:** 1.0
**Status:** Final – Approved Product Baseline
**Date:** 10 November 2026
**Product Type:** Business Simulation / Management Simulator / Interactive 3D Environment
**Initial Market Setting:** Ghana
**Primary Currency:** Ghana Cedi (GHS)
**Initial Release:** Single-player
**Future Release:** Multiplayer

---

# 1. Executive Summary

The Credit Bureau Simulator is an interactive business simulation platform in which players establish, operate, manage and grow a virtual credit bureau.

It combines a realistic credit bureau's operational environment with business management and game mechanics.

Players will manage a functioning virtual organization, overseeing departments such as Data Operations, Analytics, Finance, Sales, IT, Risk and Compliance, Human Resources, Customer Support and Product Development.

Unlike conventional business simulation games, the Credit Bureau Simulator will incorporate actual business processes and technical operations.

For example, the Data Operations department will receive synthetic credit data from financial institutions, validate submitted files, identify errors and duplicates, clean records and prepare accepted data for loading into the bureau database.

The Analytics department will use accumulated credit information to produce portfolio reports, develop analytical models and generate credit scores.

The Finance department will maintain accounting records, process transactions, manage expenses and prepare financial statements.

The ultimate objective is to create a virtual organization whose departments operate together as a connected business.

The first release will be single-player, with an architecture designed to support multiplayer in Version 2.

# 2. Product Vision

To create a realistic, interactive environment where players learn how a credit bureau operates by actually running one.

The simulator will combine:

* Business ownership and executive decision-making.
* Realistic departmental responsibilities.
* Practical data processing and database operations.
* Credit risk analytics and product development.
* Financial and operational management.
* Employee management and organizational growth.
* Collaboration and competition in future multiplayer modes.

The player should not simply observe employees working. The player should be able to participate in the actual work.

# 3. Product Objectives

1. **Operational realism:** Represent the essential processes of a functioning credit bureau.
2. **Practical learning:** Allow players to perform realistic business and technical tasks.
3. **Organizational management:** Give players responsibility for employees, departments, infrastructure, budgets and relationships.
4. **Technical engagement:** Incorporate practical SQL, Python, data processing, analytics and reporting.
5. **Business growth:** Allow players to develop products, acquire clients, generate revenue and expand.
6. **Replayability:** Offer different starting scenarios, objectives and difficulty settings.
7. **Multiplayer readiness:** Establish the architecture necessary for multiple players to work in the same organization in a future release.

# 4. Starting Game Experiences

Players will be able to choose between two starting experiences when creating a new game.

## 4.1 Established Bureau Mode

The player begins as the CEO of an existing credit bureau.

The organization has:

* An established office.
* Approximately 45 employees.
* Ten departments.
* Five initial data providers.
* Three initial subscriber relationships.
* Basic IT infrastructure.
* Initial bureau products.
* An existing synthetic credit database.
* An established financial position.

The player inherits an operating business and must manage its performance, improve operations, expand its customer base and grow the organization.

This mode emphasizes executive management, optimization, operational problem-solving and strategic expansion.

## 4.2 Startup Mode

The player begins with a newly established credit bureau.

The player must:

* Secure initial capital.
* Rent or acquire office space.
* Purchase equipment.
* Establish IT infrastructure.
* Recruit initial employees.
* Establish departments progressively.
* Acquire data providers.
* Negotiate subscriber agreements.
* Build the bureau database.
* Develop products.
* Generate revenue.
* Manage cash flow and operating expenses.

The organization starts small and grows as the player makes successful business decisions.

This mode emphasizes entrepreneurship, resource allocation, business development and organizational growth.

## 4.3 Shared Simulation Rules

Both modes will use the same underlying business systems, operational processes and organizational architecture.

The difference will primarily be the starting state of the organization, its finances, employees, infrastructure, relationships and accumulated data.

# 5. Target Experience

The experience will combine three perspectives.

## 5.1 CEO Perspective

The player initially assumes the role of Chief Executive Officer.

Responsibilities include:

* Establishing or managing the organization.
* Hiring and assigning employees.
* Establishing departments.
* Approving budgets and investments.
* Acquiring providers and subscribers.
* Monitoring organizational performance.
* Setting business objectives.
* Approving new products.
* Managing business risks.
* Making strategic decisions.

The CEO will have access to an executive dashboard showing overall company performance.

## 5.2 Departmental Worker Perspective

The player must also be able to perform the actual responsibilities of other employees.

Examples:

**Data Officer**

* Receive institutional submissions.
* Inspect incoming files.
* Run validation procedures.
* Clean records.
* Identify duplicates.
* Resolve data quality issues.
* Prepare clean records for database loading.

**Finance Officer**

* Record transactions.
* Prepare journal entries.
* Process invoices.
* Reconcile accounts.
* Manage receivables and payables.
* Prepare financial statements.

**Analytics Officer**

* Query bureau datasets.
* Analyze credit portfolios.
* Develop analytical reports.
* Build and evaluate credit scoring models.
* Monitor model performance.

**Sales Officer**

* Identify potential clients.
* Manage prospects.
* Prepare proposals.
* Negotiate contracts.
* Onboard subscribers.

**IT Officer**

* Configure infrastructure.
* Monitor servers.
* Manage storage and availability.
* Investigate technical incidents.

These tasks must be functional activities, not merely animations or fictional progress bars.

## 5.3 Organizational Observer Perspective

Players should be able to observe the office and see the organization operating.

Employees should move around, interact with their environments, perform assigned activities and respond to events.

The player should be able to inspect employees, desks, departments, infrastructure and important organizational objects.

# 6. Visual and Interaction Design

## 6.1 Visual Perspective

The simulator will use an isometric 3D office environment.

The visual experience should resemble a modern business office, with recognizable workspaces and organizational structures.

## 6.2 Initial Office Structure

The initial organization will operate from a three-floor office.

**Ground Floor**

* Reception.
* Customer Support.
* Sales and Business Development.
* Finance and Accounting.
* Human Resources.
* Cafeteria.

**First Floor**

* Data Operations.
* Data Analytics.
* IT and Infrastructure.
* Product Development.
* Server Room.

**Second Floor**

* CEO Office.
* Boardroom.
* Executive Meeting Rooms.
* Risk and Compliance.

## 6.3 Interactive Objects

The environment should include:

* Employees.
* Workstations and computers.
* Department entrances.
* Meeting rooms.
* Server racks.
* CEO desk.
* Reception desk.
* Notice boards.
* Cafeteria.
* Office equipment.

Selecting an object should reveal relevant information or available actions.

For example, selecting the server room should reveal server utilization, storage, availability and maintenance status.

# 7. Initial Organization

The established bureau scenario will begin with an illustrative 45 employees distributed across ten departments.

| Department                     | Initial Employees |
| ------------------------------ | ----------------: |
| Executive Management           |                 3 |
| Data Operations                |                 9 |
| Data Analytics                 |                 5 |
| IT and Infrastructure          |                 5 |
| Sales and Business Development |                 5 |
| Finance and Accounting         |                 4 |
| Risk and Compliance            |                 3 |
| HR and Administration          |                 4 |
| Customer Support               |                 4 |
| Product Development            |                 3 |
| **Total**                      |            **45** |

These numbers are starting assumptions, not permanent limits.

In Startup Mode, the player will recruit employees progressively.

# 8. Departmental Requirements

Each department must have defined responsibilities, employees, workflows, performance indicators and dependencies on other departments.

### 8.1 Executive Management

* Corporate strategy.
* Organizational performance.
* Budget approvals.
* Departmental oversight.
* Strategic partnerships.
* Business expansion.

### 8.2 Data Operations

* Data acquisition.
* Submission tracking.
* Structural validation.
* Data cleansing.
* Duplicate detection.
* Customer and account referencing.
* Accepted and unloadable record management.
* Database loading coordination.

### 8.3 Data Analytics

* Portfolio analysis.
* Credit risk analysis.
* Customer analytics.
* Credit scoring.
* Model development and validation.
* Model monitoring.
* Analytical product development.

### 8.4 IT and Infrastructure

* Servers and databases.
* Network infrastructure.
* System availability.
* Backups.
* Security controls.
* Technical support.
* Infrastructure upgrades.

### 8.5 Sales and Business Development

* Provider acquisition.
* Subscriber acquisition.
* Client relationship management.
* Proposals and contracts.
* Revenue generation.
* Market expansion.

### 8.6 Finance and Accounting

* General ledger.
* Accounts receivable.
* Accounts payable.
* Payroll.
* Bank reconciliation.
* Budgeting.
* Financial reporting.
* Cash flow management.

### 8.7 Risk and Compliance

* Regulatory monitoring.
* Internal controls.
* Data access oversight.
* Compliance reviews.
* Audit management.
* Incident management.
* Policy enforcement.

### 8.8 Human Resources and Administration

* Recruitment.
* Employee onboarding.
* Compensation.
* Performance reviews.
* Training.
* Employee welfare.
* Office administration.

### 8.9 Customer Support

* Customer enquiries.
* Complaints.
* Report-related issues.
* Subscriber support.
* Issue escalation.
* Resolution tracking.

### 8.10 Product Development

* Existing product improvement.
* New product development.
* Product testing.
* Product pricing proposals.
* Product performance monitoring.
* Coordination with Analytics, IT and Sales.

# 9. Credit Bureau Operations

The simulator must represent the actual information lifecycle of a credit bureau.

## 9.1 Data Providers

The initial simulation will include five fictional institutions:

* Atlas Bank.
* Meridian Bank.
* Unity Savings.
* SwiftCash.
* Horizon Finance.

These institutions will submit synthetic consumer and business credit information.

Each institution should have:

* Unique institution code.
* Submission schedule.
* Data templates.
* Contact persons.
* Submission history.
* Data quality performance.
* Service agreement.
* Institutional profile.

## 9.2 Data Submission Process

1. Financial institution generates a submission.
2. Submission arrives through a simulated secure transfer process.
3. The bureau registers the incoming file.
4. Structural validation is performed.
5. Records are cleaned and standardized.
6. Duplicate detection and referencing are performed.
7. Records are classified as accepted or unloadable.
8. Accepted records are prepared for database loading.
9. Database loading is confirmed.
10. Submission statistics and audit records are updated.

## 9.3 Data Processing Requirements

The processing engine must perform real operations on synthetic datasets.

It should support:

* Excel and CSV ingestion.
* Template validation.
* Mandatory field validation.
* Identifier validation.
* Phone number standardization.
* Duplicate detection.
* Customer referencing.
* Account referencing.
* Error classification.
* Clean and unloadable output generation.
* Processing summaries.

Original submissions must be preserved, with traceable processing history.

## 9.4 Bureau Database

The bureau database must distinguish between:

* Customers.
* Businesses.
* Credit facilities.
* Credit accounts.
* Financial institutions.
* Branches.
* Monthly account observations.
* Repayment histories.
* Enquiries.
* Guarantors.
* Legal records.
* Submission records.

A customer must not become a new customer simply because another monthly file is submitted.

An existing credit account must retain its identity across monthly observations.

# 10. Analytics and Credit Scoring

The Analytics department should work with accumulated synthetic credit history.

Initial capabilities:

* Portfolio distribution.
* Outstanding balances.
* Delinquency analysis.
* Repayment performance.
* Default rates.
* Customer segmentation.
* Facility analysis.
* Institutional benchmarking.

## 10.1 Credit Scoring

The simulator should introduce a credit scoring framework.

The initial approach should use an interpretable statistical model, such as logistic regression, followed by scorecard development and validation.

Players should be able to:

* Select historical data.
* Prepare model datasets.
* Engineer features.
* Train models.
* Evaluate predictive performance.
* Review model limitations.
* Deploy approved model versions.
* Monitor model performance.

Sensitive personal characteristics should not automatically become scoring inputs. They may be used in appropriate fairness and bias assessments.

# 11. Products and Revenue

Initial products:

1. Individual Credit Reports.
2. Business Credit Reports.
3. Batch Credit Enquiries.

Future products may include:

* Portfolio Monitoring.
* Credit Scoring as a Service.
* Risk Analytics.
* Portfolio Benchmarking.
* Fraud and Identity Risk Indicators.
* Custom Analytical Reports.

Each product should have a description, target customer, pricing, production requirements, operational costs, revenue history and performance indicators.

Players should be able to develop new products and determine whether they are commercially viable.

# 12. Finance and Company Performance

The organization must maintain a functioning financial system.

It should support:

* Chart of accounts.
* Double-entry bookkeeping.
* General ledger.
* Journal entries.
* Accounts receivable.
* Accounts payable.
* Payroll.
* Fixed assets.
* Bank accounts.
* Reconciliation.
* Budgeting.
* Profit and loss statements.
* Balance sheets.
* Cash flow statements.

Business activities must have financial consequences.

For example, purchasing additional server capacity should create an expense or asset transaction, depending on the accounting treatment.

Acquiring a new subscriber should eventually generate revenue through applicable products and contracts.

# 13. Employee Simulation

Employees should have individual attributes:

* Employee identification.
* Department.
* Job title.
* Skills.
* Experience.
* Salary.
* Productivity.
* Workload.
* Availability.
* Performance.
* Training history.
* Morale.

Employees should receive tasks based on their assigned roles.

Their performance should influence departmental output, service quality and company performance.

Players should be able to recruit, train, promote, reassign and manage employees.

# 14. Simulation Mechanics

The simulator should operate on an internal business clock.

Proposed time conversion:

| Game Time    | Simulated Time   |
| ------------ | ---------------- |
| 1 game hour  | 1 simulated hour |
| 1 game day   | 1 business day   |
| 1 game week  | 5 business days  |
| 1 game month | 20 business days |

The player should be able to:

* Pause and resume the simulation.
* Progress at different speeds.
* Review historical events.
* Monitor task queues.
* Respond to unexpected events.

Possible events include:

* Late provider submissions.
* Poor-quality data.
* Server outages.
* New business opportunities.
* Regulatory reviews.
* Customer complaints.
* Employee resignations.
* Unexpected expenses.
* Infrastructure failures.

# 15. External Economic Environment

The simulator will use a **progressively realistic economic model**.

Economic complexity will increase as the player advances.

### Initial stage

* Basic operating expenses.
* Salaries.
* Rent.
* Equipment purchases.
* Product prices.
* Revenue and cash flow.

### Intermediate stage

* Inflation.
* Changing supplier costs.
* Market demand.
* Interest rates.
* Cost of borrowing.
* Customer purchasing power.
* Wage adjustments.

### Advanced stage

* Economic cycles.
* Market competition.
* Currency fluctuations.
* Financing conditions.
* Regulatory changes.
* Economic shocks.
* Industry-wide changes in credit demand and default rates.

Economic events must affect the organization through defined rules rather than arbitrary changes.

Players should be able to review economic indicators and understand how they affect business decisions.

# 16. Cross-Department Workflows

Departments must operate as an interconnected organization.

Example: A new bank becomes a subscriber.

1. Sales negotiates and secures the agreement.
2. Finance establishes billing and customer records.
3. IT configures the required integration.
4. Data Operations receives and processes the bank's first submission.
5. Analytics incorporates the new data into portfolio analysis.
6. Customer Support handles subsequent enquiries and issues.
7. Executive Management monitors the relationship and its contribution to company performance.

No department should operate as an isolated mini-game.

# 17. Objectives, Achievements and Game Progression

The simulator will support both open-ended play and structured objectives.

### 17.1 Open-ended Mode

Players can operate their bureau indefinitely.

There is no mandatory final victory condition.

The player determines what success means, whether that is profitability, market share, product innovation, data quality, operational excellence or organizational size.

### 17.2 Objective-Based Progression

Players can pursue optional and structured milestones.

Examples:

* Establish the first operational department.
* Sign the first data provider.
* Process the first successful submission.
* Reach a specified data quality target.
* Launch the first credit report product.
* Acquire the first paying subscriber.
* Reach operational profitability.
* Develop a validated credit scoring model.
* Expand into another market.

Achievements should recognize meaningful business and operational milestones.

### 17.3 Performance Evaluation

The game should track:

* Financial health.
* Data quality.
* Provider relationships.
* Subscriber growth.
* Operational efficiency.
* Employee performance.
* Product performance.
* Compliance and governance.

These indicators should help players understand the quality of their decisions without forcing every player into one definition of success.

# 18. Difficulty Settings

Players will be able to select their preferred difficulty.

### Beginner

* More starting resources.
* Lower operating costs.
* More forgiving deadlines.
* Simpler economic conditions.
* Guided tutorials.
* More opportunities to correct mistakes.

### Intermediate

* Moderate starting resources.
* Realistic operating expenses.
* Meaningful deadlines.
* More complex departmental workflows.
* Moderate economic uncertainty.
* Greater responsibility for employee management.

### Expert

* Tighter budgets.
* More demanding operational requirements.
* Complex economic conditions.
* Stricter deadlines.
* Greater consequences for poor decisions.
* More complex compliance and risk scenarios.

Difficulty should affect the simulation environment and challenge level, not remove the underlying business logic.

# 19. Multiplayer Requirements

Multiplayer is a planned Version 2 objective.

The architecture must anticipate multiple human players working in the same virtual organization.

### Version 1: Single-player

* One primary player.
* Player begins as CEO.
* Player can switch into departmental roles.
* Other employees are controlled by the simulation.
* Organizational data is shared across all departments.
* Departmental activities affect the same company state.

### Version 2: Multiplayer

* Multiple users can join one bureau.
* Each user can be assigned an employee and department.
* Players share organizational information.
* Players collaborate on workflows.
* Tasks can be assigned and claimed.
* Departmental changes synchronize across the organization.
* Role permissions control access to sensitive actions.
* Real-time notifications and communication are supported.

The system must distinguish between a user account, an employee record and an organizational role.

A player's ability to control an employee must be governed by authorization rules.

# 20. User Experience and Navigation

The application will provide two connected interfaces.

### 20.1 3D Office Interface

Used for:

* Navigating the office.
* Inspecting employees.
* Selecting departments.
* Interacting with office objects.
* Observing organizational activities.

### 20.2 Management Interface

Used for:

* Dashboards.
* Data processing.
* Financial operations.
* Analytics.
* Employee management.
* Sales and client management.
* Infrastructure monitoring.
* Compliance and auditing.

Players should be able to move between the two interfaces without losing context.

# 21. Technology Direction

| Layer                 | Technology                   |
| --------------------- | ---------------------------- |
| Frontend              | React                        |
| 3D Environment        | Three.js / React Three Fiber |
| UI Styling            | Tailwind CSS                 |
| Backend               | Django REST Framework        |
| Primary Database      | Microsoft SQL Server         |
| Data Processing       | Python, Pandas, NumPy        |
| Machine Learning      | Scikit-learn                 |
| Background Tasks      | Celery and Redis             |
| Real-time Multiplayer | Django Channels / WebSockets |
| Containerization      | Docker                       |
| Version Control       | Git and GitHub               |

The backend should initially use a modular monolith architecture.

This keeps the first version manageable while allowing individual business capabilities to be separated later if required.

# 22. Data, Security and Governance

The simulator will use synthetic data.

It must not depend on real customer credit records or expose actual personal information.

The simulated environment should incorporate relevant Ghanaian credit reporting and data protection principles, including concepts associated with:

* Credit Reporting Act, 2007 (Act 726).
* Data Protection Act, 2012 (Act 843).
* Bank of Ghana regulatory oversight.

The simulator should include:

* User authentication.
* Role-based access control.
* Audit trails.
* Data access permissions.
* Consent and permissible-purpose concepts.
* Correction and dispute workflows.
* Data retention policies.
* Backup and recovery procedures.

These features are educational simulations and should not be represented as proof of regulatory compliance.

# 23. Scope and Release Strategy

## Version 1 – Complete Single-Player Bureau

The first full release should include:

* A functioning 3D office.
* Established Bureau and Startup starting modes.
* Initial organization and departments.
* Employee management.
* Provider management.
* Synthetic data generation.
* Data submission and processing.
* Bureau database.
* Analytics and scoring.
* Initial products.
* Finance and accounting.
* Sales and customer management.
* IT and infrastructure simulation.
* Compliance workflows.
* Employee task simulation.
* CEO dashboard.
* Departmental role switching.
* Open-ended and objective-based play.
* Selectable difficulty.
* Progressive economic simulation.

## Version 2 – Multiplayer Bureau

The multiplayer release should introduce:

* Multiple human players.
* Shared organizational state.
* Employee-to-player assignment.
* Real-time synchronization.
* Collaborative departmental workflows.
* Task ownership and delegation.
* Communication and notifications.
* Multiplayer permissions and controls.

## Future Expansion

Potential future features:

* Multiple competing credit bureaus.
* Industry-wide competition.
* Market share.
* Advanced products.
* Multiple office locations.
* International expansion.
* More complex financial and regulatory scenarios.

# 24. Non-Functional Requirements

**Modular:** Business functions should be separated into manageable components.

**Reliable:** Financial and credit data operations must maintain transactional integrity.

**Auditable:** Important changes and transactions must be traceable.

**Scalable:** The architecture should accommodate additional employees, institutions, datasets and players.

**Performant:** Large synthetic datasets should be processed efficiently.

**Secure:** Access should be restricted according to organizational responsibilities.

**Maintainable:** Code should be documented, tested and version-controlled.

**Extensible:** New products, departments, game mechanics and multiplayer capabilities should be addable without redesigning the entire platform.

# 25. Success Criteria

The first full release will be considered successful when:

1. A player can establish or manage a functioning virtual credit bureau.
2. The player can navigate the 3D office and interact with departments.
3. Synthetic institutions can submit credit data.
4. The system can genuinely validate, clean and process submissions.
5. Accepted records can be loaded into the bureau database.
6. Historical customer and account information can be maintained.
7. Analytics can be performed on accumulated credit information.
8. Credit scoring models can be developed and evaluated.
9. Products can be sold and revenue recorded.
10. Financial statements can be generated from recorded transactions.
11. Employees can perform simulated departmental tasks.
12. Departments can exchange information through connected workflows.
13. The player can switch between CEO and departmental roles.
14. The player can choose different starting experiences and difficulty settings.
15. The economic environment can progressively introduce more complex conditions.
16. The architecture can support the planned multiplayer expansion.

# 26. Final Product Definition

The Credit Bureau Simulator is not intended to be merely an office-management game.

It is a functional business simulation in which the player operates a credit bureau through realistic data, financial, technical, analytical and commercial processes.

It offers two starting experiences, flexible success conditions, selectable difficulty and an economic environment that becomes more sophisticated as the player advances.

Its distinguishing feature is the connection between the virtual organization and the actual work performed within it.

**The player does not simply manage a credit bureau. The player operates one.**

---

## DOCUMENT CONTROL

| Field         | Value                                                                                  |
| ------------- | -------------------------------------------------------------------------------------- |
| Document ID   | CBS-PRD-001                                                                            |
| Version       | 1.0                                                                                    |
| Status        | Final – Approved Product Baseline                                                      |
| Supersedes    | Version 0.1                                                                            |
| Next Document | CBS-FS-001 – Functional Specification                                                  |
| Change Policy | Material changes to product scope must be recorded in a subsequent version of this PRD |
