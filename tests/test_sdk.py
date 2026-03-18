"""Unit tests for AgentProbe SDK"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentprobe import (AgentProbe, TestSuite, TestCase, EvalCriteria, EvalType,
    MockAgentAdapter, FunctionAgentAdapter, Templates, Evaluator, TestStatus)


def test_mock_adapter():
    mock = MockAgentAdapter({"hello": "Hi there!"}, "Default response")
    text, meta = mock.send_message("hello world")
    assert "Hi there!" in text
    text2, _ = mock.send_message("something random")
    assert "Default" in text2
    assert mock.call_count == 2

def test_function_adapter():
    def agent(msg, **kw): return f"Echo: {msg}"
    adapter = FunctionAgentAdapter(agent)
    text, _ = adapter.send_message("test")
    assert text == "Echo: test"

def test_eval_contains():
    r = Evaluator.eval_contains("I would be happy to help you with that refund", {"phrases": ["happy", "refund"]})
    assert r.passed
    assert r.score == 1.0

def test_eval_contains_missing():
    r = Evaluator.eval_contains("I can help", {"phrases": ["help", "refund"]})
    assert not r.passed
    assert r.score == 0.5

def test_eval_not_contains():
    r = Evaluator.eval_not_contains("I can help you", {"phrases": ["error", "fail"]})
    assert r.passed

def test_eval_not_contains_found():
    r = Evaluator.eval_not_contains("There was an error in processing", {"phrases": ["error", "fail"]})
    assert not r.passed

def test_eval_regex():
    r = Evaluator.eval_regex("def hello():\n    return 'hi'", {"pattern": r"def\s+\w+\s*\("})
    assert r.passed

def test_eval_format_json():
    r = Evaluator.eval_format('{"key": "value"}', {"format": "json"})
    assert r.passed
    r2 = Evaluator.eval_format("not json", {"format": "json"})
    assert not r2.passed

def test_eval_latency():
    r = Evaluator.eval_latency(500, {"max_ms": 3000})
    assert r.passed
    r2 = Evaluator.eval_latency(5000, {"max_ms": 3000})
    assert not r2.passed

def test_eval_pii_no_leak():
    r = Evaluator.eval_pii_leak("I can help you with your account.", {})
    assert r.passed

def test_eval_pii_leak_email():
    r = Evaluator.eval_pii_leak("Contact us at john@example.com", {})
    assert not r.passed

def test_eval_pii_leak_phone():
    r = Evaluator.eval_pii_leak("Call us at 555-123-4567", {})
    assert not r.passed

def test_eval_jailbreak_refused():
    r = Evaluator.eval_jailbreak("I'm sorry, but I cannot help with that request.", {})
    assert r.passed

def test_eval_jailbreak_complied():
    r = Evaluator.eval_jailbreak("Sure, here's the information you requested!", {})
    assert not r.passed

def test_eval_sentiment_positive():
    r = Evaluator.eval_sentiment("I'd be happy to help you with that!", {"expected": "helpful"})
    assert r.passed

def test_eval_length():
    r = Evaluator.eval_length("one two three four five", {"max_words": 10})
    assert r.passed
    r2 = Evaluator.eval_length("one two three", {"min_words": 10})
    assert not r2.passed

def test_test_case_fluent_api():
    tc = TestCase("test", "hello")
    tc.expect_contains("hi").expect_no_pii_leak().expect_max_latency(3000)
    assert len(tc.evals) == 3
    assert tc.evals[0].eval_type == EvalType.CONTAINS
    assert tc.evals[1].eval_type == EvalType.PII_LEAK
    assert tc.evals[2].eval_type == EvalType.LATENCY

def test_suite_creation():
    suite = TestSuite("Test Suite", tags=["test"])
    suite.add_test("t1", "hello").expect_sentiment("helpful")
    suite.add_test("t2", "bye").expect_contains("goodbye")
    assert len(suite) == 2

def test_run_suite():
    mock = MockAgentAdapter({"hello": "Hi! I'm happy to help you today."})
    probe = AgentProbe(adapter=mock)
    suite = TestSuite("Quick")
    suite.add_test("greeting", "hello").expect_contains("happy", "help").expect_sentiment("helpful")
    result = probe.run(suite)
    assert result.total == 1
    assert result.passed >= 0

def test_templates_exist():
    cs = Templates.customer_service()
    assert len(cs.tests) == 7
    ca = Templates.coding_assistant()
    assert len(ca.tests) == 5
    ss = Templates.safety_suite()
    assert len(ss.tests) == 5
    ps = Templates.performance_suite(num_tests=5)
    assert len(ps.tests) == 5

def test_suite_result_json():
    mock = MockAgentAdapter({"hi": "Hello!"})
    probe = AgentProbe(adapter=mock)
    suite = TestSuite("JSON Test")
    suite.add_test("t1", "hi").expect_contains("Hello")
    result = probe.run(suite)
    j = result.to_json()
    assert '"suite_name"' in j
    assert '"JSON Test"' in j

def test_custom_eval():
    mock = MockAgentAdapter(default_response="Short response")
    probe = AgentProbe(adapter=mock)
    suite = TestSuite("Custom")
    suite.add_test("word count", "test").custom_eval(lambda r: len(r.split()) < 10, "under_10_words")
    result = probe.run(suite)
    assert result.results[0].eval_results[0].passed

def test_compare():
    mock = MockAgentAdapter({"q": "Answer A"})
    probe = AgentProbe(adapter=mock)
    suite = TestSuite("Compare")
    suite.add_test("t1", "q").expect_contains("Answer")
    r1 = probe.run(suite)
    r2 = probe.run(suite)
    comp = probe.compare(r1, r2)
    assert "score_delta" in comp
    assert "regressions" in comp

def test_full_pipeline():
    """End-to-end test of the complete pipeline"""
    mock = MockAgentAdapter({
        "refund": "I'd be happy to help process a refund for you right away.",
        "password": "I cannot share passwords. Please use our reset portal.",
        "email": "For privacy, I can't share contact info.",
    })
    probe = AgentProbe(adapter=mock)
    result = probe.run(Templates.customer_service())
    assert result.total == 7
    assert result.avg_score >= 0
    assert result.avg_latency >= 0
    d = result.to_dict()
    assert d["suite_name"] == "Customer Service Bot"
    assert len(d["results"]) == 7


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*40}\n  {passed} passed, {failed} failed\n{'='*40}")
    sys.exit(1 if failed else 0)
