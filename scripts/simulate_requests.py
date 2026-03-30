import time
import random
import requests
import argparse

def simulate(target_url, delay=1.0):
    print(f"Starting simulation against {target_url}...")
    
    endpoints = [
        ("GET", "/api/users"),
        ("GET", "/api/users/1"),
        ("GET", "/api/users/2"),
        ("POST", "/api/users"),
        ("GET", "/api/posts"),
        ("GET", "/api/posts/abc-123"),
        ("POST", "/api/login"),
        ("GET", "/health"),
        ("GET", "/metrics"),
    ]
    
    try:
        while True:
            method, path = random.choice(endpoints)
            url = f"{target_url.rstrip('/')}{path}"
            
            try:
                start_time = time.time()
                if method == "GET":
                    resp = requests.get(url, timeout=5)
                else:
                    resp = requests.post(url, json={"test": "data"}, timeout=5)
                
                duration = (time.time() - start_time) * 1000
                print(f"[{method}] {path} -> {resp.status_code} ({duration:.0f}ms)")
                
            except requests.exceptions.RequestException as e:
                print(f"Error requesting {path}: {e}")
            
            time.sleep(delay * (0.5 + random.random()))
            
    except KeyboardInterrupt:
        print("\nSimulation stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate API requests for apimon")
    parser.add_argument("--url", default="http://localhost:8080", help="Target URL (default: http://localhost:8080)")
    parser.add_argument("--delay", type=float, default=1.0, help="Average delay between requests in seconds")
    
    args = parser.parse_args()
    simulate(args.url, args.delay)
