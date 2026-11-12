# CREDIT BUREAU SIMULATOR

## DOCUMENT 03 — TECHNICAL ARCHITECTURE AND SYSTEM DESIGN

**Document ID:** CBS-TAD-001
**Version:** 0.1
**Status:** Initial Technical Architecture
**Parent Document:** CBS-PRD-001 and CBS-FS-001
**Product:** Credit Bureau Simulator
**Architecture Style:** Modular Monolith
**Primary Database:** Microsoft SQL Server
**Initial Release:** Single-player
**Future Release:** Multiplayer

---

# 1. PURPOSE

This document defines the technical structure of the Credit Bureau Simulator.

It establishes:

* Application architecture.
* Frontend and backend technologies.
* Database architecture.
* Backend module boundaries.
* API communication.
* Data processing infrastructure.
* Simulation engine architecture.
* Security and permissions.
* Multiplayer readiness.
* Development and deployment environments.
* Testing and performance requirements.

The objective is to create an architecture that supports a fully functioning credit bureau simulation while remaining manageable for incremental development.

# 2. ARCHITECTURAL PRINCIPLES

The system will follow eight fundamental principles.

### 2.1 Modular design

Each major business function must have its own logical module.

Data Operations, Finance, Analytics, HR and other departments must not be tightly coupled to one another.

### 2.2 Centralized business logic

Important business rules must be implemented in the backend.

The frontend must not independently determine whether a financial transaction is valid or whether a credit record can be loaded.

### 2.3 Database integrity

Customer records, credit accounts, financial transactions and organizational records must maintain consistent relationships.

### 2.4 Real processing

Where an activity represents an actual business operation, the system must execute the corresponding operation.

### 2.5 Server-authoritative simulation

The backend controls the official simulation clock, employee tasks, events and organizational state.

### 2.6 Auditability

Important business operations must produce traceable records.

### 2.7 Extensibility

New departments, products, providers, business rules and game features should be introduced without redesigning the entire application.

### 2.8 Multiplayer readiness

Version 1 must establish the necessary user, employee, organization and permission structures for Version 2.

# 3. PROPOSED TECHNOLOGY STACK

| Component               | Technology                                    | Responsibility                           |
| ----------------------- | --------------------------------------------- | ---------------------------------------- |
| Frontend                | React                                         | Application interface                    |
| 3D Environment          | Three.js                                      | 3D rendering                             |
| React 3D Integration    | React Three Fiber                             | 3D scene management                      |
| UI Styling              | Tailwind CSS                                  | Interface styling                        |
| Backend                 | Django                                        | Business logic and application services  |
| API                     | Django REST Framework                         | Frontend/backend communication           |
| Primary Database        | Microsoft SQL Server                          | Persistent business data                 |
| Database Integration    | Django ORM and SQL                            | Database operations                      |
| Data Processing         | Python, Pandas, NumPy                         | Data validation and cleansing            |
| Machine Learning        | Scikit-learn                                  | Credit scoring and predictive models     |
| Background Processing   | Celery                                        | Asynchronous jobs                        |
| Message Broker          | Redis                                         | Task queues and temporary coordination   |
| Real-time Communication | Django Channels                               | Future multiplayer synchronization       |
| File Storage            | Local storage initially; object storage later | Uploaded submissions and generated files |
| Containerization        | Docker                                        | Consistent development and deployment    |
| Version Control         | Git and GitHub                                | Source and documentation management      |

The selected SQL Server preference will remain central to the database design.

Exact framework and driver versions will be pinned and tested during environment setup, especially Django-to-SQL Server compatibility.

# 4. HIGH-LEVEL SYSTEM ARCHITECTURE

The system will have six major technical layers.

1. Presentation Layer.
2. Application/API Layer.
3. Business Logic Layer.
4. Data Processing and Simulation Layer.
5. Persistence Layer.
6. Infrastructure Layer.

## 4.1 Architecture Diagram

