import random
import uuid
from locust import HttpUser, task, between

class ProductCatalogUser(HttpUser):
    # Paced user simulation
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.user_id = f"user-{uuid.uuid4().hex[:8]}"
        self.session_id = f"sess-{uuid.uuid4().hex[:8]}"
        self.backend = random.choice(["redis", "memcached"])
        self.headers = {
            "X-Cache-Backend": self.backend,
            "X-User-ID": self.user_id
        }
        # Initialize session
        self.client.post(
            f"/session/{self.session_id}",
            json={
                "session_id": self.session_id,
                "user_id": self.user_id,
                "username": f"customer_{self.user_id}",
                "role": "customer",
                "last_login": "2026-09-22T22:00:00Z",
                "ip_address": "192.168.1.100",
                "cart_count": 0,
                "preferences": {"currency": "USD", "theme": "dark"}
            },
            headers=self.headers
        )

    @task(5)
    def view_product(self):
        """Simulate View Product -> Update Leaderboard flow"""
        product_id = random.randint(1, 1000)
        # Periodically refresh user_id to simulate new user sessions and stay within rate-limit window
        if random.random() < 0.05:
            self.user_id = f"user-{uuid.uuid4().hex[:8]}"
            self.headers["X-User-ID"] = self.user_id

        with self.client.get(f"/products/{product_id}", headers=self.headers, catch_response=True, name="/products/[id]") as resp:
            if resp.status_code in (200, 429):
                resp.success()

        with self.client.post(f"/products/{product_id}/view", headers=self.headers, catch_response=True, name="/products/[id]/view") as resp:
            if resp.status_code in (200, 429):
                resp.success()

    @task(2)
    def check_leaderboard(self):
        """Fetch top 10 most viewed products"""
        with self.client.get("/leaderboard?limit=10", headers=self.headers, catch_response=True, name="/leaderboard") as resp:
            if resp.status_code in (200, 429):
                resp.success()

    @task(2)
    def check_rate_limit(self):
        """Simulate user rate-limit validation"""
        with self.client.get("/rate-limit-test", headers=self.headers, catch_response=True, name="/rate-limit-test") as resp:
            if resp.status_code in (200, 429):
                resp.success()

    @task(1)
    def update_session(self):
        """Simulate session touch / cart addition"""
        with self.client.patch(
            f"/session/{self.session_id}",
            json={"last_login": "2026-09-22T22:30:00Z", "cart_count": random.randint(1, 10)},
            headers=self.headers,
            catch_response=True,
            name="/session/[id]"
        ) as resp:
            if resp.status_code in (200, 429):
                resp.success()
