from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.db import analytics


@pytest.mark.parametrize('year', [None, 2026])
@pytest.mark.parametrize('name, args', [
    ('get_capstones_by_program', ()),
    ('get_capstones_by_specialization', ()),
    ('get_capstone_trend_by_specialization', ()),
    ('get_capstone_status_flags', ()),
    ('get_specialization_report', (1,)),
    ('get_all_specialization_reports', ()),
])
def test_dashboard_and_exports_apply_parameterized_year(name, args, year):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = {'specialization_name': 'Web'}
    cursor.fetchall.return_value = []
    with patch.object(analytics, 'db_connect', return_value=connection):
        result = getattr(analytics, name)(*args, year=year)

    assert result[-1] is None
    sql, parameters = cursor.execute.call_args.args
    assert 'capstone_year = %s' in sql
    assert parameters[-2:] == (year, year)
    if name in {'get_capstones_by_program', 'get_capstones_by_specialization'}:
        assert sql.index('capstone_year = %s') < sql.index('GROUP BY')
        assert 'LEFT JOIN' in sql


@pytest.mark.parametrize('query, expected_year, expected_trend', [
    ('?year=2026', 2026, [2026]),
    ('', None, [2025, 2026]),
    ('?year=invalid', None, [2025, 2026]),
])
def test_dashboard_keeps_year_choices_and_filters_charts(query, expected_year, expected_trend):
    route = import_module('app.routes.admin.analytics')
    app = Flask(__name__)
    with app.test_request_context('/analytics' + query):
        with patch.multiple(
            route,
            get_capstones_by_specialization=MagicMock(return_value=([], None)),
            get_capstones_by_program=MagicMock(return_value=([], None)),
            get_capstone_status_flags=MagicMock(return_value=({}, None)),
            get_capstone_trend_by_specialization=MagicMock(return_value=([2025, 2026], {'Web': [2, 3]}, None)),
            render_template=MagicMock(side_effect=lambda template, **context: context),
        ):
            context = route.analytics.__wrapped__()
            route.get_capstones_by_program.assert_called_once_with(year=expected_year)
            route.get_capstones_by_specialization.assert_called_once_with(year=expected_year)
            route.get_capstone_status_flags.assert_called_once_with(year=expected_year)

    assert context['selected_year'] == expected_year
    assert context['available_years'] == [2026, 2025]
    assert context['trend_years'] == expected_trend
    assert context['trend_series']['Web'] == ([3] if expected_year else [2, 3])