```text
                  PLAYER
                    |
                    v
        +--------------------------+
        |      REACT FRONTEND      |
        |                          |
        |  Management Interface    |
        |  3D Office Environment   |
        |  Department Workspaces   |
        +------------+-------------+
                     |
                 HTTP / REST
                     |
                     v
        +--------------------------+
        |    DJANGO REST API       |
        |                          |
        | Authentication           |
        | Permissions              |
        | API Validation           |
        | Request Handling         |
        +------------+-------------+
                     |
                     v
        +--------------------------+
        |     BUSINESS MODULES     |
        |                          |
        | Organization             |
        | Employees                |
        | Data Operations          |
        | Bureau Database          |
        | Analytics                |
        | Finance                  |
        | Sales                    |
        | HR                       |
        | IT                       |
        | Compliance               |
        | Products                 |
        | Simulation               |
        +------------+-------------+
                     |
           +---------+---------+
           |                   |
           v                   v
+--------------------+  +---------------------+
| PROCESSING ENGINE  |  | SIMULATION ENGINE   |
|                    |  |                     |
| Python             |  | Game Clock          |
| Pandas             |  | AI Employees        |
| Validation         |  | Task Scheduling     |
| Cleansing          |  | Random Events       |
| Referencing        |  | Business Events     |
| Analytics          |  |                     |
+---------+----------+  +----------+----------+
          |                        |
          +------------+-----------+
                       |
                       v
        +--------------------------+
        |     DATA SERVICES        |
        |                          |
        | SQL SERVER               |
        | Raw File Storage         |
        | Redis                    |
        | Generated Reports        |
        +--------------------------+
```

This architecture represents logical components, not separate physical servers.

During Version 1, most application services will run within one deployable backend system, with background workers operating as separate processes.

# 5. FRONTEND ARCHITECTURE

The frontend will be developed using React.

It will combine a conventional management application with an interactive 3D environment.

## 5.1 Frontend Structure

The frontend will have five major areas.

### A. Core Application

Responsible for:

* Application navigation.
* Authentication screens.
* User settings.
* Notifications.
* Global state.
* Role switching.

### B. Office Environment

Responsible for:

* 3D office rendering.
* Floor navigation.
* Employee visualization.
* Workstation interactions.
* Department selection.
* Infrastructure interactions.
* Camera movement.

### C. Management Dashboard

Responsible for:

* CEO dashboard.
* Organizational performance.
* Financial indicators.
* Departmental summaries.
* Business reports.

### D. Departmental Applications

Responsible for:

* Data Operations.
* Finance.
* Analytics.
* Sales.
* HR.
* IT.
* Compliance.
* Customer Support.
* Product Development.

### E. Simulation Controls

Responsible for:

* Pause and resume.
* Simulation speed.
* Game calendar.
* Event notifications.
* Current player role.
* Current organizational status.

## 5.2 3D Environment Design

React Three Fiber will provide the connection between React and Three.js.

The 3D environment should be divided into reusable components.

Example:

```text
Office/
    Building/
        GroundFloor/
        FirstFloor/
        SecondFloor/

    Departments/
        DataOperations/
        Analytics/
        Finance/
        Sales/
        IT/
        HR/

    Objects/
        Desk/
        Computer/
        ServerRack/
        MeetingTable/
        ReceptionDesk/

    Characters/
        Employee/
        Manager/
        PlayerCharacter/

    Interactions/
        SelectObject/
        OpenDepartment/
        InspectEmployee/
```

Each department should be independently configurable.

For example, the Data Operations department should be able to display different employee counts and workstation arrangements depending on the selected game scenario.

## 5.3 Frontend State Management

The frontend must maintain application state such as:

* Logged-in user.
* Active organization.
* Active employee role.
* Current department.
* Selected employee.
* Current simulation speed.
* Open application panel.
* Notifications.

Server-owned business data must not be treated as permanently authoritative frontend state.

The frontend should refresh or reconcile its state with backend responses.

## 5.4 Frontend Navigation

The 3D office should not be the only way to access business functions.

A player should be able to open Data Operations directly through the management navigation.

This ensures the application remains practical for detailed work, especially when processing large datasets.

# 6. BACKEND ARCHITECTURE

Django and Django REST Framework will provide the backend.

The initial backend will follow a modular monolith architecture.

A modular monolith means that the application has clearly separated business modules but is initially deployed as one coordinated backend application.

This approach avoids the complexity of microservices during early development.

## 6.1 Backend Applications

The proposed Django applications are:

