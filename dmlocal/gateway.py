"""Jev-compatible local HTTP gateway implemented with the standard library."""
import base64
import json
import math
import re
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 6 * 1024 * 1024
MAX_STATE = 16 * 1024
MAX_IMAGES = 1
MAX_IMAGE_BYTES = 4 * 1024 * 1024


class DuplicateKeyError(ValueError):
    pass


class RequestLimitExceeded(ValueError):
    pass


class UnsupportedModalityError(Exception):
    pass


class UnknownModelError(Exception):
    pass


class BackendInvalidResponseError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open


def _validate_backend_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password:
        raise ValueError("model backend must be an HTTP URL on 127.0.0.1 or localhost")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate key in JSON")
        result[key] = value
    return result


def decode_json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite number")))


def _finite_probability(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0.0 <= value <= 1.0


def validate_request(body, multimodal=False, max_options=64):
    if not isinstance(body, dict):
        raise ValueError("request must be a JSON object")
    if not isinstance(body.get("model"), str) or not body["model"].strip():
        raise ValueError("model must be a non-empty string")
    if "state" not in body or not isinstance(body["state"], (str, dict, list)):
        raise ValueError("state must be a string, object, or array")
    if len(json.dumps(body["state"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_STATE:
        raise OverflowError("state exceeds 16 KiB")
    questions = body.get("questions")
    if not isinstance(questions, dict):
        raise ValueError("questions must be an object")
    if len(questions) != 1:
        raise RequestLimitExceeded("exactly one named question is supported")
    name, question = next(iter(questions.items()))
    if not isinstance(name, str) or not name.strip() or not isinstance(question, dict):
        raise ValueError("question names must be non-empty and question values must be objects")
    qtype = question.get("type")
    if qtype not in ("choice", "noul", "score"):
        raise ValueError("question type must be choice, noul, or score")
    instructions = question.get("instructions", "")
    if not isinstance(instructions, (str, dict, list, type(None))):
        raise ValueError("instructions must be a string, object, array, or null")
    criteria = question.get("criteria")
    if qtype == "choice":
        if not isinstance(criteria, dict) or len(criteria) < 2:
            raise ValueError("choice criteria must be an object with at least two options")
        if len(criteria) > max_options:
            raise ValueError(f"choice supports at most {max_options} options")
        if any(not isinstance(k, str) or not k for k in criteria):
            raise ValueError("choice option ids must be non-empty strings")
    elif qtype == "score":
        if not isinstance(criteria, list) or len(criteria) < 2:
            raise ValueError("score criteria must be an ordered array with at least two levels")
        if len(criteria) > max_options:
            raise ValueError(f"score supports at most {max_options} levels")
    elif criteria is not None and not (isinstance(criteria, dict) and set(criteria) == {"true", "false"}):
        raise ValueError("noul criteria, when supplied, must be an object with true and false keys")
    images = body.get("images", [])
    if images is None: images = []
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError("at most one image is supported")
    if images and not multimodal:
        raise ValueError("images are not accepted on /v1/systemone")
    for image in images:
        if not isinstance(image, str) or not image.startswith("data:image/") or ";base64," not in image:
            raise ValueError("images must be bounded PNG, JPEG, or WebP data URLs")
        mime, encoded = image[5:].split(";base64,", 1)
        if mime not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError("image MIME type must be PNG, JPEG, or WebP")
        try: raw = base64.b64decode(encoded, validate=True)
        except ValueError as exc: raise ValueError("image data URL contains invalid base64") from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise OverflowError("decoded image exceeds 4 MiB")
        if not _image_dimensions_ok(mime, raw):
            raise ValueError("image dimensions must be valid and no larger than 2,000,000 pixels")
    return name, question


def _image_dimensions_ok(mime, data):
    """Read dimensions from common image headers without decoding image content."""
    try:
        if mime == "image/png":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24: return False
            width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        elif mime == "image/jpeg":
            if data[:2] != b"\xff\xd8": return False
            pos, width, height = 2, None, None
            while pos + 4 <= len(data):
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                marker = data[pos + 1]
                pos += 2
                while marker == 0xFF and pos < len(data):
                    marker = data[pos]
                    pos += 1
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7: continue
                if pos + 2 > len(data): break
                size = int.from_bytes(data[pos:pos + 2], "big")
                if size < 2 or pos + size > len(data): break
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height = int.from_bytes(data[pos + 3:pos + 5], "big")
                    width = int.from_bytes(data[pos + 5:pos + 7], "big")
                    break
                pos += size
            if not width or not height: return False
        elif mime == "image/webp":
            if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP": return False
            kind = data[12:16]
            if kind == b"VP8X":
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
            elif kind == b"VP8L" and data[20] == 0x2F:
                bits = int.from_bytes(data[21:25], "little")
                width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            else:
                return False
        else:
            return False
        return width > 0 and height > 0 and width * height <= 2_000_000
    except (IndexError, ValueError):
        return False


def _http_json(url, payload, timeout=60, opener=None):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with (opener or _LOCAL_OPENER)(request, timeout=timeout) as response:
        status = getattr(response, "status", None)
        if status is None: status = response.getcode()
        return status, decode_json(response.read())


def _check_distribution(probabilities, keys):
    if not isinstance(probabilities, dict) or set(probabilities) != set(keys):
        raise ValueError("backend probabilities must cover the requested options exactly")
    if not all(_finite_probability(v) for v in probabilities.values()):
        raise ValueError("backend returned a non-finite or out-of-range probability")
    total = sum(probabilities.values())
    if abs(total - 1.0) > 1e-3:
        raise ValueError("backend probabilities do not sum to one")
    return {k: v / total for k, v in probabilities.items()}


def normalize_jev(result, request, qname, question):
    if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
        raise ValueError("backend response has no answers object")
    answer = result["answers"].get(qname)
    if not isinstance(answer, dict):
        raise ValueError("backend response is missing the named answer")
    qtype = question["type"]
    out = {"type": qtype}
    if qtype == "choice":
        options = list(question["criteria"])
        probs = _check_distribution(answer.get("probabilities"), options)
        choice = answer.get("choice")
        if choice not in options:
            raise ValueError("backend selected an unknown choice option")
        expected_choice = max(options, key=lambda key: probs[key])
        if choice != expected_choice:
            raise ValueError("backend choice does not match its highest probability; ties use the first option")
        confidence = answer.get("confidence", probs[choice])
        if not _finite_probability(confidence) or abs(confidence - probs[choice]) > 1e-3:
            raise ValueError("backend confidence is invalid")
        out.update(choice=choice, confidence=confidence, probabilities=probs)
    elif qtype == "noul":
        value = answer.get("noul", answer.get("probability_true"))
        if not _finite_probability(value):
            raise ValueError("backend noul probability is invalid")
        out.update(noul=value, probabilities={"true": value, "false": 1.0 - value})
    else:
        levels = question["criteria"]
        keys = [str(i) for i in range(len(levels))]
        probs = _check_distribution(answer.get("probabilities"), keys)
        score = sum(i * probs[str(i)] for i in range(len(levels)))
        legend = {str(i): value for i, value in enumerate(levels)}
        out.update(score=score, legend=legend, probabilities=probs,
                   confidence=answer.get("confidence", max(probs.values())))
        if not _finite_probability(out["confidence"]):
            raise ValueError("backend confidence is invalid")
    usage = result.get("usage")
    if not isinstance(usage, dict) or not all(_nonnegative_int(usage.get(k)) == usage.get(k) for k in ("input_tokens", "output_tokens")):
        raise ValueError("backend did not provide valid token usage")
    return {"id": str(result.get("id") or "dec_" + uuid.uuid4().hex[:20]),
            "model": request["model"], "answers": {qname: out},
            "usage": {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"], "decisions": 1}}


def _nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _softmax(logprobs):
    maximum = max(logprobs.values())
    values = {key: math.exp(value - maximum) for key, value in logprobs.items()}
    total = sum(values.values())
    return {key: value / total for key, value in values.items()}


def _letter_probabilities(data, letters):
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("completion backend returned no choices")
    lp = (choices[0].get("logprobs") or {}).get("top_logprobs") or []
    if not lp or not isinstance(lp[0], dict):
        raise ValueError("completion backend returned no top token log-probabilities")
    normalized = {}
    for token, value in lp[0].items():
        letter = token.strip()
        if letter in letters and isinstance(value, (int, float)) and math.isfinite(value):
            normalized[letter] = float(value)
    if set(normalized) != set(letters):
        raise ValueError("completion backend did not return every option letter")
    return _softmax(normalized)


def letter_logprobs(backend_url, config, request, qname, question, opener=None):
    qtype = question["type"]
    if qtype == "choice":
        option_ids = list(question["criteria"])
        option_values = question["criteria"]
    elif qtype == "noul":
        option_ids, option_values = ["true", "false"], {"true": "Yes", "false": "No"}
    else:
        option_ids = [str(i) for i in range(len(question["criteria"]))]
        option_values = {str(i): question["criteria"][i] for i in range(len(option_ids))}
    if len(option_ids) > 20:
        raise ValueError("letter_logprobs supports at most 20 options because it requests logprobs=20")
    letters = [chr(ord("A") + i) for i in range(len(option_ids))]
    options = "\n".join(f"{letter}. {key}: {json.dumps(option_values[key], ensure_ascii=False)}" for letter, key in zip(letters, option_ids))
    template = config.get("prompt_template") or "{state}\n\nQuestion: {instructions}\nOptions:\n{options}\nAnswer with one letter only:"
    prompt = template.format(state=json.dumps(request["state"], ensure_ascii=False), instructions=json.dumps(question.get("instructions", ""), ensure_ascii=False), options=options)
    payload = {"model": config.get("model", request["model"]), "prompt": prompt, "max_tokens": 1,
               "temperature": 0, "logprobs": 20, "stream": False}
    if config.get("extra_body") and isinstance(config["extra_body"], dict): payload.update(config["extra_body"])
    status, data = _http_json(backend_url.rstrip("/") + "/v1/completions", payload, opener=opener)
    if status < 200 or status >= 300:
        raise RuntimeError("completion backend returned an error")
    letter_probs = _letter_probabilities(data, letters)
    probs = {key: letter_probs[letter] for key, letter in zip(option_ids, letters)}
    usage = data.get("usage") or {}
    if not isinstance(usage, dict) or not all(_nonnegative_int(usage.get(k)) == usage.get(k) for k in ("prompt_tokens", "completion_tokens")):
        raise ValueError("completion backend did not provide valid token usage")
    result = {"id": "dec_" + uuid.uuid4().hex[:20], "model": request["model"], "answers": {},
              "usage": {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"], "decisions": 1}}
    if qtype == "choice":
        selected = max(option_ids, key=lambda key: probs[key])
        result["answers"][qname] = {"type": qtype, "choice": selected, "confidence": probs[selected], "probabilities": probs}
    elif qtype == "noul":
        result["answers"][qname] = {"type": qtype, "noul": probs["true"], "probabilities": probs}
    else:
        score = sum(int(k) * value for k, value in probs.items())
        result["answers"][qname] = {"type": qtype, "score": score,
            "legend": {str(i): value for i, value in enumerate(question["criteria"])},
            "probabilities": probs, "confidence": max(probs.values())}
    return result


class Gateway:
    def __init__(self, backend_url, backend_mode="proxy_jev", backend_model=None, prompt_config=None,
                 model_card=None, api_key=None, opener=None, max_options=64):
        _validate_backend_url(backend_url)
        self.backend_url = backend_url.rstrip("/")
        self.backend_mode = backend_mode
        self.backend_model = backend_model
        self.prompt_config = prompt_config or {}
        self.model_card = model_card or {}
        self.api_key = api_key
        self.opener = opener or _LOCAL_OPENER
        self.max_options = int(max_options)

    def infer(self, request, multimodal=False):
        qname, question = validate_request(request, multimodal=multimodal, max_options=self.max_options)
        slug = self.model_card.get("slug")
        if slug and request.get("model") != slug:
            raise UnknownModelError("the requested model is not installed on this gateway")
        supported = self.model_card.get("question_types")
        if supported is not None and (question["type"] not in supported or supported[question["type"]] in (None, False, "unsupported")):
            raise UnsupportedModalityError("this model does not support the requested question type")
        if multimodal and not request.get("images"):
            raise ValueError("/v1/multimodal requires at least one image")
        if multimodal and request.get("images") and "image" not in self.model_card.get("modalities", ["text", "image"]):
            raise UnsupportedModalityError("this model does not support images")
        request = dict(request)
        request["model"] = self.backend_model or request["model"]
        try:
            if self.backend_mode == "letter_logprobs":
                if request.get("images"):
                    raise UnsupportedModalityError("letter_logprobs does not support image input")
                raw = letter_logprobs(self.backend_url, self.prompt_config, request, qname, question, opener=self.opener)
            elif self.backend_mode == "proxy_jev":
                status, raw = _http_json(self.backend_url, request, opener=self.opener)
                if status < 200 or status >= 300:
                    raise RuntimeError("model backend returned an error")
            else:
                raise RuntimeError("unknown gateway backend mode")
            normalized = normalize_jev(raw, request, qname, question)
        except UnsupportedModalityError:
            raise
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            raise BackendInvalidResponseError("backend response did not meet the Jev-compatible schema") from exc
        normalized["model"] = self.model_card.get("slug", request.get("model"))
        return normalized


def make_handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        server_version = "dm-local"
        sys_version = ""

        def _send(self, code, payload, headers=None):
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items(): self.send_header(key, str(value))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, code, name, message, retryable=False, status=400):
            self._send(status, {"error": {"code": name, "message": message, "request_id": "req_" + uuid.uuid4().hex[:16], "retryable": retryable}})

        def do_GET(self):
            if gateway.api_key and self.headers.get("Authorization") != "Bearer " + gateway.api_key:
                self._error(401, "invalid_api_key", "A valid bearer token is required.", status=401)
                return
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            elif self.path == "/v1/models":
                card = {k: gateway.model_card[k] for k in ("slug", "name", "modalities", "question_types") if k in gateway.model_card}
                self._send(200, {"data": [card], "object": "list"})
            else:
                self._error(404, "unknown_model", "Endpoint not found.", status=404)

        def do_POST(self):
            if self.path not in ("/v1/systemone", "/v1/multimodal"):
                self._error(404, "unknown_model", "Endpoint not found.", status=404)
                return
            if gateway.api_key and self.headers.get("Authorization") != "Bearer " + gateway.api_key:
                self._error(401, "invalid_api_key", "A valid bearer token is required.", status=401)
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self._error(400, "invalid_request", "Content-Length is required.")
                return
            if length > MAX_BODY:
                self._error(413, "payload_too_large", "Request exceeds 6 MiB.", status=413)
                return
            started = time.monotonic()
            try:
                request = decode_json(self.rfile.read(length))
                multimodal = self.path == "/v1/multimodal"
                result = gateway.infer(request, multimodal=multimodal)
                elapsed = (time.monotonic() - started) * 1000
                self._send(200, result, {"DM-Model": result["model"], "DM-Latency-Ms": f"{elapsed:.3f}"})
            except OverflowError as exc:
                self._error(413, "payload_too_large", str(exc), status=413)
            except RequestLimitExceeded as exc:
                self._error(400, "request_limit_exceeded", str(exc), status=400)
            except UnsupportedModalityError as exc:
                self._error(422, "unsupported_modality", str(exc), status=422)
            except UnknownModelError as exc:
                self._error(404, "unknown_model", str(exc), status=404)
            except BackendInvalidResponseError:
                self._error(503, "model_unavailable", "The local model backend returned an invalid response.", retryable=True, status=503)
            except (ValueError, DuplicateKeyError, UnicodeDecodeError) as exc:
                self._error(400, "invalid_request", str(exc))
            except (urllib.error.URLError, TimeoutError, RuntimeError, OSError):
                self._error(503, "model_unavailable", "The local model backend is unavailable.", retryable=True, status=503)
            except Exception:
                self._error(503, "model_unavailable", "The local model backend returned an invalid response.", retryable=True, status=503)

        def log_message(self, fmt, *args):
            # Do not log request bodies, headers, or answers.
            super().log_message("%s", "HTTP request handled")

    return Handler


def serve(host, port, gateway):
    server = ThreadingHTTPServer((host, port), make_handler(gateway))
    server.daemon_threads = True
    try: server.serve_forever(poll_interval=0.25)
    finally: server.server_close()
