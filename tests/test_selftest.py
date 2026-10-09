import json
import unittest

from dmlocal.selftest import run


class Response:
    status = 200
    def __init__(self, payload, latency):
        self.payload = payload
        self.headers = {"DM-Latency-Ms": str(latency)}
    def read(self): return json.dumps(self.payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False


class SelftestTests(unittest.TestCase):
    def test_three_fixed_question_types_and_five_choice_latency_runs(self):
        count = {"value": 0}
        def opener(request, timeout=10):
            count["value"] += 1
            payload = json.loads(request.data.decode())
            self.assertEqual(payload["model"], "fixture")
            name, question = next(iter(payload["questions"].items()))
            if question["type"] == "choice":
                answer = {"type": "choice", "choice": "orange", "confidence": 0.9,
                          "probabilities": {"orange": 0.9, "apple": 0.1}}
            elif question["type"] == "noul":
                answer = {"type": "noul", "noul": 0.99}
            else:
                answer = {"type": "score", "score": 1.5, "legend": {"0": "unclear", "1": "partly clear", "2": "clear"},
                          "probabilities": {"0": 0.0, "1": 0.5, "2": 0.5}, "confidence": 0.5}
            return Response({"id": "test", "model": "fixture", "answers": {name: answer},
                             "usage": {"input_tokens": 1, "output_tokens": 0, "decisions": 1}}, count["value"])
        result = run("http://127.0.0.1:8484", model="fixture", opener=opener)
        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(count["value"], 7)
        self.assertEqual(result["latency_p50_ms_5_runs"], 5.0)


if __name__ == "__main__": unittest.main()