| Application     | Responsibility                      |
| --------------- | ----------------------------------- |
| accounts        | User authentication                 |
| organizations   | Organization and company records    |
| employees       | Employee management                 |
| departments     | Department structure                |
| providers       | Data provider management            |
| subscribers     | Subscriber management               |
| submissions     | Incoming submission records         |
| data_quality    | Validation and error management     |
| data_processing | Cleansing and processing            |
| referencing     | Customer and account matching       |
| bureau_core     | Credit bureau information           |
| analytics       | Portfolio analytics                 |
| scoring         | Credit scoring models               |
| products        | Product configuration               |
| sales           | Leads, contracts and CRM            |
| finance         | Accounting and financial operations |
| infrastructure  | Servers and IT assets               |
| compliance      | Regulatory controls and audits      |
| support         | Customer support tickets            |
| simulation      | Clock, events and AI employees      |
| tasks           | Task queues and assignments         |
| audit           | Central audit records               |
| notifications   | System notifications                |

These applications will communicate through defined service interfaces rather than importing each other's internal implementation indiscriminately.

## 6.2 Backend Responsibilities

The backend must:

* Authenticate users.
* Authorize actions.
* Validate requests.
* Apply business rules.
* Coordinate transactions.
* Execute background jobs.
* Store business records.
* Generate audit events.
* Manage simulation state.
* Provide data to the frontend.

## 6.3 Service Layer

Complex business operations should be implemented in dedicated service functions.

Examples:

```text
data_processing/
    services/
        submission_service.py
        validation_service.py
        cleansing_service.py
        duplicate_service.py
        referencing_service.py
        loading_service.py

finance/
    services/
        journal_service.py
        invoice_service.py
        payment_service.py
        reconciliation_service.py

simulation/
    services/
        clock_service.py
        employee_service.py
        task_service.py
        event_service.py
```

The API should call these services rather than contain all business logic directly inside endpoint functions.

# 7. DATABASE ARCHITECTURE

Microsoft SQL Server will serve as the primary relational database.

## 7.1 Initial Database Strategy

For Version 1, the preferred approach is one primary SQL Server database with multiple logical schemas.

This simplifies transactions and relationships across departments.

Proposed schemas:

| Schema         | Contents                                  |
| -------------- | ----------------------------------------- |
| auth           | Users and authentication-related records  |
| org            | Organizations and departments             |
| hr             | Employees and HR records                  |
| providers      | Financial institutions                    |
| submissions    | Incoming files and processing history     |
| quality        | Validation and cleansing results          |
| core           | Customers, businesses and credit accounts |
| analytics      | Analytical datasets and model metadata    |
| products       | Bureau products                           |
| sales          | Leads, contracts and subscribers          |
| finance        | Accounting and financial records          |
| infrastructure | IT assets and incidents                   |
| compliance     | Audits, disputes and controls             |
| simulation     | Clock, events and game state              |
| audit          | Audit events and system history           |

The exact mapping between Django applications and SQL schemas will be finalized during database design.

Separate databases can be introduced later if workload isolation or operational scale justifies them.

## 7.2 Database Separation

The following data categories must remain logically distinct:

**Organizational data**

* Employees.
* Departments.
* Budgets.
* Company information.

**Credit bureau data**

* Customers.
* Businesses.
* Accounts.
* Facilities.
* Monthly observations.
* Enquiries.

**Financial data**

* Chart of accounts.
* Journals.
* Invoices.
* Receipts.
* Payments.

**Simulation data**

* Game clock.
* Events.
* Employee tasks.
* Game scenarios.
* Simulation settings.

## 7.3 Database Integrity

The database must enforce:

* Primary keys.
* Foreign keys.
* Unique constraints.
* Appropriate indexes.
* Required fields.
* Valid relationships.
* Transactional consistency.

Critical financial and credit operations must use database transactions.

## 7.4 Historical Data

The system must preserve important historical records.

Examples:

* Monthly credit account observations.
* Submission processing history.
* Historical financial transactions.
* Employee movement history.
* Product pricing history.
* Model versions.

Historical information must not be silently replaced by current values.

# 8. DATA PROCESSING ARCHITECTURE

This component is central to the simulator.

The processing engine will use Python and Pandas.

## 8.1 Processing Pipeline

```text
Provider Submission
        |
        v
File Registration
        |
        v
Raw File Storage
        |
        v
Structural Validation
        |
        v
Data Cleansing
        |
        v
Duplicate Detection
        |
        v
Customer Referencing
        |
        v
Account Referencing
        |
        v
Unloadable Classification
        |
        v
Accepted Records
        |
        v
Database Loading
        |
        v
Processing Summary
```

