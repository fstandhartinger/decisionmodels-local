"""Public, synthetic smoke decisions for the installed local endpoint."""
import base64
import json
import statistics
import struct
import time
import urllib.error
import urllib.request
import zlib

SAMPLES = [
    {"model": "local", "state": "A bowl contains a ripe orange and a green apple.", "questions": {"fruit": {
        "type": "choice", "instructions": "Which fruit is orange?", "criteria": {"orange": None, "apple": None}}}},
    {"model": "local", "state": "Water freezes at 0 degrees Celsius.", "questions": {"true": {
        "type": "noul", "instructions": "Does water freeze at 0 degrees Celsius?"}}},
    {"model": "local", "state": "A response says: 'The meeting begins at 9 AM.'", "questions": {"clarity": {
        "type": "score", "instructions": "How clear is the sentence?", "criteria": ["unclear", "partly clear", "clear"]}}},
]


def _red_square():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    pixels = (b"\x00" + b"\xff\x00\x00" * 64) * 64
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def run(base_url, api_key=None, model="local", opener=urllib.request.urlopen, image=False):
    results = []
    latencies = []
    choice_latencies = []
    for index, sample in enumerate(SAMPLES):
        sample = dict(sample)
        sample["model"] = model
        payload = json.dumps(sample).encode()
        headers = {"Content-Type": "application/json"}
        if api_key: headers["Authorization"] = "Bearer " + api_key
        req = urllib.request.Request(base_url.rstrip("/") + "/v1/systemone", data=payload, headers=headers, method="POST")
        with opener(req, timeout=120) as response:
            result = json.loads(response.read().decode())
            if response.status != 200: raise RuntimeError(f"self-test returned HTTP {response.status}")
            latencies.append(float(response.headers.get("DM-Latency-Ms", "0")))
        if index == 0: choice_latencies.append(latencies[-1])
        qname = next(iter(sample["questions"]))
        answer = result.get("answers", {}).get(qname)
        if not isinstance(answer, dict) or answer.get("type") != sample["questions"][qname]["type"]:
            raise RuntimeError(f"self-test returned invalid answer schema for {qname}")
        if answer["type"] == "choice":
            probs = answer.get("probabilities", {})
            if answer.get("choice") not in probs or abs(sum(probs.values()) - 1.0) > 1e-3:
                raise RuntimeError("self-test choice probabilities are invalid")
            if answer["choice"] != "orange":
                raise RuntimeError("obvious choice sample did not select orange")
        elif answer["type"] == "score":
            probs = answer.get("probabilities", {})
            if not isinstance(answer.get("score"), (int, float)) or abs(sum(probs.values()) - 1.0) > 1e-3:
                raise RuntimeError("self-test score probabilities are invalid")
        elif answer["type"] == "noul" and not 0 <= answer.get("noul", -1) <= 1:
            raise RuntimeError("self-test noul probability is invalid")
        results.append({"question": qname, "answer": answer})
    # Five latency observations, reusing the first fixed public decision.
    sample = dict(SAMPLES[0])
    sample["model"] = model
    for _ in range(4):
        req = urllib.request.Request(base_url.rstrip("/") + "/v1/systemone", data=json.dumps(sample).encode(),
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + api_key} if api_key else {})}, method="POST")
        with opener(req, timeout=120) as response:
            response.read()
            value = float(response.headers.get("DM-Latency-Ms", "0"))
            latencies.append(value)
            choice_latencies.append(value)
    p50 = statistics.median(choice_latencies[:5])
    if image:
        sample = {"model": model, "state": "A single solid coloured square.", "images": [_red_square()],
                  "questions": {"colour": {"type": "choice", "instructions": "What colour is the square in the attached image?",
                                           "criteria": {"red": "red", "blue": "blue"}}}}
        req = urllib.request.Request(base_url.rstrip("/") + "/v1/multimodal", data=json.dumps(sample).encode(),
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + api_key} if api_key else {})}, method="POST")
        with opener(req, timeout=120) as response:
            result = json.loads(response.read().decode())
            if response.status != 200:
                raise RuntimeError(f"image self-test returned HTTP {response.status}")
        answer = result.get("answers", {}).get("colour", {})
        probs = answer.get("probabilities", {})
        if (answer.get("type") != "choice" or answer.get("choice") != "red" or "red" not in probs
                or abs(sum(probs.values()) - 1.0) > 1e-3):
            raise RuntimeError("image self-test did not recognize the red square with valid choice probabilities")
        results.append({"question": "colour", "answer": answer})
    return {"results": results, "latency_p50_ms_5_runs": round(p50, 3)}
