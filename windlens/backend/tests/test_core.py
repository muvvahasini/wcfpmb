import pandas as pd
import pytest

from app.services.forecast_service import prepare_forecasts, select_decision_forecasts, tag_availability
from app.services.metrics_service import compute_metrics, match, prepare_actuals
from app.utils.timestamps import decision_cutoff_utc, parse_hhmm
from datetime import date


def fc(rows):
    return prepare_forecasts(pd.DataFrame(rows, columns=["startTime", "publishTime", "generation"]))


# Delivery 2026-01-15 12:00Z; cutoff D-1 (Jan 14) 12:00 UK (= 12:00Z in winter)
T = "2026-01-15T12:00:00Z"
ROWS = [(T, "2026-01-14T08:00:00Z", 5200), (T, "2026-01-14T11:30:00Z", 5600), (T, "2026-01-14T13:00:00Z", 6100)]


def test_latest_eligible_selected_and_late_excluded():
    sel = select_decision_forecasts(fc(ROWS), cutoff_uk="12:00")
    assert len(sel) == 1 and sel.loc[0, "generation"] == 5600


def test_publish_exactly_at_cutoff_is_eligible():
    sel = select_decision_forecasts(fc([(T, "2026-01-14T12:00:00Z", 1)]), "12:00")
    assert len(sel) == 1


def test_no_eligible_forecast_gives_no_row():
    assert select_decision_forecasts(fc([(T, "2026-01-14T13:00:00Z", 1)]), "12:00").empty


def test_availability_flags():
    t = tag_availability(fc(ROWS), "12:00").sort_values("publishTime")
    assert list(t["available_at_cutoff"]) == [True, True, False]


def test_default_cutoff_0920_excludes_1130():
    sel = select_decision_forecasts(fc(ROWS))
    assert sel.loc[0, "generation"] == 5200


def test_duplicates_dropped():
    assert len(fc(ROWS + [ROWS[0]])) == 3


def test_signed_and_abs_error_and_metrics():
    sel = select_decision_forecasts(fc(ROWS), "12:00")
    act = prepare_actuals(pd.DataFrame([
        {"startTime": T, "fuelType": "WIND", "generation": 5600},
        {"startTime": "2026-01-15T12:30:00Z", "fuelType": "WIND", "generation": 6000},
    ]))
    m = match(sel, act)
    assert m.loc[0, "error"] == -200 and m.loc[0, "abs_error"] == 200
    r = compute_metrics(m, 1, 1)
    assert r["mae"] == 200 and r["rmse"] == 200 and r["bias"] == -200


def test_half_hour_actuals_are_averaged_to_complete_hour():
    actuals = prepare_actuals(pd.DataFrame([
        {"startTime": "2026-01-15T12:00:00Z", "generation": 5600},
        {"startTime": "2026-01-15T12:30:00Z", "generation": 6000},
        {"startTime": "2026-01-15T13:00:00Z", "generation": 7000},
    ]))
    assert len(actuals) == 1
    assert actuals.loc[0, "startTime"] == pd.Timestamp("2026-01-15T12:00:00Z")
    assert actuals.loc[0, "generation"] == 5800


def test_incomplete_half_hour_hour_is_excluded():
    actuals = prepare_actuals(pd.DataFrame([
        {"startTime": "2026-01-15T12:00:00Z", "generation": 5600},
        {"startTime": "2026-01-15T13:00:00Z", "generation": 7000},
        {"startTime": "2026-01-15T13:30:00Z", "generation": 7200},
    ]))
    assert len(actuals) == 1
    assert actuals.loc[0, "startTime"] == pd.Timestamp("2026-01-15T13:00:00Z")
    assert actuals.loc[0, "generation"] == 7100


def test_metric_definitions():
    m = pd.DataFrame({"generation_actual": [1000, 1000], "error": [100, -300]})
    m["abs_error"] = m["error"].abs()
    r = compute_metrics(m, 2, 2)
    assert r["mae"] == 200 and r["bias"] == -100
    assert r["rmse"] == pytest.approx(((100**2 + 300**2) / 2) ** 0.5)


def test_mape_excludes_near_zero_actuals():
    m = pd.DataFrame({"generation_actual": [0, 1000], "error": [50, 100]})
    m["abs_error"] = m["error"].abs()
    r = compute_metrics(m, 2, 2)
    assert r["mape"] == pytest.approx(10.0) and r["mape_excluded"] == 1


def test_missing_values_not_zero_filled():
    act = prepare_actuals(pd.DataFrame([{"startTime": T, "fuelType": "WIND", "generation": None}]))
    assert act.empty
    r = compute_metrics(match(select_decision_forecasts(fc(ROWS), "12:00"), act), 1, 0)
    assert r["mae"] is None and r["matched"] == 0


def test_conflicting_actual_duplicates_rejected():
    with pytest.raises(ValueError):
        prepare_actuals(pd.DataFrame([{"startTime": T, "generation": 1}, {"startTime": T, "generation": 2}]))


def test_non_wind_filtered():
    act = prepare_actuals(pd.DataFrame([{"startTime": T, "fuelType": "CCGT", "generation": 9}]))
    assert act.empty


def test_uk_dst_cutoff_in_utc():
    # BST: 09:20 UK on 2026-07-01 is 08:20Z; GMT: 09:20 UK on 2026-01-14 is 09:20Z
    assert decision_cutoff_utc(date(2026, 7, 2), parse_hhmm("09:20")) == pd.Timestamp("2026-07-01T08:20:00Z")
    assert decision_cutoff_utc(date(2026, 1, 15), parse_hhmm("09:20")) == pd.Timestamp("2026-01-14T09:20:00Z")


def test_one_to_one_matching_no_fanout():
    sel = select_decision_forecasts(fc(ROWS), "12:00")
    act = prepare_actuals(pd.DataFrame([
        {"startTime": T, "generation": 5700},
        {"startTime": "2026-01-15T12:30:00Z", "generation": 5900},
    ]))
    assert len(match(sel, act)) == 1
