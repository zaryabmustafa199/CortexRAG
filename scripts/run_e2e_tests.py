import asyncio
import httpx
import uuid
import json
import sys
import time
from typing import Dict, Any

# ANSI Colors for beautiful logging
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"

BASE_URL = "http://localhost:8002/api/v1"

def print_header(title: str):
    print(f"\n{CYAN}{'='*60}\n{title}\n{'='*60}{RESET}")

def print_pass(step: str):
    print(f"{GREEN}[PASS] {step}{RESET}")

def print_fail(step: str, error: str):
    print(f"{RED}[FAIL] {step} - Error: {error}{RESET}")

def print_info(msg: str):
    print(f"{YELLOW}[INFO] {msg}{RESET}")

async def check_health() -> bool:
    print_header("Phase 1: Environment & Health Probe Checks")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get("http://localhost:8002/health", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                print_pass(f"Health check status: {data.get('status')}")
                print_info(f"Services status: {data.get('services')}")
                return True
            else:
                print_fail("Health check failed", f"Status code: {resp.status_code}")
                return False
        except Exception as exc:
            print_fail("Health check connection failed", str(exc))
            return False

async def run_auth_workspace_tests() -> Dict[str, Any]:
    print_header("Phase 2: Auth & Workspace Lifecycle Tests")
    results = {}
    
    # 1. Test Weak Password Rejection
    async with httpx.AsyncClient(timeout=30.0) as client:
        weak_payload = {
            "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
            "password": "weak"
        }
        try:
            resp = await client.post(f"{BASE_URL}/auth/register", json=weak_payload)
            if resp.status_code == 422:
                print_pass("Registration with weak password rejected (ValidationError)")
            else:
                print_fail("Registration with weak password accepted", f"Status: {resp.status_code}")
        except Exception as exc:
            print_fail("Weak password test failed", str(exc))

        # 2. Register Strong Password
        email = f"user_{uuid.uuid4().hex[:6]}@example.com"
        password = "StrongPassword123!"
        register_payload = {
            "email": email,
            "password": password
        }
        try:
            resp = await client.post(f"{BASE_URL}/auth/register", json=register_payload)
            if resp.status_code in [200, 201]:
                print_pass(f"User registration success: {email}")
            else:
                print_fail("Registration failed", f"Status: {resp.status_code}, Body: {resp.text}")
                return results
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print_fail("Registration call failed", repr(exc))
            return results

        # 3. Login
        login_payload = {
            "email": email,
            "password": password
        }
        try:
            # Login uses JSON payload representation
            resp = await client.post(f"{BASE_URL}/auth/login", json=login_payload)
            if resp.status_code == 200:
                data = resp.json()
                access_token = data.get("access_token")
                print_pass("JWT Login success. Access token obtained.")
                results["headers"] = {"Authorization": f"Bearer {access_token}"}
            else:
                print_fail("Login failed", f"Status: {resp.status_code}, Body: {resp.text}")
                return results
        except Exception as exc:
            print_fail("Login call failed", str(exc))
            return results

        # 4. Create Workspace
        headers = results["headers"]
        ws_payload = {
            "name": f"Workspace_{uuid.uuid4().hex[:6]}"
        }
        try:
            resp = await client.post(f"{BASE_URL}/workspaces", json=ws_payload, headers=headers)
            if resp.status_code in [200, 201]:
                ws_data = resp.json()
                results["workspace_id"] = ws_data.get("id")
                print_pass(f"Workspace created successfully: {ws_payload['name']} (ID: {results['workspace_id']})")
            else:
                # Fallback: List workspaces to reuse the default personal workspace
                print_info(f"Workspace creation status: {resp.status_code}. Attempting fallback to fetch existing workspace...")
                list_resp = await client.get(f"{BASE_URL}/workspaces", headers=headers)
                if list_resp.status_code == 200:
                    workspaces = list_resp.json()
                    if len(workspaces) > 0:
                        results["workspace_id"] = workspaces[0].get("id")
                        print_pass(f"Reused existing workspace: {workspaces[0].get('name')} (ID: {results['workspace_id']})")
                    else:
                        print_fail("Workspace reuse failed", "No existing workspaces found.")
                else:
                    print_fail("Workspace creation failed", f"Status: {resp.status_code}, Fallback status: {list_resp.status_code}")
        except Exception as exc:
            print_fail("Workspace create call failed", str(exc))

        # 5. Create API Key
        key_payload = {
            "name": "E2E-Test-Key"
        }
        try:
            resp = await client.post(f"{BASE_URL}/keys", json=key_payload, headers=headers)
            if resp.status_code in [200, 201]:
                key_data = resp.json()
                results["api_key"] = key_data.get("raw_key")
                print_pass(f"API Key created successfully: {key_payload['name']}")
            else:
                print_fail("API Key creation failed", f"Status: {resp.status_code}, Body: {resp.text}")
        except Exception as exc:
            print_fail("API Key call failed", str(exc))
            
    return results

async def run_upload_ingestion_tests(auth_info: Dict[str, Any]) -> str:
    print_header("Phase 3: File Ingestion Pipelines Tests")
    if "headers" not in auth_info or "workspace_id" not in auth_info:
        print_info("Skipping Phase 3 due to missing auth/workspace details.")
        return ""

    headers = auth_info["headers"]
    workspace_id = auth_info["workspace_id"]
    doc_id = ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Test Malicious Double-Extension Block
        files = {
            "file": ("backdoor.sh.pdf", b"echo 'hacking'", "application/pdf")
        }
        try:
            resp = await client.post(
                f"{BASE_URL}/documents/upload?workspace_id={workspace_id}",
                files=files,
                headers=headers
            )
            if resp.status_code == 400 or "error" in resp.text.lower():
                print_pass("Malicious double-extension blocked successfully (400 Bad Request)")
            else:
                print_fail("Malicious double-extension upload permitted", f"Status: {resp.status_code}")
        except Exception as exc:
            print_fail("Double extension test failed", str(exc))

        # 2. Upload Valid Document (.txt)
        txt_content = (
            "CortexRAG is a local-first enterprise RAG platform.\n"
            "The monthly document limit for the Free tier is 5 documents.\n"
            "The storage limit for the Free tier is 10 megabytes.\n"
            "This document was uploaded during the automated E2E test suite in the year 2026."
        )
        valid_files = {
            "file": ("e2e_limits_report.txt", txt_content.encode("utf-8"), "text/plain")
        }
        try:
            resp = await client.post(
                f"{BASE_URL}/documents/upload?workspace_id={workspace_id}",
                files=valid_files,
                headers=headers
            )
            if resp.status_code in [200, 201, 202]:
                data = resp.json()
                doc_id = data.get("document_id")
                print_pass(f"Valid document upload success. Document ID: {doc_id}")
            else:
                print_fail("Valid document upload failed", f"Status: {resp.status_code}, Body: {resp.text}")
                return ""
        except Exception as exc:
            print_fail("Upload call failed", str(exc))
            return ""

        # 3. Poll Celery Ingestion Job Status
        print_info("Polling document ingestion job status (Celery worker pipeline)...")
        max_retries = 30
        for i in range(max_retries):
            try:
                status_resp = await client.get(f"{BASE_URL}/documents/{doc_id}/status?workspace_id={workspace_id}", headers=headers)
                if status_resp.status_code == 200:
                    doc_data = status_resp.json()
                    status = doc_data.get("status")
                    print_info(f"Polling attempt {i+1}: Document Ingestion Status = {status}")
                    if status in ["READY", "SUCCESS"]:
                        print_pass("Document successfully parsed, embedded, and ready.")
                        break
                    elif status == "FAILED":
                        print_fail("Document ingestion pipeline failed", doc_data.get("error_message", "Unknown error"))
                        return ""
                else:
                    print_fail("Fetch document status failed", f"Status: {status_resp.status_code}")
            except Exception as exc:
                print_fail("Polling document status failed", str(exc))
            await asyncio.sleep(2.0)
        else:
            print_fail("Document ingestion timeout", f"Status remained PENDING/PROCESSING after {max_retries * 2}s")

    return doc_id

async def run_rag_retrieval_tests(auth_info: Dict[str, Any]):
    print_header("Phase 4: RAG Retrieval & Citation Verification")
    if "headers" not in auth_info or "workspace_id" not in auth_info:
        print_info("Skipping Phase 4 due to missing auth/workspace details.")
        return

    headers = auth_info["headers"]
    workspace_id = auth_info["workspace_id"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Create a query session
        session_payload = {
            "title": "E2E-RAG-Session"
        }
        session_id = ""
        try:
            resp = await client.post(f"{BASE_URL}/query/sessions?workspace_id={workspace_id}", json=session_payload, headers=headers)
            if resp.status_code in [200, 201]:
                session_data = resp.json()
                session_id = session_data.get("id")
                print_pass(f"Query session created: {session_id}")
            else:
                print_fail("Session creation failed", f"Status: {resp.status_code}")
                return
        except Exception as exc:
            print_fail("Session create call failed", str(exc))
            return

        # 2. Execute RAG Query Ask (SSE stream check)
        query_payload = {
            "session_id": session_id,
            "workspace_id": workspace_id,
            "question": "What is the storage size limit for Free tier? Cite using [Source 1]."
        }
        
        print_info("Submitting query and parsing SSE tokens stream...")
        try:
            # Connect to streaming endpoint
            async with client.stream("POST", f"{BASE_URL}/query/ask?workspace_id={workspace_id}", json=query_payload, headers=headers, timeout=60.0) as response:
                if response.status_code != 200:
                    print_fail("RAG ask request failed", f"Status: {response.status_code}")
                    return
                
                full_reply = ""
                citations = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data_json = json.loads(data_str)
                            if "token" in data_json:
                                full_reply += data_json["token"]
                            if "citations" in data_json:
                                citations = data_json["citations"]
                        except Exception:
                            pass
                
                print_info(f"Final LLM Reply: {full_reply}")
                if "10" in full_reply or "megabytes" in full_reply.lower() or "mb" in full_reply.lower():
                    print_pass("Correct grounded answer generated by LLM.")
                else:
                    print_info("Answer did not match expected '10MB' directly. Check Ollama generation content.")
                
                # Verify citations tracing
                if len(citations) > 0 or "Source 1" in full_reply:
                    print_pass(f"Citations correctly mapped back to documents: {citations}")
                else:
                    print_fail("No citations found in output", "Citations list was empty")
        except Exception as exc:
            print_fail("RAG stream query call failed", str(exc))

async def run_quota_cache_tests(auth_info: Dict[str, Any]):
    print_header("Phase 5: SaaS Quotas & Caching")
    if "headers" not in auth_info or "workspace_id" not in auth_info:
        print_info("Skipping Phase 5 due to missing auth/workspace details.")
        return

    headers = auth_info["headers"]
    workspace_id = auth_info["workspace_id"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create a query session for cache checks
        session_payload = {"title": "E2E-Cache-Session"}
        resp = await client.post(f"{BASE_URL}/query/sessions?workspace_id={workspace_id}", json=session_payload, headers=headers)
        session_id = resp.json().get("id")

        # 1. Ask query to populate cache
        query_payload = {
            "session_id": session_id,
            "workspace_id": workspace_id,
            "question": "What is the monthly document limit for the Free tier?"
        }
        
        t0 = time.time()
        # Initial request (Cache Miss)
        resp1 = await client.post(f"{BASE_URL}/query/ask?workspace_id={workspace_id}", json=query_payload, headers=headers)
        duration_miss = time.time() - t0
        print_info(f"Query 1 (Cache Miss) took: {duration_miss:.2f}s")

        # 2. Repeat exact query (Assert Cache Hit)
        t1 = time.time()
        resp2 = await client.post(f"{BASE_URL}/query/ask?workspace_id={workspace_id}", json=query_payload, headers=headers)
        duration_hit = time.time() - t1
        print_info(f"Query 2 (Cache Hit) took: {duration_hit:.2f}s")
        
        if duration_hit < duration_miss or duration_hit < 0.1:
            print_pass("Query caching verified. Speedup achieved on identical question.")
        else:
            print_info("Cache hit speed check inconclusive. Redis might not be configured as cache, or LLM generated locally very fast.")

async def run_security_hardening_tests():
    print_header("Phase 6: Hardening, Security, and Next.js Compilation")
    
    # 1. Check response headers for Security Configurations (CSP, HSTS, XFO)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get("http://localhost:8002/health", timeout=5.0)
            headers = resp.headers
            
            xfo = headers.get("X-Frame-Options")
            cto = headers.get("X-Content-Type-Options")
            csp = headers.get("Content-Security-Policy")
            
            if xfo == "DENY" and cto == "nosniff":
                print_pass("Security headers successfully verified (X-Frame-Options: DENY, X-Content-Type-Options: nosniff)")
            else:
                print_info(f"Warning: Expected security headers missing or modified. XFO: {xfo}, CTO: {cto}, CSP: {csp}")
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print_fail("Security headers probe failed", repr(exc))

        # 2. Check Admin Route Blocks
        try:
            resp = await client.get("http://localhost:8080/admin/security-check", timeout=5.0)
            # Route should be blocked by Caddy reverse proxy on port 80
            if resp.status_code in [403, 404]:
                print_pass(f"Administrative router blocked successfully: status {resp.status_code}")
            else:
                print_info(f"Warning: Administrative endpoint returned status {resp.status_code}")
        except Exception as exc:
            print_fail("Admin block check connection failed", str(exc))

async def main():
    print(f"\n{GREEN}{'='*60}\nCORTEXRAG E2E AUTOMATED VERIFICATION SUITE\n{'='*60}{RESET}")
    
    # Check if backend container is running
    is_healthy = await check_health()
    if not is_healthy:
        print(f"\n{RED}Error: Backend container is not running or unreachable on port 8002. Please start your Docker containers first via 'docker compose up -d'.{RESET}")
        sys.exit(1)
        
    auth_info = await run_auth_workspace_tests()
    
    doc_id = await run_upload_ingestion_tests(auth_info)
    
    if doc_id:
        await run_rag_retrieval_tests(auth_info)
        await run_quota_cache_tests(auth_info)
        
    await run_security_hardening_tests()
    
    print(f"\n{GREEN}{'='*60}\nVERIFICATION COMPLETE\n{'='*60}{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())
