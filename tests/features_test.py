from textwrap import dedent
from nanoemoji.features import generate_fea, DEFAULT_GSUB_FEATURE_TAG
import pytest


@pytest.mark.parametrize("feature_tag", (DEFAULT_GSUB_FEATURE_TAG, "rlig"))
def test_generate_fea(feature_tag):
    rgi_sequences = [(0x1F64C,), (0x1F64C, 0x1F3FB), (0x1F64C, 0x1F3FC)]
    assert generate_fea(rgi_sequences, feature_tag=feature_tag) == dedent(
        f"""\
        languagesystem DFLT dflt;
        languagesystem latn dflt;

        feature {feature_tag} {{
          sub g_1f64c g_1f3fb by g_1f64c_1f3fb;
          sub g_1f64c g_1f3fc by g_1f64c_1f3fc;
        }} {feature_tag};
        """
    )
