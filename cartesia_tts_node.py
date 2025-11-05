# cartesia_tts_node.py
# ComfyUI custom node: Cartesia Sonic-3 TTS -> returns saved WAV/MP3 + bytes + optional URL
#
# Install: clone repo into ComfyUI/custom_nodes/ and restart ComfyUI.
#
# This node performs a synchronous POST to https://api.cartesia.ai/tts/bytes
# using headers:
#   Cartesia-Version: 2024-06-10
#   X-API-Key: <key>
#   Content-Type: application/json
#
# and body fields according to Cartesia docs.
#
# Outputs:
#   file_path (STRING) : path where audio is saved (absolute)
#   bytes (BYTES)      : raw bytes of audio
#   url (STRING)       : optional URL (file://path or uploaded URL if upload_to_tmpfiles=True)

import os
import json
import tempfile
import requests

SUPPORTED_CONTAINERS = ("wav", "mp3", "raw")

class CartesiaTTSNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": ""}),
                "transcript": ("STRING", {"multiline": True, "default": ""}),
                "voice_id": ("STRING", {"multiline": False, "default": ""}),
            },
            "optional": {
                "model_id": ("STRING", {"default": "sonic-3"}),
                "container": ("STRING", {"default": "wav"}),
                "encoding": ("STRING", {"default": "pcm_f32le"}),
                "sample_rate": ("INT", {"default": 44100, "min": 8000, "max": 48000}),
                "gen_speed": ("FLOAT", {"default": 1.0, "min": 0.6, "max": 1.5}),
                "gen_volume": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0}),
                "save_basename": ("STRING", {"default": "cartesia_audio"}),
                "upload_to_tmpfiles": ("BOOL", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING", "BYTES", "STRING")
    RETURN_NAMES = ("file_path", "bytes", "url")
    FUNCTION = "run"
    CATEGORY = "Cartesia"

    def _upload_tmpfiles(self, filepath):
        # Best-effort upload to tmpfiles.org; if fails, return file:// URL
        try:
            # tmpfiles.org upload API: POST multipart form with 'file'
            with open(filepath, "rb") as f:
                resp = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                # API returns {"status":"ok","data":{"url":"https://tmpfiles.org/xxxxxx"}}
                url_page = data.get("data", {}).get("url")
                if url_page:
                    # build direct download link if page URL is present
                    if "/tmpfiles.org/" in url_page:
                        # page url looks like https://tmpfiles.org/xxxxx ; downloadable is /dl/xxxxx/<name> maybe
                        # fallback to page url
                        return url_page
                    return url_page
        except Exception:
            pass
        return "file://" + filepath

    def run(
        self,
        api_key,
        transcript,
        voice_id,
        model_id="sonic-3",
        container="wav",
        encoding="pcm_f32le",
        sample_rate=44100,
        gen_speed=1.0,
        gen_volume=1.0,
        save_basename="cartesia_audio",
        upload_to_tmpfiles=False,
    ):
        container = (container or "wav").lower()
        if container not in SUPPORTED_CONTAINERS:
            raise ValueError(f"Unsupported container '{container}'. Use one of {SUPPORTED_CONTAINERS}.")

        headers = {
            "Cartesia-Version": "2024-06-10",
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        body = {
            "model_id": model_id,
            "transcript": transcript,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {"container": container, "encoding": encoding, "sample_rate": int(sample_rate)},
            "speed": "normal",
            "generation_config": {"speed": float(gen_speed), "volume": float(gen_volume)},
        }

        r = requests.post("https://api.cartesia.ai/tts/bytes", headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"Cartesia TTS HTTP {r.status_code}: {r.text}")

        audio_bytes = r.content
        suffix = "." + ("raw" if container == "raw" else container)
        fd, path = tempfile.mkstemp(prefix=save_basename + "_", suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)

        url = "file://" + path
        if upload_to_tmpfiles:
            url = self._upload_tmpfiles(path)

        # Return absolute path, bytes, and a URL string (file:// or remote)
        return (os.path.abspath(path), audio_bytes, url)


NODE_CLASS_MAPPINGS = {
    "CartesiaTTSNode": CartesiaTTSNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CartesiaTTSNode": "Cartesia Sonic-3 TTS"
}
