"""합성 데이터로 지표 엔진 검사 (M2)."""

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from gyeol.config import params
from gyeol.metrics.access import cover, decay, g2sfca, gravity, radius
from gyeol.network import edges_to_network
from gyeol.raster import coarsen_mode, grain_counts, patch_max_area
from gyeol.sample import aggregate, entropy, interspersion, walkshed_cells

A = params()["access"]


def test_radius_scales_with_beta_and_clips():
    S = np.array([400.0, 10_000.0, 1_000_000.0])
    assert np.allclose(radius(S, 0.0, A), A["r0_m"])
    r = radius(S, 0.5, A)
    assert r[1] == pytest.approx(A["r0_m"])          # S = S0
    assert r[0] == A["r_min_m"] and r[2] == A["r_max_m"]


def test_gaussian_decay_shape():
    R = np.array([800.0])
    assert decay(np.array([0.0]), R, "gaussian", A)[0] == pytest.approx(1.0)
    assert decay(np.array([800.0]), R, "gaussian", A)[0] == pytest.approx(0.0, abs=1e-12)
    assert decay(np.array([900.0]), R, "gaussian", A)[0] == 0.0
    d = np.linspace(0, 800, 9)
    assert np.all(np.diff(decay(d, np.full(9, 800.0), "gaussian", A)) <= 0)


def test_step_decay_follows_radius_scale():
    R = np.array([1600.0])  # scale 2
    f = lambda d: decay(np.array([d]), R, "step", A)[0]  # noqa: E731
    assert f(700) == 1.0 and f(1000) == A["step_mid"] and f(1700) == 0.0


def _D(rows):
    """rows: (cell, space, dist) → 저장 규약(거리+1) 희소 행렬."""
    r, c, d = zip(*rows, strict=True)
    return sp.csr_matrix((np.array(d, float) + 1, (r, c)), shape=(max(r) + 1, max(c) + 1))


def test_gravity_alpha_and_mask():
    D = _D([(0, 0, 0.0), (0, 1, 0.0)])
    S = np.array([100.0, 400.0])
    g1 = gravity(D, S, np.array([True, True]), 1.0, 0.0, "gaussian", A)[0]
    assert g1 == pytest.approx(500.0)
    g05 = gravity(D, S, np.array([True, True]), 0.5, 0.0, "gaussian", A)[0]
    assert g05 == pytest.approx(10 + 20)
    assert gravity(D, S, np.array([True, False]), 1.0, 0.0, "gaussian", A)[0] == pytest.approx(100.0)


def test_g2sfca_conserves_supply():
    """2SFCA 성질: 모든 공간에 수요가 있으면 Σ_i P_i A_i = Σ_j S_j."""
    rng = np.random.default_rng(0)
    rows = [(i, j, float(rng.uniform(0, 600))) for i in range(30) for j in range(4) if rng.random() < 0.7]
    rows += [(0, j, 10.0) for j in range(4) if not any(r[0] == 0 and r[1] == j for r in rows)]
    D = _D(rows)
    S = np.array([1000.0, 2000.0, 500.0, 4000.0])
    P = rng.uniform(10, 100, D.shape[0])
    a = g2sfca(D, S, np.ones(4, bool), P, 0.0, "gaussian", A)
    assert (P * a).sum() == pytest.approx(S.sum(), rel=1e-9)


def test_cover_respects_limit_and_min_area():
    D = _D([(0, 0, 100.0), (1, 0, 500.0), (2, 1, 50.0)])
    S = np.array([5000.0, 10.0])
    c = cover(D, S, np.array([True, True]), 360, 400)
    assert c.tolist() == [1.0, 0.0, 0.0]


def test_interspersion_extremes():
    # 완전 분리(두 반쪽) → 0 근처, 바둑판 → 2 (모든 쌍이 섞임 / 기대 0.5)
    half = np.zeros((10, 10), np.uint8)
    half[:, :5], half[:, 5:] = 1, 3
    chk = np.where((np.indices((10, 10)).sum(0) % 2) == 0, 1, 3).astype(np.uint8)
    lbl = np.ones((10, 10), np.int32)
    gh = grain_counts(half, lbl, 1, "base")
    gc = grain_counts(chk, lbl, 1, "base")
    ih = interspersion(gh["nP"][0], gh["nQ"][0], gh["PP"][0], gh["PQ"][0], gh["QQ"][0])
    ic = interspersion(gc["nP"][0], gc["nQ"][0], gc["PP"][0], gc["PQ"][0], gc["QQ"][0])
    assert ih == pytest.approx((10 / 180) / 0.5)
    assert ic == pytest.approx(2.0)


def test_interspersion_random_is_about_one():
    rng = np.random.default_rng(1)
    a = np.where(rng.random((200, 200)) < 0.3, 1, 3).astype(np.uint8)
    g = grain_counts(a, np.ones_like(a, np.int32), 1, "base")
    assert interspersion(g["nP"][0], g["nQ"][0], g["PP"][0], g["PQ"][0], g["QQ"][0]) == pytest.approx(1.0, abs=0.03)


def test_pops_variant_moves_class_6():
    a = np.array([[6, 3]], np.uint8)
    lbl = np.ones_like(a, np.int32)
    assert grain_counts(a, lbl, 1, "base")["nP"][0] == 0
    assert grain_counts(a, lbl, 1, "pops")["nP"][0] == 1