## 8.2 Processing Components

### File Reader

Reads Excel and CSV files.

### Template Validator

Compares incoming file structures with institution-specific templates.

### Cleansing Engine

Applies configured transformation rules.

### Duplicate Engine

Identifies repeated records.

### Referencing Engine

Matches customers and credit accounts against historical records.

### Error Engine

Classifies unloadable records and stores their reasons.

### Loading Engine

Loads eligible records into SQL Server.

## 8.3 Processing Rule Configuration

Rules should be configurable rather than hardcoded wherever practical.

For example:

```text
Institution: Atlas Bank

Template: Consumer Monthly v1

Rules:
    CustomerID: Required
    FacilityAccNum: Required
    DisbursementDate: Valid Date
    PhoneNumber: Normalize
    OutstandingBalance: Numeric
    AccountStatus: Approved Values
```

Different institutions may have different templates and validation requirements.

## 8.4 Processing Isolation

Large submissions must be processed through background jobs.

A player should not have to keep a browser request open while a large Excel file is being processed.

Each processing run must have:

* A unique processing identifier.
* Start time.
* Completion time.
* Processing status.
* Error information.
* Record counts.
* Output file references.

## 8.5 Processing Recovery

If a processing job fails:

* The original file must remain available.
* The processing run must be marked appropriately.
* Partial results must not be treated as completed.
* The player must be able to investigate the failure.
* A controlled retry must be possible.

# 9. ASYNCHRONOUS PROCESSING

Celery and Redis will support long-running operations.

Potential background jobs include:

* Excel ingestion.
* Data validation.
* Data cleansing.
* Duplicate detection.
* Customer referencing.
* Database loading.
* Report generation.
* Model training.
* Payroll processing.
* Simulation events.
* AI employee task execution.

The frontend should receive task status through polling initially.

WebSocket-based notifications can be introduced where useful and expanded for multiplayer.

# 10. API ARCHITECTURE

The frontend will communicate with the backend through REST APIs.

## 10.1 API Structure

Proposed base path:

```text
/api/v1/
```

Example endpoints:

### Authentication

```text
POST /api/v1/auth/login/
POST /api/v1/auth/logout/
GET  /api/v1/auth/me/
```

### Organization

```text
GET  /api/v1/organizations/
GET  /api/v1/organizations/{id}/
POST /api/v1/organizations/
```

### Employees

```text
GET  /api/v1/employees/
POST /api/v1/employees/
GET  /api/v1/employees/{id}/
PATCH /api/v1/employees/{id}/
```

### Providers

```text
GET  /api/v1/providers/
POST /api/v1/providers/
GET  /api/v1/providers/{id}/
```

### Submissions

```text
GET  /api/v1/submissions/
POST /api/v1/submissions/
GET  /api/v1/submissions/{id}/
POST /api/v1/submissions/{id}/validate/
POST /api/v1/submissions/{id}/process/
POST /api/v1/submissions/{id}/load/
```

### Data Processing

```text
GET /api/v1/processing-runs/
GET /api/v1/processing-runs/{id}/
GET /api/v1/processing-runs/{id}/errors/
```

### Finance

```text
GET  /api/v1/finance/accounts/
POST /api/v1/finance/journals/
GET  /api/v1/finance/ledger/
GET  /api/v1/finance/reports/trial-balance/
```

### Analytics

```text
GET  /api/v1/analytics/portfolio/
POST /api/v1/analytics/reports/
POST /api/v1/scoring/models/
GET  /api/v1/scoring/models/{id}/
```

### Simulation

```text
GET  /api/v1/simulation/state/
POST /api/v1/simulation/pause/
POST /api/v1/simulation/resume/
POST /api/v1/simulation/speed/
GET  /api/v1/simulation/events/
```

These are proposed endpoint contracts. Detailed request and response schemas will be documented during API design.

## 10.2 API Response Standards

Responses should use a consistent structure.

Example successful response:

```json
{
  "success": true,
  "message": "Submission registered successfully",
  "data": {
    "submission_id": "SUB-000001",
    "status": "RECEIVED"
  }
}
```

Example error response:

```json
{
  "success": false,
  "message": "The submitted file is missing a required column",
  "errors": {
    "missing_columns": [
      "CustomerID"
    ]
  }
}
```

The API must use appropriate HTTP status codes and avoid exposing internal errors or sensitive information.

