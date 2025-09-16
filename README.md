
#### **Project Nidhi: A Self-Service Database Provisioning Platform**

**Abstract:**

Project Nidhi addresses the significant administrative overhead and security challenges associated with manually managing databases for student projects. In many educational environments, the process of creating, assigning credentials for, and deleting PostgreSQL databases is a manual, error-prone task for administrators. This bottleneck stifles student innovation and introduces potential security vulnerabilities.

Nidhi is a secure, web-based control panel that automates and governs the entire database lifecycle. By integrating with a central authentication system (the Attendance Project), Nidhi provides a single sign-on experience for students and administrators. The platform implements a robust, role-based workflow where students can request a new database via a simple interface. This request is then routed to a designated college administrator for approval.

Upon approval, Nidhi's backend securely orchestrates the creation of a new, isolated PostgreSQL database and generates unique user credentials. This process is fully automated, ensuring consistency and security. The platform features a multi-tenant architecture, allowing college administrators to oversee their respective students' resources, while providing a superuser with a global "bird's-eye view" for system-wide auditing. Nidhi is built on a modern technology stack, including React for the frontend, Django REST Framework for the API, and PostgreSQL as the database engine, all designed to run within a containerized Docker environment. The result is a streamlined, secure, and auditable Database-as-a-Service (DBaaS) platform that empowers students while providing institutions with complete control and visibility.


# Project Nidhi - A Self-Service Database Provisioning Platform

**Nidhi is a secure, multi-tenant, and fully containerized web platform that automates the entire PostgreSQL database lifecycle for users in an educational environment. It empowers students and faculty to provision, manage, and delete their own isolated databases on demand, turning a slow administrative task into a fast, self-service workflow.**

[![Frontend](https://img.shields.io/badge/Frontend-React.js-61DAFB?logo=react)](https://reactjs.org/)
[![Backend](https://img.shields.io/badge/Backend-Django%20REST-092E20?logo=django)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-336791?logo=postgresql)](https://www.postgresql.org/)
[![Deployment](https://img.shields.io/badge/Deployment-Docker%20%26%20Nginx-2496ED?logo=docker)](https://www.docker.com/)

---

## **1. 🎯 The Vision: Why Nidhi?**

In many academic settings, a student or faculty member needing a database for a new project faces a bottleneck: they must file a request and wait for a busy administrator to manually create the database and user, and then securely transmit the credentials. This process is slow, inefficient, and prone to error.

Nidhi was created to solve this problem. The name **Nidhi (निधि)** is a Sanskrit word meaning **"Treasure."** The project's vision is to provide a secure place where the data—the treasure of any project—can be stored and managed effortlessly and safely.

Nidhi acts as a secure control panel, integrating with our existing **[Jnwn Attendance System](https://github.com/Safacts/jnwn)** to provide a single, unified authentication experience.

---

## **2. ✨ Key Features**

-   **Seamless Authentication:** No new accounts needed. Nidhi uses a custom-built REST API from the `jnwn` project to authenticate all users (Admins, Faculty, Students) via their existing credentials.
-   **Multi-Tenant by Design:** A robust architecture ensures that College Admins can only view and approve requests from users within their own college, providing complete data isolation. A global Superuser role has a "bird's-eye view" for system-wide auditing.
-   **Automated Provisioning Workflow:**
    1.  A user requests a new database via a simple UI.
    2.  The request appears in the correct College Admin's dashboard.
    3.  Upon approval, Nidhi's backend securely orchestrates the creation of a new, isolated PostgreSQL database and a unique user with a strong, randomly generated password.
-   **Full Lifecycle Management:** The user-friendly, card-based dashboard gives users complete control over their resources:
    -   **Secure Credential Viewing:** Retrieve the generated password once.
    -   **Password Management:** Change their database password at any time.
    -   **Resource Monitoring:** Check the current size of their database on demand.
    -   **Database Introspection:** Securely view a list of all tables within their database.
    -   **Safe Deletion:** A confirmation workflow ensures databases and their users are cleanly and permanently deleted.
-   **Resource Governance:** A built-in quota system prevents users from requesting an excessive number of databases.
-   **Polished UI/UX:** A sleek, responsive interface with a persistent Light/Dark mode, a custom notification system, and a focus on intuitive user workflows.

---

## **3. 🛠️ System Architecture & Tech Stack**

Nidhi is architected as a modern, multi-service application, fully containerized with Docker and designed to run as part of a larger, unified platform.

### **Core Technologies**
*   **Backend:** Django, Django REST Framework, Gunicorn
*   **Frontend:** React.js (with custom hooks for state management)
*   **Databases:**
    *   **Nidhi's Internal DB:** A dedicated PostgreSQL container to store request data.
    *   **Managed DB Server:** A separate PostgreSQL container that Nidhi manages, where all user databases are created.
*   **DevOps:** Docker, Docker Compose, Nginx (as a reverse proxy).

### **Unified Deployment with Nginx**
In production, Nidhi runs behind an **Nginx reverse proxy** alongside the `jnwn` project. This allows both applications to be served from a single public domain, creating a seamless user experience.
*   Traffic to `https://<your-domain>/` is routed to the **Jnwn** application.
*   Traffic to `https://<your-domain>/nidhi/` is routed to the **Nidhi** frontend.
*   API calls to `/nidhi/api/` are routed to the **Nidhi backend**.

---

## **4. 🚀 Deployment**

Nidhi is designed to be deployed as part of the unified architecture detailed in the `jnwn` project. It is managed by a master `docker-compose.master.yml` and an automated deployment script (`auto_deploy_master.sh`).

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Safacts/Nidhi.git /home/aadi/services/nidhi
    ```
2.  **Create Production `.env` File:**
    *   Create a file at `/home/aadi/services/nidhi/.env.prod`.
    *   Populate it with a production `SECRET_KEY`, database credentials for `nidhi_db` and `nidhi_main_db`, and set the `ATTENDANCE_API_URL` to the internal Docker service name (e.g., `http://jnwn_web:8000`).
3.  **Run the Master Deployment Script:**
    *   Execute the `auto_deploy_master.sh` script from the `/home/aadi/services/` directory. The script will handle building the images, running migrations, and starting all services.

---

## **5. 🎯 Future Roadmap**

-   [ ] **Backup & Restore:** Implement one-click backup (`pg_dump`) and restore functionality for users.
-   [ ] **Web-Based SQL Shell:** Build a simple, secure interface for users to run read-only SQL queries against their databases.
-   [ ] **Advanced Analytics:** Provide admins with dashboards showing database usage statistics.

---

## **6. 📜 License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


## **7. 📞 Contact**

This project was designed and built by **Aadi**. For questions, feature requests, or collaboration, please feel free to reach out.

-   **GitHub Issues:** For any bugs or technical issues, please open an issue in this repository.
-   **LinkedIn:** [www.linkedin.com/in/aadisheshu-konga]