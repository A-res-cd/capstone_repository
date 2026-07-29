"""
Locust load test for CAPRE (Flask + PostgreSQL capstone repository)
Run with:  locust -f locustfile.py --host=http://localhost:5000
Web UI:    http://localhost:8089
"""

import random
from locust import HttpUser, task, between


class GuestUser(HttpUser):
    """Simulates users who log in first, then browse the archive."""
    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post("/signin", data={
            "email": f"guest{random.randint(1, 200)}@example.com",
            "password": "TestPassword123",
        })

    @task(3)
    def view_home(self):
        self.client.get("/")

    @task(2)
    def view_archive(self):
        self.client.get("/archive")

    @task(1)
    def search_archive(self):
        queries = ["capstone", "thesis", "system", "flask", "database"]
        self.client.get("/archive", params={"q": random.choice(queries)})


class StudentUser(HttpUser):
    """Simulates logged-in students searching and requesting manuscripts."""
    weight = 5
    wait_time = between(2, 5)

    def on_start(self):
        # Adjust field names to match your auth blueprint's signin form
        self.client.post("/signin", data={
            "email": f"student{random.randint(1, 200)}@example.com",
            "password": "TestPassword123",
        })

    @task(3)
    def search_archive(self):
        queries = ["capstone", "IoT", "machine learning", "web app"]
        self.client.get("/archive", params={"q": random.choice(queries)})

    @task(1)
    def request_manuscript(self):
        # Adjust payload to match your admin/pages blueprint's request route
        self.client.post("/request", data={
            "manuscript_id": random.randint(1, 100),
            "reason": "Reference for related literature",
        })

    @task(1)
    def logout(self):
        self.client.get("/logOut")


class AdminUser(HttpUser):
    """Simulates a small number of admins managing requests/users."""
    weight = 1
    wait_time = between(3, 6)

    def on_start(self):
        self.client.post("/signin", data={
            "email": "admin@example.com",
            "password": "AdminPassword123",
        })

    @task
    def view_manage_users(self):
        self.client.get("/admin/manage-users")

    @task
    def view_requests(self):
        self.client.get("/admin/requests")