# 11. SIMULATION ENGINE ARCHITECTURE

The simulation engine controls the virtual organization's behaviour.

It must be separate from the visual rendering engine.

The browser displays the simulation; the backend determines what actually happens.

## 11.1 Simulation Clock

The backend maintains:

* Current simulated date.
* Current simulated time.
* Current simulation speed.
* Pause status.
* Active game scenario.

The simulation clock must not depend on the browser's animation frame rate.

## 11.2 Task Engine

The task engine manages:

* Task creation.
* Task assignment.
* Task priorities.
* Employee availability.
* Task dependencies.
* Task completion.
* Escalation.

Example:

```text
Task:
    Process Atlas Bank submission

Assigned Employee:
    Data Officer 001

Required Skills:
    Excel Processing
    Data Validation

Status:
    In Progress

Dependencies:
    File Received
    Submission Registered
```

## 11.3 AI Employee Engine

AI employees will be controlled by backend rules.

Their behaviour will depend on:

* Role.
* Skills.
* Experience.
* Workload.
* Availability.
* Task priority.
* Departmental requirements.

The system should not require every employee to have a complex artificial intelligence model.

A deterministic task and decision engine is sufficient initially.

## 11.4 Event Engine

The event engine will generate events according to configured rules.

Examples:

* A provider misses its submission deadline.
* A server reaches a storage threshold.
* A new sales opportunity appears.
* An employee becomes unavailable.
* A customer complaint is received.

Each event must have an impact on the appropriate business module.

# 12. EVENT-DRIVEN BUSINESS COMMUNICATION

Departments must communicate through defined business events.

Examples:

| Event               | Trigger                   | Consequence                              |
| ------------------- | ------------------------- | ---------------------------------------- |
| Contract Won        | Sales closes contract     | Finance receives billing setup task      |
| Provider Activated  | Onboarding completed      | Data Operations receives setup task      |
| Submission Received | File registered           | Validation task created                  |
| Data Loaded         | Database loading succeeds | Analytics data availability updated      |
| Invoice Issued      | Finance creates invoice   | Receivable balance updated               |
| Server Outage       | Infrastructure incident   | Affected services may become unavailable |
| Employee Hired      | HR completes onboarding   | Department receives new employee         |

For reliable event delivery, important database changes and their associated events should be coordinated transactionally.

An event must not be published as successful if the underlying business transaction failed.

# 13. SECURITY ARCHITECTURE

Security must be enforced on the backend.

## 13.1 Authentication

The system must authenticate users before allowing access to protected functionality.

The authentication mechanism should support future multiplayer accounts.

## 13.2 Authorization

Role-based access control will determine which operations a user can perform.

Examples:

* Data Officers can process submissions.
* Finance Officers can prepare financial entries.
* Finance approvers can authorize eligible postings.
* Compliance Officers can inspect audit records.
* CEOs can access organizational summaries and authorized management actions.

## 13.3 Data Protection

The application must:

* Use synthetic personal and credit information.
* Restrict access to sensitive records.
* Avoid exposing credentials in source code.
* Protect file uploads.
* Validate user inputs.
* Maintain audit logs.
* Secure API communication.
* Back up important records.

## 13.4 Financial Security

Posted transactions must not be silently overwritten.

Sensitive financial actions should require the appropriate permissions and approval process.

## 13.5 Multiplayer Security

Version 2 must support organization-level access boundaries.

A player must not access or modify another organization's information without authorization.

# 14. MULTIPLAYER-READY ARCHITECTURE

Multiplayer implementation is deferred to Version 2.

However, the following structures must exist in Version 1:

### User

Represents an authenticated account.

### Organization

Represents a virtual credit bureau.

### Employee

Represents a person working within an organization.

### Organization Membership

Connects a user to an organization.

### Employee Assignment

Connects a player to an employee they are authorized to control.

### Role and Permission

Defines available actions.

### Player Session

Tracks an active player's interaction with an organization.

### Player Activity

Records important player actions.

## 14.1 Future Real-Time Communication

Django Channels and WebSockets will support real-time updates.

Examples:

* A Data Officer completes a submission.
* The Head of Data sees the updated queue.
* The CEO dashboard receives updated figures.
* Finance receives an invoice notification.
* Another player sees the changed organizational state.

## 14.2 Shared State

The database will remain the source of truth.

WebSockets will distribute updates, not replace database transactions.

