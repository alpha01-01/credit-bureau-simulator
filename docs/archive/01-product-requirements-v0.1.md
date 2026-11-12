# CREDIT BUREAU SIMULATOR

## Product Requirements Document (PRD)

**Document Version:** 0.1
**Status:** Initial Draft
**Product Type:** Business Simulation / Management Simulator / Interactive 3D Environment
**Initial Market Setting:** Ghana
**Primary Currency:** Ghana Cedi (GHS)
**Initial Game Mode:** Single-player
**Long-term Game Mode:** Multiplayer
**Working Project Name:** Credit Bureau Simulator

---

# 1. Executive Summary

The Credit Bureau Simulator is an interactive business simulation platform in which players establish, operate, manage and grow a virtual credit bureau.

The product combines a realistic credit bureau's operational environment with business management and game mechanics.

Players will manage a functioning virtual organization, overseeing departments such as Data Operations, Analytics, Finance, Sales, IT, Risk and Compliance, Human Resources, Customer Support and Product Development.

Unlike conventional business simulation games, the Credit Bureau Simulator will incorporate actual business processes and technical operations.

For example, the Data Operations department will receive synthetic credit data from financial institutions, validate submitted files, identify errors and duplicates, clean records and prepare accepted data for loading into the bureau database.

The Analytics department will use accumulated credit information to produce portfolio reports, develop analytical models and generate credit scores.

The Finance department will maintain accounting records, process transactions, manage expenses and prepare financial statements.

The ultimate objective is to create a virtual organization whose departments operate together as a connected business.

The product will initially launch as a single-player simulation, with an architecture designed to support a multiplayer environment in a future version.

# 2. Product Vision

To create a realistic, interactive environment where players can learn how a credit bureau operates by actually running one.

The simulator should provide an experience that combines:

* Business ownership and executive decision-making.
* Realistic departmental responsibilities.
* Practical data processing and database operations.
* Credit risk analytics and product development.
* Financial and operational management.
* Employee management and organizational growth.
* Collaboration and competition in future multiplayer modes.

The player should not simply observe employees working. The player should be able to participate in the actual work.

# 3. Product Objectives

The product should achieve the following objectives.

### 3.1 Operational realism

Represent the essential processes of a functioning credit bureau, including data acquisition, validation, storage, analysis, reporting and commercial service delivery.

### 3.2 Practical learning

Allow players to interact with realistic business tasks rather than relying exclusively on simplified game controls.

### 3.3 Organizational management

Give players responsibility for employees, departments, infrastructure, budgets, business relationships and company performance.

### 3.4 Technical engagement

Incorporate practical data operations, SQL, Python-based processing, analytics and reporting into gameplay.

### 3.5 Business growth

Allow players to develop new products, attract financial institutions, acquire subscribers, increase revenue and expand operations.

### 3.6 Multiplayer readiness

Establish the underlying architecture necessary to support multiple players working in the same organization in a future release.

# 4. Target Experience

The experience will combine three perspectives.

### 4.1 CEO perspective

The player initially assumes the role of the Chief Executive Officer.

The CEO is responsible for:

* Establishing the organization.
* Hiring and assigning employees.
* Establishing departments.
* Approving budgets and investments.
* Acquiring providers and subscribers.
* Monitoring organizational performance.
* Setting business objectives.
* Approving new products.
* Managing business risks.
* Making strategic decisions.

The CEO should have access to an executive dashboard showing the organization's overall performance.

### 4.2 Departmental worker perspective

Players must also be able to perform the actual responsibilities of other employees.

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
* Onboard new subscribers.

**IT Officer**

* Configure infrastructure.
* Monitor servers.
* Manage storage and system availability.
* Investigate technical incidents.

These tasks should be functional activities, not merely animations or fictional progress bars.

### 4.3 Organizational observer perspective

The player should be able to observe the office and see the organization operating.

Employees should move around, interact with their environments, perform assigned activities and respond to events.

The player should be able to inspect employees, desks, departments, infrastructure and important organizational objects.

# 5. Visual and Interaction Design

### 5.1 Visual perspective

The simulator will use an isometric 3D office environment.

The visual experience should resemble a modern business office, with recognizable workspaces and organizational structures.

### 5.2 Initial office structure

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

### 5.3 Interactive objects

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

# 6. Initial Organization

The simulator will begin with an illustrative Ghanaian credit bureau.