def test_coarsen_mode_tie_top_left():
    a = np.array([[1, 3], [3, 1]], np.uint8)
    assert coarsen_mode(a, 2)[0, 0] == 1
    b = np.array([[3, 1], [1, 3]], np.uint8)
    assert coarsen_mode(b, 2)[0, 0] == 3
    c = np.array([[3, 1], [1, 1]], np.uint8)
    assert coarsen_mode(c, 2)[0, 0] == 1


def test_patch_excludes_sidewalk_and_reports_touching_max():
    # 보도(4)가 열린 공간 두 덩어리를 나눈다: 왼쪽 4칸 패치, 오른쪽 1칸 패치
    a = np.array([[1, 1, 4, 1], [1, 1, 4, 3]], np.uint8)
    lbl = np.array([[1, 1, 2, 2], [1, 1, 2, 2]], np.int32)
    m = patch_max_area(a, lbl, 2, "base", 5.0)
    assert m.tolist() == [100.0, 25.0]
    lbl2 = np.array([[1, 2, 2, 2], [1, 2, 2, 2]], np.int32)
    assert patch_max_area(a, lbl2, 2, "base", 5.0).tolist() == [100.0, 100.0]   # 패치 일부만 닿아도 전체 면적


def test_entropy():
    assert entropy([5, 5]) == pytest.approx(np.log(2))
    assert entropy([3]) == 0.0
    assert entropy([]) is None


def _toy_network():
    # 0 - 1 - 2 - 3 (간격 100m)
    x = np.array([0, 100, 200, 300.0])
    y = np.zeros(4)
    return edges_to_network(x, y, {(0, 1): 100.0, (1, 2): 100.0, (2, 3): 100.0})


def test_walkshed_network_distance():
    net = _toy_network()
    cell_node = np.array([0, 1, 2, 3, -1])
    idx = walkshed_cells(net, cell_node, 0, minutes=150 / 72, speed=1.2)   # 150m
    assert idx.tolist() == [0, 1]


def test_aggregate_additive_stats():
    prm = params()
    res = prm["raster"]["resolution_m"]
    n = 2
    cells = pd.DataFrame({"pop_night": [100.0, 0.0], "pop_day": [50.0, 50.0], "land_m2": [1e4, 1e4],
                          "street_len_m": [100.0, 100.0], "a_sidewalk_m2": [400.0, 600.0], "a_roadway_m2": [1000.0, 1000.0],
                          "a_open_free_m2": [100.0, 300.0], "a_open_free_green_m2": [50.0, 150.0], "a_pops_m2": [0, 0],
                          "a_pops_green_m2": [0, 0], "bldg_street_a_m2": [10.0, 30.0], "bldg_street_ha_m3": [100.0, 900.0],
                          "patch_base_max_m2": [5.0, 7.0], "patch_pops_max_m2": [5.0, 7.0], "income": [50000.0, np.nan]})
    for v in ("base", "pops"):
        for r in prm["raster"]["multiscale_m"]:
            for k, val in {"nP": 10, "nQ": 10, "nV": 0, "PP": 5, "PQ": 10, "QQ": 5}.items():
                cells[f"g_{v}_{r}_{k}"] = float(val)
    a = prm["access"]
    from gyeol.metrics.cellmetrics import lens_key
    cm = pd.DataFrame({lens_key("os_gravity", "with_plaza_playground", "gaussian", 1.0, 0.25): [1.0, 3.0],
                       lens_key("os_g2sfca", "with_plaza_playground", "gaussian", None, 0.25, "night"): [1.0, 1.0],
                       lens_key("os_g2sfca", "with_plaza_playground", "gaussian", None, 0.25, "day"): [1.0, 1.0],
                       lens_key("os_cover_5", "with_plaza_playground"): [1.0, 0.0],
                       lens_key("os_cover_10", "with_plaza_playground"): [1.0, 1.0],
                       "amen_t_grocery": [2.0, 4.0], "amen_t_pharmacy": [6.0, 1.0]})
    lens = {"definition": "with_plaza_playground", "decay": "gaussian", "alpha": 1.0, "beta": 0.25}
    out = aggregate(np.arange(n), cells, cm, [[0, 2], [0, 1, 1, 1]], lens, prm)
    assert out["os_gravity"] == 2.0
    assert out["os_cover_5"] == 1.0                           # 인구 가중 (두 번째 셀 인구 0)
    assert out["os_greenness"] == pytest.approx(0.5)
    assert out["nolli_ratio"] == pytest.approx(0.5)
    assert out["edge_density"] == pytest.approx(20 * res / (40 * res * res / 1e4))
    assert out["interspersion"] == pytest.approx((20 / 40) / 0.5)
    assert out["sidewalk_width"] == pytest.approx(1000 / 400)
    assert out["lane_share"] == pytest.approx(2000 / 3000)
    assert out["enclosure"] == pytest.approx((3000 / 200) / (1000 / 40))
    assert out["largest_public_patch"] == 7.0
    assert out["amenity_daily"] == pytest.approx((6 + 4) / 2)
    assert out["amenity_diversity"] == pytest.approx(entropy([3, 1]))
    assert out["ctx_density"] == pytest.approx(100 / 2)
    assert out["ctx_daytime_ratio"] == pytest.approx(1.0)
    assert out["ctx_income"] == pytest.approx(50000)
    assert out["frontage_permeability"] is None
    assert a["default_alpha"] == 1.0