Important actions must be validated and committed on the backend.

# 15. FILE STORAGE ARCHITECTURE

Submitted files should not be stored directly inside large relational database records unless a specific requirement justifies it.

The initial system will use organized file storage.

Proposed structure:

```text
storage/
    organizations/
        organization_001/
            providers/
                atlas_bank/
                    submissions/
                        raw/
                        clean/
                        unloadable/
                        reports/
                    logs/

            generated_reports/
            exports/
            backups/
```

The database should store file metadata and storage references.

Important requirements:

* Original submissions remain unchanged.
* Processed outputs are stored separately.
* Access is permission-controlled.
* File names and identifiers are managed consistently.
* Storage paths are not exposed as unrestricted public URLs.
* File integrity can be verified using checksums.

# 16. REPORTING AND ANALYTICS ARCHITECTURE

Operational records and analytical workloads must be logically separated.

The operational database will maintain current business transactions and credit information.

The analytics module will generate analytical datasets and reporting outputs.

For Version 1, analytical queries can initially run against the same SQL Server instance, using controlled schemas and appropriately designed queries.

As the system grows, a separate analytical database or warehouse may be introduced.

## 16.1 Analytical Processing

The system should support:

* SQL-based aggregations.
* Python-based analysis.
* Pandas data preparation.
* Scikit-learn model development.
* Historical portfolio analysis.

## 16.2 Model Storage

Model metadata must be stored in SQL Server.

Model artifacts should be stored in controlled file storage.

Each deployed model must have a version and reference to its training data and evaluation results.

# 17. PROJECT DIRECTORY STRUCTURE

The proposed repository structure is:

```text
credit-bureau-simulator/
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── office/
│   │   ├── dashboards/
│   │   ├── departments/
│   │   ├── features/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── store/
│   │   ├── styles/
│   │   └── utils/
│   └── package.json
│
├── backend/
│   ├── config/
│   ├── apps/
│   │   ├── accounts/
│   │   ├── organizations/
│   │   ├── employees/
│   │   ├── departments/
│   │   ├── providers/
│   │   ├── subscribers/
│   │   ├── submissions/
│   │   ├── data_quality/
│   │   ├── data_processing/
│   │   ├── referencing/
│   │   ├── bureau_core/
│   │   ├── analytics/
│   │   ├── scoring/
│   │   ├── products/
│   │   ├── sales/
│   │   ├── finance/
│   │   ├── infrastructure/
│   │   ├── compliance/
│   │   ├── support/
│   │   ├── simulation/
│   │   ├── tasks/
│   │   ├── notifications/
│   │   └── audit/
│   │
│   ├── shared/
│   ├── requirements/
│   └── manage.py
│
├── data/
│   ├── synthetic/
│   ├── templates/
│   ├── reference/
│   └── test_datasets/
│
├── storage/
│
├── docs/
│   ├── 01_product_requirements/
│   ├── 02_functional_specification/
│   ├── 03_technical_architecture/
│   ├── 04_database_design/
│   ├── 05_game_design/
│   └── 06_development_roadmap/
│
├── tests/
│
├── scripts/
│
├── docker/
│
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml
```

The exact structure may evolve as development progresses, but the separation between frontend, backend, data, documentation and tests should remain.

# 18. DEVELOPMENT ENVIRONMENTS

The project should support three environments.

## 18.1 Development

Used by developers.

Characteristics:

* Local application instances.
* Synthetic development datasets.
* Debugging tools.
* Test database.
* Development configuration.

## 18.2 Testing

Used for:

* Automated tests.
* Integration testing.
* Database migration testing.
* Data processing verification.
* User acceptance testing.

## 18.3 Production

Used for the released simulator.

Characteristics:

* Debugging disabled.
* Protected configuration.
* Secure database access.
* Controlled file storage.
* Backups.
* Application monitoring.
* Error logging.

Configuration and secrets must be separated from source code.

# 19. TESTING ARCHITECTURE

Testing must be incorporated throughout development.

## 19.1 Unit Tests

Test individual functions.

Examples:

* Phone number cleaning.
* Duplicate detection.
* Journal balancing.
* Credit score calculations.
* Employee task assignment.

## 19.2 Integration Tests

Test communication between modules.

Examples:

* Submission registration and validation.
* Database loading and processing history.
* Sales contract and finance billing.
* Payroll and general ledger.
* Server outage and submission loading.