The initial company will have approximately 45 employees distributed across ten departments.

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

The player should eventually be able to recruit employees, restructure departments and expand the organization.

# 7. Departmental Requirements

Each department must have defined responsibilities, employees, workflows, performance indicators and dependencies on other departments.

### 7.1 Executive Management

Responsible for:

* Corporate strategy.
* Organizational performance.
* Budget approvals.
* Departmental oversight.
* Strategic partnerships.
* Business expansion.

### 7.2 Data Operations

Responsible for:

* Provider onboarding from a data perspective.
* Data acquisition.
* Submission tracking.
* Structural validation.
* Data cleansing.
* Duplicate detection.
* Customer and account referencing.
* Accepted and unloadable record management.
* Database loading coordination.

This department is central to the simulator.

### 7.3 Data Analytics

Responsible for:

* Portfolio analysis.
* Credit risk analysis.
* Customer analytics.
* Credit scoring.
* Model development.
* Model validation.
* Model monitoring.
* Analytical product development.

### 7.4 IT and Infrastructure

Responsible for:

* Servers.
* Databases.
* Network infrastructure.
* System availability.
* Backups.
* Security controls.
* Technical support.
* Infrastructure upgrades.

### 7.5 Sales and Business Development

Responsible for:

* Provider acquisition.
* Subscriber acquisition.
* Client relationship management.
* Proposals and contracts.
* Revenue generation.
* Market expansion.

### 7.6 Finance and Accounting

Responsible for:

* General ledger.
* Accounts receivable.
* Accounts payable.
* Payroll.
* Bank reconciliation.
* Budgeting.
* Financial reporting.
* Cash flow management.

### 7.7 Risk and Compliance

Responsible for:

* Regulatory monitoring.
* Internal controls.
* Data access oversight.
* Compliance reviews.
* Audit management.
* Incident management.
* Policy enforcement.

### 7.8 Human Resources and Administration

Responsible for:

* Recruitment.
* Employee onboarding.
* Compensation.
* Performance reviews.
* Training.
* Employee welfare.
* Office administration.

### 7.9 Customer Support

Responsible for:

* Customer enquiries.
* Complaints.
* Report-related issues.
* Subscriber support.
* Issue escalation.
* Resolution tracking.

### 7.10 Product Development

Responsible for:

* Existing product improvement.
* New product development.
* Product testing.
* Product pricing proposals.
* Product performance monitoring.
* Coordination with Analytics, IT and Sales.

# 8. Credit Bureau Operations

The simulator must represent the actual information lifecycle of a credit bureau.

### 8.1 Data providers

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

### 8.2 Data submission process

The operational workflow will be:

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

### 8.3 Data processing requirements

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

The system must preserve original submissions and maintain traceable processing history.

### 8.4 Bureau database

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

Likewise, an existing credit account must retain its identity across monthly observations.

# 9. Analytics and Credit Scoring

The Analytics department should be capable of working with accumulated synthetic credit history.

Initial capabilities:

* Portfolio distribution.
* Outstanding balances.
* Delinquency analysis.
* Repayment performance.
* Default rates.
* Customer segmentation.
* Facility analysis.
* Institutional benchmarking.

### 9.1 Credit scoring

The simulator should introduce a credit scoring framework.

The initial approach should use an interpretable statistical model, such as logistic regression, followed by scorecard development and validation.

Players should be able to:

* Select relevant historical data.
* Prepare model datasets.
* Engineer features.
* Train models.
* Evaluate predictive performance.
* Review model limitations.
* Deploy approved model versions.
* Monitor model performance.

Sensitive personal characteristics should not automatically become scoring inputs. They may be used in appropriate fairness and bias assessments.

# 10. Products and Revenue

The organization must have a commercial model.

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

Each product should have:

* Description.
* Target customer.
* Pricing.
* Production requirements.
* Operational costs.
* Revenue history.
* Product performance.

Players should be able to develop new products and determine whether they are commercially viable.

# 11. Finance and Company Performance

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

Acquiring a new subscriber should eventually generate revenue through the applicable products and contracts.

# 12. Employee Simulation

Employees should have individual attributes.

These include:

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

The player should be able to recruit, train, promote, reassign and manage employees.

# 13. Simulation Mechanics

The simulator should operate on an internal business clock.

Proposed time conversion:

| Game Time    | Simulated Time   |
| ------------ | ---------------- |
| 1 game hour  | 1 simulated hour |
| 1 game day   | 1 business day   |
| 1 game week  | 5 business days  |
| 1 game month | 20 business days |

The player should be able to:

* Pause the simulation.
* Resume the simulation.
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

# 14. Cross-Department Workflows

Departments must operate as an interconnected organization.

For example:

**A new bank becomes a subscriber.**

1. Sales negotiates and secures the agreement.
2. Finance establishes billing and customer records.
3. IT configures the required integration.
4. Data Operations receives and processes the bank's first submission.
5. Analytics incorporates the new data into portfolio analysis.
6. Customer Support handles subsequent enquiries and issues.
7. Executive Management monitors the relationship and its contribution to company performance.

No department should operate as an isolated mini-game.

# 15. Multiplayer Requirements

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
* Players can collaborate on workflows.
* Tasks can be assigned and claimed.
* Departmental changes synchronize across the organization.
* Role permissions control access to sensitive actions.
* Real-time notifications and communication are supported.

The system must distinguish between a user account, an employee record and an organizational role.

A player's ability to control an employee must be governed by authorization rules.

# 16. User Experience and Navigation

The application should provide two connected interfaces.

### 16.1 3D office interface

Used for:

* Navigating the office.
* Inspecting employees.
* Selecting departments.
* Interacting with office objects.
* Observing organizational activities.

### 16.2 Management interface

Used for:

* Dashboards.
* Data processing.
* Financial operations.
* Analytics.
* Employee management.
* Sales and client management.
* Infrastructure monitoring.
* Compliance and auditing.

The player should be able to move between the two interfaces without losing context.

# 17. Technology Direction

The proposed technology stack is:

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

# 18. Data, Security and Governance

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

# 19. Scope and Release Strategy

### Version 1 — Complete Single-Player Bureau

The first full release should include:

* A functioning 3D office.
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

### Version 2 — Multiplayer Bureau

The multiplayer release should introduce:

* Multiple human players.
* Shared organizational state.
* Employee-to-player assignment.
* Real-time synchronization.
* Collaborative departmental workflows.
* Task ownership and delegation.
* Communication and notifications.
* Multiplayer permissions and controls.

### Future Expansion

Potential future features:

* Multiple competing credit bureaus.
* Industry-wide competition.
* Market share.
* Advanced products.
* Multiple office locations.
* International expansion.
* More complex financial and regulatory scenarios.

# 20. Non-Functional Requirements

The system should be:

**Modular:** Business functions should be separated into manageable components.

**Reliable:** Financial and credit data operations must maintain transactional integrity.

**Auditable:** Important changes and transactions must be traceable.

**Scalable:** The architecture should accommodate additional employees, institutions, datasets and players.

**Performant:** Large synthetic datasets should be processed efficiently.

**Secure:** Access should be restricted according to organizational responsibilities.

**Maintainable:** Code should be documented, tested and version-controlled.

**Extensible:** New products, departments, game mechanics and multiplayer capabilities should be addable without redesigning the entire platform.

# 21. Success Criteria

The first full release will be considered successful when:

1. A player can establish and manage a functioning virtual credit bureau.
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
14. The architecture can support the planned multiplayer expansion.

# 22. Assumptions and Open Decisions

The following are initial assumptions to be validated during project design:

* The initial bureau will operate in a Ghanaian business environment.
* GHS will be the default currency.
* All customer and institutional records will be synthetic.
* The starting organization will have approximately 45 employees.
* The initial office will have three floors.
* The first release will be single-player.
* Multiplayer will be designed for from the beginning but implemented in Version 2.
* The system will use Microsoft SQL Server as its primary database.
* The simulator will prioritize operational realism over purely decorative gameplay.

Further decisions to make during the design process include:

* Whether players can create their own bureau or begin with a predefined company.
* How much financial capital the initial bureau receives.
* Whether the game has a defined victory condition or an open-ended business mode.
* How realistic the external economic environment should become.
* Whether competing bureaus will eventually operate in the same market.

# 23. Product Definition

The Credit Bureau Simulator is not intended to be merely an office-management game.

It is a functional business simulation in which the player operates a credit bureau through realistic data, financial, technical, analytical and commercial processes.

Its distinguishing feature is the connection between the virtual organization and the actual work performed within it.

**The player does not simply manage a credit bureau. The player operates one.**
