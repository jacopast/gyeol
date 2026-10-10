"""시나리오 실험실 성질 테스트 (SPEC 9.9). 경계값은 가정하지 않고 성질만 검사한다."""

import numpy as np
import pytest

from gyeol.config import params
from gyeol.scenarios import build_network, layout, make_city, run_sweep, winners


@pytest.fixture(scope="module")
def sweep():
    return run_sweep(params())


def test_total_area_is_fixed_across_layouts():
    cfg = params()["scenarios"]
    city = make_city(cfg)
    areas = [sum(s["geom"].area for s in layout(n, city, cfg)) for n in cfg["layouts"]]
    assert np.allclose(areas, areas[0], rtol=1e-9)


def test_spaces_do_not_overlap():
    cfg = params()["scenarios"]
    city = make_city(cfg)
    for n in cfg["layouts"]:
        geoms = [s["geom"] for s in layout(n, city, cfg)]
        tot = sum(g.area for g in geoms)
        from shapely import union_all
        assert union_all(geoms).area == pytest.approx(tot, rel=1e-9)


def test_dispersed_beats_concentrated_when_beta0_alpha_below_1_no_congestion(sweep):
    """β = 0, α < 1, 혼잡 없음 → 분산형 os_gravity 평균이 집중형보다 높다 (모든 감쇠·기회비용·장벽 조건)."""
    w = winners(sweep, "access_mean")
    sel = w[(w.beta == 0) & (w.alpha < 1) & (~w.congestion)]
    assert len(sel) > 0
    assert (sel["dispersed"] > sel["concentrated"]).all()


def test_reversal_exists_for_large_beta(sweep):
    """β가 충분히 크면 집중형 ≥ 분산형인 칸이 존재한다 (혼잡 없음)."""
    w = winners(sweep, "access_mean")
    nc = w[~w.congestion]
    assert (nc[nc.beta > 0]["concentrated"] >= nc[nc.beta > 0]["dispersed"]).any()


def test_d_over_c_falls_as_beta_grows(sweep):
    """혼잡 없음에서 β를 키우면 D/C는 (같은 α·감쇠·조건에서) 늘지 않는다 — β는 큰 공간의 서비스권만 키운다."""
    w = winners(sweep, "access_mean")
    nc = w[~w.congestion]
    for _, g in nc.groupby(["decay", "alpha", "opportunity_cost", "barrier"]):
        r = g.sort_values("beta")["D_over_C"].to_numpy()
        assert np.all(np.diff(r) <= 1e-9)


def test_2sfca_population_weighted_mean_is_identity(sweep):
    """2SFCA 성질: 인구 가중 평균 = 총 면적 / 총 인구 (배치 무관)."""
    s = sweep[sweep.congestion & ~sweep.opportunity_cost]
    expected = s["total_area_m2"] / s["population"]
    assert np.allclose(s["access_mean"], expected, rtol=1e-6)


def test_barrier_removes_nodes_inside_parks():
    cfg = params()["scenarios"]
    city = make_city(cfg)
    geoms = [s["geom"] for s in layout("concentrated", city, cfg)]
    open_net, _ = build_network(city, cfg["node_spacing_m"])
    bar_net, xy = build_network(city, cfg["node_spacing_m"], geoms)
    assert bar_net.n < open_net.n
    from shapely import contains_xy
    assert not contains_xy(geoms[0].buffer(-1), xy[:, 0], xy[:, 1]).any()