## 19.3 API Tests

Verify:

* Valid requests.
* Invalid requests.
* Authentication.
* Permissions.
* Response formats.
* Error handling.

## 19.4 Frontend Tests

Verify:

* Navigation.
* Role switching.
* Form validation.
* Department selection.
* Dashboard rendering.
* 3D interactions.

## 19.5 End-to-End Tests

Test complete business scenarios.

Example:

A bank submits a file, the Data Officer processes it, accepted records are loaded, analytics updates and the CEO dashboard reflects the results.

## 19.6 Data Integrity Tests

These tests must verify:

* No unintended duplicate customers.
* No unintended duplicate credit accounts.
* Historical observations remain available.
* Accounting entries balance.
* Failed transactions do not leave incomplete state.
* Processing totals reconcile.

# 20. PERFORMANCE AND RELIABILITY

The architecture must account for:

* Large Excel submissions.
* High-volume record processing.
* Database query efficiency.
* Background task queues.
* File storage growth.
* Multiple simultaneous operations.
* Simulation performance.

Long-running operations must not block ordinary user interactions.

Database indexes should be designed around actual query patterns.

Processing jobs should support controlled retries and prevent duplicate execution from creating duplicate business effects.

# 21. DEPLOYMENT ARCHITECTURE

The initial deployment should use Docker to standardize application components.

Proposed logical services:

```text
Application Environment
│
├── Frontend
│
├── Django API
│
├── Celery Worker
│
├── Celery Scheduler
│
├── Redis
│
├── SQL Server
│
└── File Storage
```

These services may initially run on one development machine.

Production deployment can separate database, application and background-processing resources as requirements grow.

# 22. ARCHITECTURAL DECISIONS AND TRADE-OFFS

| Decision                          | Reason                                        |
| --------------------------------- | --------------------------------------------- |
| Modular monolith                  | Reduces initial engineering complexity        |
| SQL Server                        | Supports relational business and credit data  |
| React                             | Supports a modular management interface       |
| React Three Fiber                 | Connects 3D office rendering to React         |
| Django REST Framework             | Provides structured backend APIs              |
| Python processing engine          | Supports data processing and machine learning |
| Celery and Redis                  | Handles long-running operations               |
| Single primary database initially | Simplifies cross-department transactions      |
| Server-authoritative simulation   | Prevents conflicting game states              |
| WebSockets in Version 2           | Supports real-time multiplayer collaboration  |

# 23. VERSION 1 IMPLEMENTATION BOUNDARIES

Version 1 will implement:

* React frontend.
* 3D office environment.
* Django backend.
* SQL Server database.
* Departmental modules.
* Data processing engine.
* Bureau database.
* Finance and accounting.
* Analytics and scoring.
* Simulation engine.
* AI employee task management.
* Audit and permissions.
* Role switching.
* Background processing.

The following are deferred to Version 2:

* Multi-user real-time collaboration.
* Shared player sessions.
* Multiplayer presence.
* Player-to-employee assignment at scale.
* Real-time cross-player communication.

The underlying data structures and service boundaries must accommodate these future capabilities.

# 24. TECHNICAL ACCEPTANCE CRITERIA

The architecture will be considered successfully established when:

1. The frontend communicates with the Django API.
2. The backend connects successfully to SQL Server.
3. Database migrations execute reliably.
4. Users can authenticate.
5. Role permissions are enforced by the backend.
6. The 3D environment can display organizational information.
7. Background processing can execute and report job status.
8. Synthetic files can be received and processed.
9. Business modules can communicate through defined service interfaces.
10. Financial transactions maintain database integrity.
11. Simulation state is controlled by the backend.
12. Important operations generate audit events.
13. The project can run through its documented development setup.
14. Automated tests can be executed consistently.
15. The architecture supports the planned multiplayer extension without requiring a complete redesign.

---

# DOCUMENT CONTROL

| Field            | Value                                                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| Document ID      | CBS-TAD-001                                                                                                           |
| Version          | 0.1                                                                                                                   |
| Status           | Initial Technical Architecture                                                                                        |
| Parent Documents | CBS-PRD-001, CBS-FS-001                                                                                               |
| Next Document    | CBS-DBD-001 — Database Design and Data Dictionary                                                                     |
| Change Policy    | Material architectural changes must be recorded and reviewed against the approved product and functional requirements |
