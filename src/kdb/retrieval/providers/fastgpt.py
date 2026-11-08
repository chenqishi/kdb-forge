import httpx


async def request_completion(url, text, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "stream": False,
        "detail": True,
        "messages": [
            {
                "role": "user",
                "content": text
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)

    return response
