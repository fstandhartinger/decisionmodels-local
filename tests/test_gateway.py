import http.client
import base64
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dmlocal.gateway import Gateway, make_handler, normalize_jev, validate_request

CHOICE = {"model": "fixture", "state": "Mia owns a red bicycle.", "questions": {"color": {
    "type": "choice", "instructions": "What color is the bicycle?", "criteria": {"red": None, "blue": None}}}}


class FakeResponse:
    status = 200
    def __init__(self, body): self.body = json.dumps(body).encode()
    def read(self): return self.body
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): return False


class GatewayTests(unittest.TestCase):
    def test_request_schema_and_duplicate_key_rejection(self):
        qname, question = validate_request(CHOICE)
        self.assertEqual(qname, "color")
        self.assertEqual(question["type"], "choice")
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            from dmlocal.gateway import decode_json
            decode_json(b'{"model":"a","model":"b"}')
        invalid = dict(CHOICE); invalid["questions"] = {"a": {"type": "choice", "criteria": {"x": 1}} , "b": {}}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_request(invalid)

    def test_proxy_jev_maps_model_and_normalizes_probabilities(self):
        def opener(request, timeout=10):
            payload = json.loads(request.data.decode())
            self.assertEqual(payload["model"], "author-model-id")
            return FakeResponse({"id": "raw-id", "answers": {"color": {
                "type": "choice", "choice": "red", "confidence": 0.8,
                "probabilities": {"red": 0.8, "blue": 0.2}}},
                "usage": {"input_tokens": 12, "output_tokens": 0}})
        gateway = Gateway("http://127.0.0.1:9/jev", "proxy_jev", "author-model-id", model_card={"slug": "fixture"}, opener=opener)
        result = gateway.infer(CHOICE)
        self.assertEqual(result["model"], "fixture")
        self.assertEqual(result["answers"]["color"]["choice"], "red")
        self.assertEqual(result["usage"], {"input_tokens": 12, "output_tokens": 0, "decisions": 1})

    def test_proxy_rejects_probability_sum_error(self):
        raw = {"answers": {"color": {"choice": "red", "probabilities": {"red": 0.7, "blue": 0.2}}}}
        with self.assertRaisesRegex(ValueError, "sum to one"):
            normalize_jev(raw, CHOICE, "color", CHOICE["questions"]["color"])

    def test_author_rounded_distribution_ties_and_score_are_preserved(self):
        probabilities = {"red": 0.4999, "blue": 0.4999}
        raw = {"answers": {"color": {"choice": "blue", "confidence": 0.72, "probabilities": probabilities}},
               "usage": {"input_tokens": 4, "output_tokens": 0}}
        answer = normalize_jev(raw, CHOICE, "color", CHOICE["questions"]["color"])["answers"]["color"]
        self.assertEqual(answer["probabilities"], probabilities)
        self.assertEqual(answer["choice"], "blue")
        self.assertEqual(answer["confidence"], 0.72)
        question = {"type": "score", "criteria": ["low", "medium", "high"]}
        probabilities = {"0": 0.3333, "1": 0.3333, "2": 0.3333}
        raw["answers"]["color"] = {"score": 1.0, "confidence": 0.6, "probabilities": probabilities}
        answer = normalize_jev(raw, CHOICE, "color", question)["answers"]["color"]
        self.assertEqual(answer["score"], 1.0)
        self.assertEqual(answer["probabilities"], probabilities)

    def test_usage_without_output_tokens_is_accepted_as_zero(self):
        raw = {"answers": {"color": {"choice": "red", "probabilities": {"red": 0.7, "blue": 0.3}}}, "usage": {"input_tokens": 12}}
        out = normalize_jev(raw, CHOICE, "color", CHOICE["questions"]["color"])
        self.assertEqual(out["usage"]["output_tokens"], 0)
        raw["usage"] = {"input_tokens": "x"}
        with self.assertRaisesRegex(ValueError, "token usage"):
            normalize_jev(raw, CHOICE, "color", CHOICE["questions"]["color"])

    def test_author_discrete_score_is_accepted_only_when_it_is_the_most_likely_level(self):
        question = {"type": "score", "criteria": ["low", "medium", "high"]}
        probabilities = {"0": 0.003, "1": 0.01, "2": 0.987}
        raw = {"answers": {"color": {"score": 2, "probabilities": probabilities}}, "usage": {"input_tokens": 4, "output_tokens": 0}}
        answer = normalize_jev(raw, CHOICE, "color", question)["answers"]["color"]
        self.assertEqual(answer["score"], 2)
        raw["answers"]["color"] = {"score": 1.97, "probabilities": {"0": 0.0, "1": 0.02, "2": 0.98}}
        self.assertEqual(normalize_jev(raw, CHOICE, "color", question)["answers"]["color"]["score"], 1.97)
        raw["answers"]["color"] = {"score": 1, "probabilities": probabilities}
        with self.assertRaisesRegex(ValueError, "disagrees"):
            normalize_jev(raw, CHOICE, "color", question)

    def test_letter_logprobs_choice_and_noul_score(self):
        bodies = [
            {"choices": [{"logprobs": {"top_logprobs": [{" A": -0.1, " B": -2.0}]}}],
             "usage": {"prompt_tokens": 15, "completion_tokens": 1}},
        ]
        def opener(request, timeout=10):
            if b"Clarity" in request.data:
                return FakeResponse({"choices": [{"logprobs": {"top_logprobs": [{" A": -2.0, " B": -0.1}]}}],
                                     "usage": {"prompt_tokens": 15, "completion_tokens": 1}})
            return FakeResponse(bodies[0])
        gateway = Gateway("http://127.0.0.1:9", "letter_logprobs", prompt_config={"prompt_template": "{state}\n{instructions}\n{options}"},
                          model_card={"slug": "fixture"}, opener=opener)
        choice = gateway.infer(CHOICE)
        self.assertEqual(choice["answers"]["color"]["choice"], "red")
        self.assertAlmostEqual(sum(choice["answers"]["color"]["probabilities"].values()), 1.0)
        noul = {"model": "fixture", "state": "Water freezes at 0C.", "questions": {"q": {"type": "noul", "instructions": "True?"}}}
        yesno = gateway.infer(noul)
        self.assertGreater(yesno["answers"]["q"]["noul"], 0.5)
        score = {"model": "fixture", "state": "A plain sentence.", "questions": {"q": {"type": "score", "instructions": "Clarity?", "criteria": ["low", "high"]}}}
        scored = gateway.infer(score)
        self.assertGreater(scored["answers"]["q"]["score"], 0.5)
        self.assertEqual(scored["answers"]["q"]["legend"], {"0": "low", "1": "high"})

    def test_letter_logprobs_accepts_modern_content_logprobs(self):
        def opener(request, timeout=10):
            return FakeResponse({"choices": [{"logprobs": {"content": [{"top_logprobs": [
                {"token": " A", "logprob": -0.1}, {"token": " B", "logprob": -2.0}]}]}}],
                "usage": {"prompt_tokens": 41, "completion_tokens": 1}})
        gateway = Gateway("http://127.0.0.1:9", "letter_logprobs", model_card={"slug": "fixture"}, opener=opener)
        answer = gateway.infer(CHOICE)["answers"]["color"]
        self.assertEqual(answer["choice"], "red")
        self.assertGreater(answer["probabilities"]["red"], answer["probabilities"]["blue"])

    def setUp(self):
        def opener(request, timeout=10):
            return FakeResponse({"answers": {"color": {"choice": "red", "confidence": 1,
                "probabilities": {"red": 1.0, "blue": 0.0}}}, "usage": {"input_tokens": 2, "output_tokens": 0}})
        self.gateway = Gateway("http://127.0.0.1:9", "proxy_jev", model_card={"slug": "fixture", "name": "Fixture",
            "modalities": ["text"], "question_types": {"choice": "native"}}, api_key="topsecret", opener=opener)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.gateway))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def post(self, path, body, auth=True):
        headers = {"Content-Type": "application/json"}
        if auth: headers["Authorization"] = "Bearer topsecret"
        req = Request(self.base + path, data=body, headers=headers, method="POST")
        return urlopen(req, timeout=2)

    def test_gateway_rejects_missing_bearer_and_duplicate_keys(self):
        with self.assertRaises(HTTPError) as error:
            self.post("/v1/systemone", json.dumps(CHOICE).encode(), auth=False)
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "invalid_api_key")
        with self.assertRaises(HTTPError) as error:
            self.post("/v1/systemone", b'{"model":"fixture","model":"duplicate"}')
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "invalid_request")

    def test_gateway_request_limit_unknown_model_and_unsupported_modality_codes(self):
        multiple = json.loads(json.dumps(CHOICE))
        multiple["questions"]["extra"] = {"type": "noul", "instructions": "Is this a test?"}
        with self.assertRaises(HTTPError) as error:
            self.post("/v1/systemone", json.dumps(multiple).encode())
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "request_limit_exceeded")
        unknown = json.loads(json.dumps(CHOICE)); unknown["model"] = "other-model"
        with self.assertRaises(HTTPError) as error:
            self.post("/v1/systemone", json.dumps(unknown).encode())
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "unknown_model")
        image = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1).to_bytes(4, "big") * 2
        multimodal = json.loads(json.dumps(CHOICE)); multimodal["images"] = ["data:image/png;base64," + base64.b64encode(image).decode()]
        with self.assertRaises(HTTPError) as error:
            self.post("/v1/multimodal", json.dumps(multimodal).encode())
        self.assertEqual(error.exception.code, 422)
        self.assertEqual(json.loads(error.exception.read())["error"]["code"], "unsupported_modality")

    def test_gateway_size_limit_and_headers(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.putrequest("POST", "/v1/systemone")
        connection.putheader("Content-Length", str(6 * 1024 * 1024 + 1))
        connection.putheader("Authorization", "Bearer topsecret")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 413)
        self.assertEqual(json.loads(response.read())["error"]["code"], "payload_too_large")
        connection.close()
        with self.post("/v1/systemone", json.dumps(CHOICE).encode()) as ok:
            payload = json.loads(ok.read())
            self.assertEqual(ok.status, 200)
            self.assertEqual(ok.headers["DM-Model"], "fixture")
            self.assertIn("DM-Latency-Ms", ok.headers)
            self.assertEqual(payload["answers"]["color"]["choice"], "red")

    def test_gateway_health_and_model_list(self):
        with urlopen(Request(self.base + "/health", headers={"Authorization": "Bearer topsecret"})) as response:
            self.assertEqual(json.loads(response.read())["status"], "ok")
        with urlopen(Request(self.base + "/v1/models", headers={"Authorization": "Bearer topsecret"})) as response:
            self.assertEqual(json.loads(response.read())["data"][0]["slug"], "fixture")


if __name__ == "__main__": unittest.main()
