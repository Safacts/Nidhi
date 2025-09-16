# Project Nidhi - A Self-Service Database-as-a-Service (DBaaS) Platform

**Project Nidhi is a secure, multi-tenant, and fully containerized web platform that automates the entire PostgreSQL database lifecycle for users in an educational environment. It empowers students and faculty to provision, manage, and delete their own isolated databases on demand, turning a slow administrative task into a fast, self-service workflow.**

**Live Application:** [**https://sunbeam-smiling-trout.ngrok-free.app/nidhi/**](https://sunbeam-smiling-trout.ngrok-free.app/nidhi/)

[![Frontend](https://img.shields.io/badge/Frontend-React.js-61DAFB?logo=react)](https://reactjs.org/)
[![Backend](https://img.shields.io/badge/Backend-Django%20REST-092E20?logo=django)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-336791?logo=postgresql)](https://www.postgresql.org/)
[![Deployment](https://img.shields.io/badge/Deployment-Docker%20%26%20Nginx-2496ED?logo=docker)](https://www.docker.com/)

---

## **1. 🎯 The Vision: Why Nidhi?**

In many academic settings, a student or faculty member needing a database for a new project faces a significant bottleneck: they must file a request and wait for a busy administrator to manually create the database, user, and then securely transmit the credentials. This process is slow, inefficient, and stifles innovation.

Nidhi was created to solve this problem. The name **Nidhi (निधि)** is a Sanskrit word meaning **"Treasure."** The project's vision is to provide a secure place where the data—the treasure of any project—can be stored and managed effortlessly and safely.

Nidhi acts as a secure control panel, integrating with our existing **[Jnwn Attendance System](https://github.com/Safacts/jnwn)** to provide a single, unified authentication experience for all users.

---

## **2. ✨ Key Features**

-   **Seamless & Unified Authentication:** No new accounts are needed. Nidhi uses a custom-built REST API from the `jnwn` project to authenticate all users (Admins, Faculty, Students) via their existing credentials. Students have the flexibility to log in with either their **Email or unique Roll Number**.

-   **True Multi-Tenancy by Design:** A robust architecture ensures that College Admins can *only* view and approve requests from users within their own college, providing complete data privacy and isolation. A global Superuser role has a "bird's-eye view" for system-wide auditing.

-   **Automated Provisioning Workflow:** A simple request-approve-use workflow that automatically creates isolated PostgreSQL databases and users with strong, randomly generated passwords.

-   **Full Lifecycle Management:** A user-friendly, card-based dashboard gives users complete control over their resources:
    -   **Secure Credential Viewing:** Retrieve the generated password once.
    -   **Password Management:** Change their database password at any time.
    -   **Resource Monitoring:** Check the current size of their database on demand.
    -   **Database Introspection:** Securely view a list of all tables within their database by providing their password for on-demand authentication.
    -   **Safe Deletion:** A confirmation workflow ensures databases and their users are cleanly and permanently deleted.

-   **Resource Governance:** A built-in quota system prevents users from requesting an excessive number of databases.

-   **Polished UI/UX:** A sleek, responsive interface with a persistent Light/Dark mode, a custom notification system, and a focus on intuitive user workflows.

---

## **3. 🛠️ System Architecture & Tech Stack**

Nidhi is architected as a modern, multi-service application, fully containerized with Docker and designed to run as part of a larger, unified platform.

### **Unified Deployment with Nginx**
In production, Nidhi runs behind an **Nginx reverse proxy** alongside the `jnwn` project. This allows both applications to be served from a single public domain, creating a seamless user experience.

```
                  +----------------------------------------------+
                  |  User via Browser (e.g., Chrome, Firefox)    |
                  +----------------------------------------------+
                                      |
                                      v
                  +----------------------------------------------+
                  |  Public URL (https://your-domain.com)        |
                  |  Managed by Ngrok / Cloudflare Tunnel        |
                  +----------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------+
| Raspberry Pi / Server                                                             |
|                                                                                   |
|      +---------------------------------------------------------------------+      |
|      | Docker's Internal Network                                           |      |
|      |                                                                     |      |
|      |   +--------------------------+                                      |      |
|      |   | Nginx Reverse Proxy      |                                      |      |
|      |   +--------------------------+                                      |      |
|      |      |                         |                                   |      |
|      |      | (/nidhi/*)              | (all other traffic, e.g., /)        |      |
|      |      v                         v                                   |      |
|      |   +-----------------+      +-----------------+                      |      |
|      |   | Nidhi Frontend  |      | Jnwn Application|                      |      |
|      |   | (React)         |      | (Django)        |                      |      |
|      |   +-------+---------+      +-------+---------+                      |      |
|      |           | (/nidhi/api/*)         | (/api/*)                         |      |
|      |           v                        v                                |      |
|      |   +-----------------+      +-----------------+                      |      |
|      |   | Nidhi Backend   |----->| Jnwn Auth API   |                      |      |
|      |   | (Django REST)   |      | (on Jnwn App)   |                      |      |
|      |   +-------+---------+      +-----------------+                      |      |
|      |           |                                                         |      |
|      |           v                                                         |      |
|      |   +-----------------+      +-----------------+                      |      |
|      |   | Nidhi Internal  |      | Main Managed DB |                      |      |
|      |   | DB (Postgres)   |      | Server (Postgres)|                      |      |
|      |   +-----------------+      +-----------------+                      |      |
|      |                                                                     |      |
+-----------------------------------------------------------------------------------+
```

### **Core Technologies**
*   **Backend:** Django, Django REST Framework, Gunicorn
*   **Frontend:** React.js (with custom hooks for state management)
*   **Databases:** Two PostgreSQL containers (one for Nidhi's internal state, one as the managed server).
*   **DevOps:** Docker, Docker Compose, Nginx (as a reverse proxy), `systemd`, Bash Scripting.

---

## **4. 🚀 Deployment Overview**

Nidhi is deployed as part of the unified architecture detailed in the `jnwn` project. It is managed by a master `docker-compose.master.yml` and an automated deployment script (`auto_deploy_master.sh`).

1.  **Clone the Repository** into the master `services` directory on the production server.
2.  **Create a `.env.prod` file** with all production secrets (SECRET_KEY, database passwords, etc.).
3.  **Run the master deployment script**, which handles building the images, running migrations, and starting all services in the correct order.

---

## **5. 🎯 Future Roadmap**

-   [ ] **Backup & Restore:** Implement one-click backup (`pg_dump`) and restore functionality for users.
-   [ ] **Web-Based SQL Shell:** Build a simple, secure interface for users to run read-only SQL queries against their databases.
-   [ ] **Admin Analytics:** Provide admins with dashboards showing database usage statistics.

---

## **6. 📜 License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## **7. 📞 Contact**

This project was designed and built by **Aadi**.
-   **LinkedIn:** [www.linkedin.com/in/aadisheshu-konga](https://www.linkedin.com/in/aadisheshu-konga)
-   **GitHub Issues:** For any bugs or technical issues, please open an issue.