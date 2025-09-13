
#### **Project Nidhi: A Self-Service Database Provisioning Platform**

**Abstract:**

Project Nidhi addresses the significant administrative overhead and security challenges associated with manually managing databases for student projects. In many educational environments, the process of creating, assigning credentials for, and deleting PostgreSQL databases is a manual, error-prone task for administrators. This bottleneck stifles student innovation and introduces potential security vulnerabilities.

Nidhi is a secure, web-based control panel that automates and governs the entire database lifecycle. By integrating with a central authentication system (the Attendance Project), Nidhi provides a single sign-on experience for students and administrators. The platform implements a robust, role-based workflow where students can request a new database via a simple interface. This request is then routed to a designated college administrator for approval.

Upon approval, Nidhi's backend securely orchestrates the creation of a new, isolated PostgreSQL database and generates unique user credentials. This process is fully automated, ensuring consistency and security. The platform features a multi-tenant architecture, allowing college administrators to oversee their respective students' resources, while providing a superuser with a global "bird's-eye view" for system-wide auditing. Nidhi is built on a modern technology stack, including React for the frontend, Django REST Framework for the API, and PostgreSQL as the database engine, all designed to run within a containerized Docker environment. The result is a streamlined, secure, and auditable Database-as-a-Service (DBaaS) platform that empowers students while providing institutions with complete control and visibility.
