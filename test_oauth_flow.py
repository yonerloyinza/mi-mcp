"""
Test completo del flujo OAuth 2.1 para el servidor MCP seguro.
"""
import asyncio
import httpx
import jwt
from urllib.parse import urlparse, parse_qs

async def main():
    async with httpx.AsyncClient(follow_redirects=False) as client:
        
        # Paso 1: Cliente MCP intenta usar el servidor sin token
        print("=== Paso 1: Cliente MCP sin token ===")
        r = await client.post(
            "http://127.0.0.1:8005/mcp",
            headers={"Mcp-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"},
            json={}
        )
        print(f"Sin token: {r.status_code} - {r.json().get('detail', r.text[:80])}")
        
        # Paso 2: Descubrir recurso protegido
        print("\n=== Paso 2: Recurso protegido ===")
        r = await client.get("http://127.0.0.1:8005/.well-known/oauth-protected-resource")
        print(f"Well-known resource: {r.status_code}")
        if r.status_code == 200:
            metadata = r.json()
            print(f"  Resource: {metadata.get('resource')}")
            print(f"  Auth servers: {metadata.get('authorization_servers')}")
            auth_server_url = metadata["authorization_servers"][0]
        
        # Paso 3: Descubrir authorization server
        print("\n=== Paso 3: Authorization server metadata ===")
        r = await client.get(f"{auth_server_url}/.well-known/oauth-authorization-server")
        print(f"Well-known auth: {r.status_code}")
        if r.status_code == 200:
            auth_metadata = r.json()
            print(f"  Authorize endpoint: {auth_metadata.get('authorization_endpoint')}")
            print(f"  Token endpoint: {auth_metadata.get('token_endpoint')}")
            authorize_url = auth_metadata["authorization_endpoint"]
            token_url = auth_metadata["token_endpoint"]
        
        # Paso 4: Usuario autoriza en /authorize
        print("\n=== Paso 4: Usuario autoriza ===")
        r = await client.get(
            f"{authorize_url}?response_type=code&client_id=mcp-client&redirect_uri=http://localhost:3000/callback&scope=mcp:tools&code_challenge=test_challenge&code_challenge_method=S256&state=abc123",
            follow_redirects=False
        )
        print(f"Authorize GET: {r.status_code}")
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("location", "")
            print(f"Redirect a: {location}")
            parsed = urlparse(location)
            code = parse_qs(parsed.query).get("code", [None])[0]
            print(f"Código: {code}")
        else:
            print(f"Contenido: {r.text[:200]}")
            code = None
        
        # Paso 5: Intercambiar código por token
        print("\n=== Paso 5: Token endpoint ===")
        if code:
            r = await client.post(
                f"{token_url}",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "http://localhost:3000/callback",
                    "code_verifier": "test_verifier",
                    "client_id": "mcp-client",
                }
            )
            print(f"Token: {r.status_code}")
            if r.status_code == 200:
                token_data = r.json()
                access_token = token_data["access_token"]
                print(f"Token obtenido: {access_token[:40]}...")
                
                # Paso 6: Usar token en /mcp
                print("\n=== Paso 6: Usar token en /mcp ===")
                r = await client.post(
                    "http://127.0.0.1:8005/mcp",
                    headers={
                        "Mcp-Protocol-Version": "2026-07-28",
                        "Mcp-Method": "tools/list",
                        "Authorization": f"Bearer {access_token}"
                    },
                    json={}
                )
                print(f"Tools list: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    tools = [t.get("name", "?") for t in data.get("tools", [])]
                    print(f"  Tools: {tools}")
                    
                    # Test add
                    r = await client.post(
                        "http://127.0.0.1:8005/mcp",
                        headers={
                            "Mcp-Protocol-Version": "2026-07-28",
                            "Mcp-Method": "tools/call",
                            "Mcp-Name": "add",
                            "Authorization": f"Bearer {access_token}"
                        },
                        json={"arguments": {"a": 10, "b": 25}}
                    )
                    print(f"add(10,25): {r.status_code} - {r.text[:150]}")
            else:
                print(f"Error: {r.text[:200]}")
        else:
            print("No se obtuvo código, probando con token directo...")
            token = jwt.encode(
                {"scope": "mcp:tools", "aud": "https://mcp.example.com"},
                "dev-secret-change-in-production",
                algorithm="HS256"
            )
            r = await client.post(
                "http://127.0.0.1:8005/mcp",
                headers={
                    "Mcp-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "tools/list",
                    "Authorization": f"Bearer {token}"
                },
                json={}
            )
            print(f"Tools list (token directo): {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                tools = [t.get("name", "?") for t in data.get("tools", [])]
                print(f"  Tools: {tools}")
            
            r = await client.post(
                "http://127.0.0.1:8005/mcp",
                headers={
                    "Mcp-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "tools/call",
                    "Mcp-Name": "add",
                    "Authorization": f"Bearer {token}"
                },
                json={"arguments": {"a": 10, "b": 25}}
            )
            print(f"add(10,25): {r.status_code} - {r.text[:150]}")

if __name__ == "__main__":
    asyncio.run(main())
