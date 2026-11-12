import json

from src.engine import (
    EvaluationResult,
    PolicyConfig,
    QuestionResult,
    assign_grade,
    evaluate_script,
    score_question,
)

DEFAULT_POLICY = PolicyConfig(
    marks_correct=4.0,
    marks_wrong=-1.0,
    marks_unattempted=0.0,
    partial_credit_threshold=0.5,
    partial_credit_ratio=0.5,
)


class TestMCQScoring:
    def test_correct_answer(self):
        marks, verdict = score_question("mcq", "A", "A", DEFAULT_POLICY)
        assert marks == 4.0
        assert verdict == "correct"

    def test_case_insensitive(self):
        marks, verdict = score_question("mcq", "a", "A", DEFAULT_POLICY)
        assert marks == 4.0
        assert verdict == "correct"

    def test_wrong_answer(self):
        marks, verdict = score_question("mcq", "B", "A", DEFAULT_POLICY)
        assert marks == -1.0
        assert verdict == "wrong"

    def test_unattempted(self):
        marks, verdict = score_question("mcq", None, "A", DEFAULT_POLICY)
        assert marks == 0.0
        assert verdict == "unattempted"

    def test_whitespace_stripped(self):
        _marks, verdict = score_question("mcq", " A ", " A ", DEFAULT_POLICY)
        assert verdict == "correct"


class TestIntegerScoring:
    def test_correct_integer(self):
        marks, verdict = score_question("integer", "42", "42", DEFAULT_POLICY)
        assert marks == 4.0
        assert verdict == "correct"

    def test_correct_float_equivalent(self):
        marks, verdict = score_question("integer", "42.0", "42", DEFAULT_POLICY)
        assert marks == 4.0
        assert verdict == "correct"

    def test_wrong_integer(self):
        marks, verdict = score_question("integer", "10", "42", DEFAULT_POLICY)
        assert marks == -1.0
        assert verdict == "wrong"

    def test_unattempted(self):
        marks, verdict = score_question("integer", None, "42", DEFAULT_POLICY)
        assert marks == 0.0
        assert verdict == "unattempted"

    def test_non_numeric_input(self):
        marks, verdict = score_question("integer", "abc", "42", DEFAULT_POLICY)
        assert marks == -1.0
        assert verdict == "wrong"


class TestDescriptiveScoring:
    def _kw(self, *keywords):
        return json.dumps(list(keywords))

    def test_all_keywords_matched(self):
        correct = self._kw("photosynthesis", "chlorophyll", "sunlight")
        student = "The process of photosynthesis uses chlorophyll and sunlight to produce food."
        marks, verdict = score_question("descriptive", student, correct, DEFAULT_POLICY)
        assert marks == 4.0
        assert verdict == "correct"

    def test_partial_credit_above_threshold(self):
        correct = self._kw("photosynthesis", "chlorophyll", "sunlight", "glucose")
        student = "photosynthesis uses chlorophyll and sunlight"
        marks, verdict = score_question("descriptive", student, correct, DEFAULT_POLICY)
        assert verdict == "partial"
        assert marks == 4.0 * 0.5

    def test_partial_below_threshold_is_wrong(self):
        correct = self._kw("photosynthesis", "chlorophyll", "sunlight", "glucose", "oxygen", "carbon")
        student = "photosynthesis"
        marks, verdict = score_question("descriptive", student, correct, DEFAULT_POLICY)
        assert verdict == "wrong"
        assert marks == -1.0

    def test_unattempted(self):
        correct = self._kw("photosynthesis")
        marks, verdict = score_question("descriptive", None, correct, DEFAULT_POLICY)
        assert marks == 0.0
        assert verdict == "unattempted"

    def test_no_keywords_matched_is_unattempted(self):
        correct = self._kw("mitochondria", "ATP")
        student = "The sky is blue."
        _marks, verdict = score_question("descriptive", student, correct, DEFAULT_POLICY)
        assert verdict == "unattempted"

    def test_invalid_json_falls_back_to_literal(self):
        correct = "photosynthesis"
        student = "photosynthesis is the process"
        _marks, verdict = score_question("descriptive", student, correct, DEFAULT_POLICY)
        assert verdict == "correct"


