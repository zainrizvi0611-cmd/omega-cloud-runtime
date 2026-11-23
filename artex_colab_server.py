"""
ARTEX Coder 7B - Google Colab OpenAI-Compatible Inference Server
Model: 0XARTEX/artex-coder-7b (Qwen2.5-Coder Architecture)
Features:
  - Non-blocking Multi-threaded FastAPI Server
  - Proper Qwen2 EOS (<|im_end|>) stopping token handling (prevents runaway generation)
  - /v1/chat/completions (OpenAI Compatible)
  - /v1/models
  - /health (Keep-alive & GPU diagnostic)
  - Cloudflared Free HTTPS Public Tunnel
"""

import sys
import os
import time
import subprocess
import threading
import json

def setup_environment():
    print("[*] Installing Colab Server Dependencies...")
    pkgs = [
        "torch",
        "transformers>=4.45.0",
        "accelerate>=0.26.0",
        "bitsandbytes>=0.43.0",
        "fastapi",
        "uvicorn",
        "pydantic"
    ]
    subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + pkgs, check=True)

    # Install Cloudflared for public zero-config tunnel
    if not os.path.exists("/usr/local/bin/cloudflared"):
        print("[*] Installing Cloudflared tunnel binary...")
        subprocess.run([
            "curl", "-L", "-s",
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
            "-o", "/usr/local/bin/cloudflared"
        ], check=True)
        os.chmod("/usr/local/bin/cloudflared", 0o755)

def run_server():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn

    model_id = os.environ.get("MODEL_ID") or (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "0XARTEX/artex-coder-7b")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Target Device: {device.upper()}")
    if device == "cuda":
        print(f"[*] GPU: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB)")
    else:
        print("[!] WARNING: Running on CPU! For best speed, enable GPU in Runtime -> Change runtime type -> T4 GPU.")

    print(f"[*] Loading Tokenizer: {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    # Configure EOS tokens for Qwen2.5-Coder architecture
    eos_ids = [tokenizer.eos_token_id] if tokenizer.eos_token_id is not None else []
    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if isinstance(im_end_id, int) and im_end_id not in eos_ids:
        eos_ids.append(im_end_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print(f"[*] Loading Model: {model_id} in 4-bit...")
    load_kwargs = {
        "trust_remote_code": True,
        "device_map": "auto"
    }
    if device == "cuda":
        load_kwargs["torch_dtype"] = torch.float16
        load_kwargs["load_in_4bit"] = True
    else:
        load_kwargs["torch_dtype"] = torch.float32

    model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)
    print("[+] Model loaded successfully!")

    app = FastAPI(title="0XARTEX Coder 7B API")

    @app.get("/")
    @app.get("/health")
    def health():
        return {
            "status": "online",
            "model": model_id,
            "device": device,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None",
            "timestamp": int(time.time())
        }

    @app.get("/v1/models")
    def list_models():
        return {
            "object": "list",
            "data": [
                {
                    "id": "0XARTEX/artex-coder-7b",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "0XARTEX"
                }
            ]
        }

    # Synchronous def runs in FastAPI ThreadPoolExecutor to prevent event-loop freezing
    @app.post("/v1/chat/completions")
    def chat_completions(body: dict):
        try:
            messages = body.get("messages", [])
            temperature = float(body.get("temperature", 0.3))
            max_tokens = min(int(body.get("max_tokens", 512)), 1024)

            # Apply chat template
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            target_device = "cuda" if torch.cuda.is_available() else "cpu"
            encoded = tokenizer([prompt_text], return_tensors="pt")
            inputs = {k: v.to(target_device) for k, v in encoded.items()}
            prompt_len = inputs["input_ids"].shape[1]

            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 0.01,
                    do_sample=True if temperature > 0 else False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=eos_ids
                )

            generated_ids = outputs[0][prompt_len:]
            response_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "0XARTEX/artex-coder-7b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_len,
                    "completion_tokens": len(generated_ids),
                    "total_tokens": prompt_len + len(generated_ids)
                }
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": "server_error"}})

    # Start Cloudflared tunnel
    def start_tunnel():
        time.sleep(3)
        print("[*] Launching Cloudflared Tunnel...")
        proc = subprocess.Popen(
            ["/usr/local/bin/cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            if "trycloudflare.com" in line:
                import re
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    tunnel_url = match.group(0)
                    print("\n" + "=" * 65)
                    print("🚀 ARTEX CODER 7B OPENAI-COMPATIBLE API IS LIVE!")
                    print(f"👉 API BASE URL : {tunnel_url}/v1")
                    print(f"👉 MODEL ID     : 0XARTEX/artex-coder-7b")
                    print("=" * 65 + "\n")
                    with open("/content/artex_api_url.txt", "w") as f:
                        f.write(f"{tunnel_url}/v1\n")
                    break


    # 24/7 Anti-Idle Heartbeat Worker
    def keep_alive_heartbeat():
        while True:
            time.sleep(30)
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as r:
                    pass
            except Exception:
                pass

    threading.Thread(target=keep_alive_heartbeat, daemon=True).start()

    def sync_to_github(tunnel_url):
        gh_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not gh_tok:
            return
        try:
            import base64, urllib.request
            repo = "zainrizvi0611-cmd/omega-cloud-runtime"
            url = f"https://api.github.com/repos/{repo}/contents/artex_live_endpoint.txt"
            headers = {"Authorization": f"token {gh_tok}", "Accept": "application/vnd.github.v3+json"}
            sha = None
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    sha = json.loads(resp.read().decode()).get("sha")
            except Exception:
                pass
            payload = {"message": "chore: auto-update 24/7 live endpoint", "content": base64.b64encode(f"{tunnel_url}/v1
".encode()).decode()}
            if sha:
                payload["sha"] = sha
            put_req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="PUT")
            with urllib.request.urlopen(put_req) as r:
                print(f"[+] 24/7 Dynamic Cloud Tracker auto-updated on GitHub: {repo}/artex_live_endpoint.txt")
        except Exception as e:
            print(f"[-] GitHub auto-sync notice: {e}")

    threading.Thread(target=start_tunnel, daemon=True).start()

    # Run Uvicorn server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

if __name__ == "__main__":
    setup_environment()
    run_server()
