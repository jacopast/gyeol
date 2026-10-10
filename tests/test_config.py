from gyeol.config import params, params_hash, region


def test_params_load():
    p = params()
    assert p["access"]["default_alpha"] in p["access"]["alphas"]
    assert p["access"]["default_beta"] in p["access"]["betas"]
    assert len(params_hash()) == 12


def test_region_load():
    r = region("manhattan")
    assert r["id"] == "manhattan"