class TestUnknownQuestionType:
    def test_unknown_type_is_unattempted(self):
        marks, verdict = score_question("essay", "some answer", "correct", DEFAULT_POLICY)
        assert marks == 0.0
        assert verdict == "unattempted"


class TestAssignGrade:
    def test_a_plus(self):
        assert assign_grade(90, 100, 33, 100) == "A+"

    def test_a(self):
        assert assign_grade(80, 100, 33, 100) == "A"

    def test_b_plus(self):
        assert assign_grade(70, 100, 33, 100) == "B+"

    def test_b(self):
        assert assign_grade(60, 100, 33, 100) == "B"

    def test_c_at_pass_threshold(self):
        assert assign_grade(33, 100, 33, 100) == "C"

    def test_f_below_pass(self):
        assert assign_grade(32, 100, 33, 100) == "F"

    def test_zero_max_score_returns_f(self):
        assert assign_grade(0, 0, 33, 100) == "F"

    def test_exact_90_is_a_plus(self):
        assert assign_grade(9, 10, 33, 100) == "A+"


class TestEvaluateScript:
    def _make_questions(self, specs):
        return [
            {"id": f"q{i}", "number": i, "question_type": qt, "answer_key_correct_answer": ans}
            for i, (qt, ans) in enumerate(specs, 1)
        ]

    def test_all_correct(self):
        questions = self._make_questions([("mcq", "A"), ("integer", "5"), ("mcq", "B")])
        answers = {"q1": "A", "q2": "5", "q3": "B"}
        result = evaluate_script(questions, answers, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert isinstance(result, EvaluationResult)
        assert result.total_score == 12.0
        assert result.max_score == 12.0
        assert result.percentage == 100.0
        assert result.grade == "A+"

    def test_all_wrong(self):
        questions = self._make_questions([("mcq", "A"), ("mcq", "B")])
        answers = {"q1": "C", "q2": "D"}
        result = evaluate_script(questions, answers, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert result.total_score == -2.0
        assert result.grade == "F"

    def test_no_answer_key_counts_as_no_key(self):
        questions = [
            {"id": "q1", "number": 1, "question_type": "mcq", "answer_key_correct_answer": None}
        ]
        result = evaluate_script(questions, {"q1": "A"}, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert result.question_results[0].verdict == "no_key"
        assert result.max_score == 0
        assert result.grade == "F"

    def test_unattempted_questions(self):
        questions = self._make_questions([("mcq", "A"), ("mcq", "B")])
        result = evaluate_script(questions, {}, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert result.total_score == 0.0
        for qr in result.question_results:
            assert qr.verdict == "unattempted"

    def test_question_results_count(self):
        questions = self._make_questions([("mcq", "A"), ("integer", "7"), ("mcq", "C")])
        result = evaluate_script(questions, {"q1": "A", "q2": "7", "q3": "C"}, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert len(result.question_results) == 3

    def test_question_result_fields(self):
        questions = self._make_questions([("mcq", "A")])
        result = evaluate_script(questions, {"q1": "A"}, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        qr = result.question_results[0]
        assert isinstance(qr, QuestionResult)
        assert qr.question_id == "q1"
        assert qr.question_number == 1
        assert qr.verdict == "correct"
        assert qr.marks_awarded == 4.0

    def test_percentage_calculation(self):
        questions = self._make_questions([("mcq", "A"), ("mcq", "B")])
        answers = {"q1": "A", "q2": "C"}
        result = evaluate_script(questions, answers, DEFAULT_POLICY, total_marks=100, passing_marks=33)
        assert result.max_score == 8.0
        assert result.total_score == 3.0
        expected_pct = round(3.0 / 8.0 * 100, 2)
        assert result.percentage == expected_pct
