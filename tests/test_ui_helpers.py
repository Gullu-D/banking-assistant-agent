"""Tests for UI helper functions: _sparkline_svg and _step_indicator_html."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _sparkline_svg, _step_indicator_html


class TestSparklineSvg:
    def test_empty_returns_empty(self):
        assert _sparkline_svg([]) == ""

    def test_single_value_returns_empty(self):
        assert _sparkline_svg([42.0]) == ""

    def test_two_values_returns_svg(self):
        result = _sparkline_svg([10.0, 20.0])
        assert result.startswith("<svg")
        assert "</svg>" in result
        assert 'stroke="#78d8ba"' in result

    def test_custom_color(self):
        result = _sparkline_svg([1.0, 2.0, 3.0], color="#FF0000")
        assert 'stroke="#FF0000"' in result

    def test_flat_values_no_division_error(self):
        result = _sparkline_svg([5.0, 5.0, 5.0])
        assert "<svg" in result

    def test_path_has_correct_point_count(self):
        result = _sparkline_svg([1.0, 2.0, 3.0, 4.0])
        stroke_idx = result.index('fill="none"')
        path_start = result.rindex('d="M', 0, stroke_idx)
        path_end = result.index('"', path_start + 3)
        path_data = result[path_start + 3:path_end]
        points = path_data.replace("M", "").split("L")
        assert len(points) == 4

    def test_dimensions_in_output(self):
        result = _sparkline_svg([1.0, 2.0], width=100, height=30)
        assert 'width="100"' in result
        assert 'height="30"' in result


class TestStepIndicatorHtml:
    def test_first_step_active(self):
        result = _step_indicator_html(1, ["Upload", "Map", "Validate", "Import"])
        assert 'step-num active' in result
        assert "Upload" in result

    def test_second_step_marks_first_done(self):
        result = _step_indicator_html(2, ["Upload", "Map", "Validate", "Import"])
        assert 'step-num done' in result
        assert 'step-num active' in result

    def test_all_steps_present(self):
        steps = ["A", "B", "C"]
        result = _step_indicator_html(1, steps)
        for s in steps:
            assert s in result

    def test_step_lines_between_items(self):
        result = _step_indicator_html(1, ["A", "B", "C"])
        assert result.count("step-line") == 2

    def test_wrapping_div(self):
        result = _step_indicator_html(1, ["A", "B"])
        assert result.startswith('<div class="step-bar">')
        assert result.endswith("</div>")
