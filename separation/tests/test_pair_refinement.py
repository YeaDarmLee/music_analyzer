import numpy as np
import pytest
from music_analyzer.pair_refinement import repartition

def test_pair_repartition_preserves_sum_without_clipping():
    pair=np.array([[2.,-3.],[.1,.2]],dtype=np.float32)
    estimate=np.array([[1.5,-1.],[.4,.8]],dtype=np.float32)
    guitar,other=repartition(pair,estimate)
    np.testing.assert_array_equal(guitar,estimate)
    np.testing.assert_allclose(guitar.astype(np.float64)+other,pair,atol=1e-7,rtol=0)
    assert other[0,1]==-2.
    assert other[1,0]<0

def test_pair_mismatched_estimate_rejected():
    with pytest.raises(ValueError):
        repartition(np.ones((10,2),np.float32),np.ones((9,2),np.float32))

def test_pair_nonfinite_estimate_rejected():
    with pytest.raises(ValueError):
        repartition(np.ones((10,2),np.float32),np.full((10,2),np.nan,np.float32))
