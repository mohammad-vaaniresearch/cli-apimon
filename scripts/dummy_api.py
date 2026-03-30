from aiohttp import web
import asyncio
import random

async def handle_users(request):
    await asyncio.sleep(random.uniform(0.01, 0.1))
    return web.json_response([{"id": 1, "name": "User 1"}, {"id": 2, "name": "User 2"}])

async def handle_user_detail(request):
    user_id = request.match_info.get('id')
    await asyncio.sleep(random.uniform(0.02, 0.15))
    return web.json_response({"id": int(user_id), "name": f"User {user_id}"})

async def handle_posts(request):
    # Simulate a slow write
    if request.method == "POST":
        await asyncio.sleep(1.5)
        return web.json_response({"status": "created"}, status=201)
    return web.json_response([{"id": "abc-123", "title": "Hello World"}])

async def handle_login(request):
    # Simulate a security anomaly (random failures)
    if random.random() < 0.3:
        return web.json_response({"error": "Unauthorized"}, status=401)
    return web.json_response({"token": "fake-jwt-token"})

def run_dummy_api(port=3000):
    app = web.Application()
    app.add_routes([
        web.get('/api/users', handle_users),
        web.get('/api/users/{id}', handle_user_detail),
        web.get('/api/posts', handle_posts),
        web.post('/api/posts', handle_posts),
        web.post('/api/login', handle_login),
    ])
    print(f"Dummy API running on http://localhost:{port}")
    web.run_app(app, port=port)

if __name__ == "__main__":
    run_dummy_api()
